from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from io import BytesIO

from PIL import Image

from app.models.sprite_artifact import SpriteArtifact
from app.schemas.sprite import AssetSpec, AssetSpecDecisionTrace, AssetSpecRequest, BlueprintStrategy, SpriteBlueprint
from app.services.llm_generation import LlmGenerationService
from app.services.procedural_sprite import ProceduralSpriteError, render_procedural_sprite
from app.services.procedural_sprite import (
    render_blueprint as render_blueprint_png,
)
from app.services.settings import get_app_settings
from app.services.sprite_artifact_store import SpriteArtifactStore, SpriteArtifactStoreError
from app.services.sprite_blueprint import BlueprintGenerationError, generate_sprite_blueprint
from app.services.sprite_interpretation import SpriteSpecError, create_asset_spec_from_request_with_trace
from app.services.sprite_processing import SpriteProcessingError, process_sprite_image
from app.services.trace_context import log_context, trace_details
from app.sprite_engine.quality.structural import SpriteQualityError, require_sprite_quality

logger = logging.getLogger(__name__)


class SpriteError(ValueError):
    pass


@dataclass
class SpriteService:
    llm_service: LlmGenerationService | None = None
    artifact_store: SpriteArtifactStore | None = None

    def __post_init__(self) -> None:
        if self.artifact_store is None:
            settings = get_app_settings()
            self.artifact_store = SpriteArtifactStore(data_dir=settings.data_dir, items_dir=settings.items_dir)

    def _store(self) -> SpriteArtifactStore:
        if self.artifact_store is None:
            raise SpriteError("Sprite artifact store is not configured")
        return self.artifact_store

    async def create_asset_spec(
        self, request: AssetSpecRequest
    ) -> tuple[AssetSpec, SpriteArtifact, AssetSpecDecisionTrace]:
        started_at = time.perf_counter()
        logger.info(
            "sprite asset spec generation started",
            extra={
                "operation": "asset_spec",
                "stage": "interpretation",
                "outcome": "started",
                "prompt_chars": len(request.prompt),
                "use_llm": request.use_llm,
            },
        )
        try:
            spec, decision_trace = await create_asset_spec_from_request_with_trace(
                request, llm_service=self.llm_service
            )
            artifact = self._store().create_asset_spec_artifact(
                prompt=request.prompt, asset_spec=spec, decision_trace=decision_trace
            )
        except SpriteSpecError as exc:
            logger.warning(
                "sprite asset spec generation failed",
                extra={
                    "operation": "asset_spec",
                    "stage": "interpretation",
                    "outcome": "failed",
                    "duration_ms": _elapsed_ms(started_at),
                    "error_type": type(exc).__name__,
                },
            )
            raise SpriteError(str(exc)) from exc
        logger.info(
            "sprite asset spec generation completed",
            extra={
                "artifact_id": artifact.artifact_id,
                "operation": "asset_spec",
                "stage": "interpretation",
                "outcome": "completed",
                "duration_ms": _elapsed_ms(started_at),
                "asset_type": spec.asset_type,
                "subject": spec.subject,
                "width": spec.size.width,
                "height": spec.size.height,
            },
        )
        return spec, artifact, decision_trace

    async def create_sprite_blueprint(
        self,
        artifact_id: str,
        *,
        strategy: BlueprintStrategy = "auto",
        seed: int = 0,
        provider: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> tuple[SpriteBlueprint, SpriteArtifact]:
        store = self._store()
        started_at = time.perf_counter()
        try:
            asset_spec = store.read_asset_spec(artifact_id)
            with log_context(artifact_id=artifact_id):
                logger.info(
                    "sprite blueprint generation started",
                    extra={
                        "operation": "blueprint",
                        "stage": "generation",
                        "outcome": "started",
                        "strategy": strategy,
                        "seed": seed,
                    },
                )
                store.append_trace_event(
                    artifact_id,
                    event_type="blueprint.generation.started",
                    stage="blueprint",
                    outcome="started",
                    status_before=store.load_artifact(artifact_id).status,
                    details=trace_details(requested_strategy=strategy, seed=seed),
                )
                generated = await generate_sprite_blueprint(
                    asset_spec,
                    strategy=strategy,
                    seed=seed,
                    llm_service=self.llm_service,
                    provider=provider,
                    model=model,
                    base_url=base_url,
                )
                generation = {
                    "requested_strategy": strategy,
                    "resolved_strategy": generated.strategy,
                    "strategy": generated.strategy,
                    "provider": generated.provider,
                    "model": generated.model,
                    "grammar": generated.grammar,
                    "grammar_version": 1 if generated.grammar else None,
                    "family": asset_spec.family,
                    "archetype": asset_spec.archetype,
                    "skeleton": generated.skeleton,
                    "fallback_reason": generated.fallback_reason,
                    "seed": seed,
                    "semantic_quality": generated.semantic_quality.as_dict() if generated.semantic_quality else None,
                }
                artifact = store.save_blueprint(artifact_id, generated.blueprint, generation=generation)
                store.append_trace_event(
                    artifact_id,
                    event_type="blueprint.generation.completed",
                    stage="blueprint",
                    outcome="completed",
                    status_after=artifact.status,
                    details=trace_details(
                        duration_ms=_elapsed_ms(started_at),
                        requested_strategy=strategy,
                        resolved_strategy=generated.strategy,
                        provider=generated.provider,
                        model=generated.model,
                        seed=seed,
                        primitive_count=len(generated.blueprint.primitives),
                        semantic_issue_codes=(
                            list(generated.semantic_quality.issue_codes) if generated.semantic_quality else None
                        ),
                    ),
                )
        except BlueprintGenerationError as exc:
            generation_error = _safe_generation_error(exc)
            store.mark_blueprint_failed(
                artifact_id,
                generation_error=generation_error,
                trace_event_details=trace_details(
                    duration_ms=_elapsed_ms(started_at), requested_strategy=strategy, seed=seed
                ),
            )
            logger.warning(
                "sprite blueprint generation failed",
                extra={
                    "artifact_id": artifact_id,
                    "operation": "blueprint",
                    "stage": "generation",
                    "outcome": "failed",
                    "duration_ms": _elapsed_ms(started_at),
                    "issue_codes": generation_error["issue_codes"],
                },
            )
            raise SpriteError(str(exc)) from exc
        except (ProceduralSpriteError, SpriteArtifactStoreError) as exc:
            logger.warning(
                "sprite blueprint generation failed",
                extra={
                    "artifact_id": artifact_id,
                    "operation": "blueprint",
                    "stage": "generation",
                    "outcome": "failed",
                    "duration_ms": _elapsed_ms(started_at),
                    "error_type": type(exc).__name__,
                },
            )
            raise SpriteError(str(exc)) from exc
        logger.info(
            "sprite blueprint generation completed",
            extra={
                "artifact_id": artifact_id,
                "operation": "blueprint",
                "stage": "generation",
                "outcome": "completed",
                "duration_ms": _elapsed_ms(started_at),
                "strategy": generated.strategy,
                "subject": asset_spec.subject,
                "primitive_count": len(generated.blueprint.primitives),
            },
        )
        return generated.blueprint, artifact

    def process_sprite(self, image_bytes: bytes, asset_spec: AssetSpec) -> tuple[bytes, dict[str, object]]:
        try:
            result = process_sprite_image(image_bytes, asset_spec)
        except SpriteProcessingError as exc:
            raise SpriteError(str(exc)) from exc
        return result.png_bytes, result.report

    def render_sprite(self, artifact_id: str, *, seed: int = 0) -> tuple[bytes, dict[str, object]]:
        store = self._store()
        started_at = time.perf_counter()
        artifact: SpriteArtifact | None = None
        try:
            artifact = store.load_artifact(artifact_id)
            with log_context(artifact_id=artifact_id):
                store.append_trace_event(
                    artifact_id,
                    event_type="render.started",
                    stage="render",
                    outcome="started",
                    status_before=artifact.status,
                    details={
                        "seed": seed,
                        "render_source": "blueprint" if artifact.blueprint_json_path.exists() else "procedural",
                    },
                )
                asset_spec = store.read_asset_spec(artifact_id)
                if artifact.blueprint_json_path is not None and artifact.blueprint_json_path.exists():
                    blueprint = store.read_blueprint(artifact_id)
                    result = render_blueprint_png(
                        blueprint,
                        width=asset_spec.size.width,
                        height=asset_spec.size.height,
                        seed=seed,
                        max_colors=asset_spec.processing_profile.palette_max_colors,
                    )
                else:
                    result = render_procedural_sprite(asset_spec, seed=seed)
                quality = require_sprite_quality(Image.open(BytesIO(result.png_bytes)))
                result.report["quality"] = quality.as_dict()
                result.report["blueprint_generation"] = store.read_metadata(artifact_id).get("blueprint_generation", {})
                store.save_render_png(artifact_id, result.png_bytes)
                store.append_trace_event(
                    artifact_id,
                    event_type="render.completed",
                    stage="render",
                    outcome="completed",
                    status_after="rendered",
                    details=trace_details(
                        duration_ms=_elapsed_ms(started_at),
                        seed=seed,
                        output_bytes=len(result.png_bytes),
                        recipe=result.report.get("recipe"),
                        quality_passed=quality.passed,
                    ),
                )
        except (ProceduralSpriteError, SpriteArtifactStoreError, SpriteQualityError) as exc:
            self._record_render_failure(store, artifact, artifact_id, seed, started_at, exc)
            raise SpriteError(str(exc)) from exc
        logger.info(
            "sprite render completed",
            extra={
                "artifact_id": artifact_id,
                "operation": "render",
                "stage": "render",
                "outcome": "completed",
                "duration_ms": _elapsed_ms(started_at),
                "seed": seed,
            },
        )
        return result.png_bytes, result.report

    def render_blueprint(self, artifact_id: str, *, seed: int = 0) -> tuple[bytes, dict[str, object]]:
        store = self._store()
        started_at = time.perf_counter()
        artifact: SpriteArtifact | None = None
        try:
            artifact = store.load_artifact(artifact_id)
            with log_context(artifact_id=artifact_id):
                store.append_trace_event(
                    artifact_id,
                    event_type="render.started",
                    stage="render",
                    outcome="started",
                    status_before=artifact.status,
                    details={"seed": seed, "render_source": "blueprint"},
                )
                asset_spec = store.read_asset_spec(artifact_id)
                blueprint = store.read_blueprint(artifact_id)
                result = render_blueprint_png(
                    blueprint,
                    width=asset_spec.size.width,
                    height=asset_spec.size.height,
                    seed=seed,
                    max_colors=asset_spec.processing_profile.palette_max_colors,
                )
                quality = require_sprite_quality(Image.open(BytesIO(result.png_bytes)))
                result.report["quality"] = quality.as_dict()
                result.report["blueprint_generation"] = store.read_metadata(artifact_id).get("blueprint_generation", {})
                store.save_render_png(artifact_id, result.png_bytes)
                store.append_trace_event(
                    artifact_id,
                    event_type="render.completed",
                    stage="render",
                    outcome="completed",
                    status_after="rendered",
                    details=trace_details(
                        duration_ms=_elapsed_ms(started_at),
                        seed=seed,
                        output_bytes=len(result.png_bytes),
                        recipe=result.report.get("recipe"),
                        quality_passed=quality.passed,
                    ),
                )
        except (ProceduralSpriteError, SpriteArtifactStoreError, SpriteQualityError) as exc:
            self._record_render_failure(store, artifact, artifact_id, seed, started_at, exc)
            raise SpriteError(str(exc)) from exc
        logger.info(
            "sprite blueprint render completed",
            extra={
                "artifact_id": artifact_id,
                "operation": "render",
                "stage": "render",
                "outcome": "completed",
                "duration_ms": _elapsed_ms(started_at),
                "subject": artifact.subject,
                "seed": seed,
            },
        )
        return result.png_bytes, result.report

    def _record_render_failure(
        self,
        store: SpriteArtifactStore,
        artifact: SpriteArtifact | None,
        artifact_id: str,
        seed: int,
        started_at: float,
        error: Exception,
    ) -> None:
        if artifact is not None:
            store.append_trace_event(
                artifact_id,
                event_type="render.failed",
                stage="render",
                outcome="failed",
                details={"duration_ms": _elapsed_ms(started_at), "seed": seed, "error_type": type(error).__name__},
            )
        logger.warning(
            "sprite render failed",
            extra={
                "artifact_id": artifact_id,
                "operation": "render",
                "stage": "render",
                "outcome": "failed",
                "duration_ms": _elapsed_ms(started_at),
                "error_type": type(error).__name__,
            },
        )

    def get_asset_spec(self, artifact_id: str) -> AssetSpec:
        try:
            return self._store().read_asset_spec(artifact_id)
        except SpriteArtifactStoreError as exc:
            raise SpriteError(str(exc)) from exc

    def get_blueprint_generation(self, artifact_id: str) -> dict[str, object]:
        try:
            metadata = self._store().read_metadata(artifact_id)
            generation = metadata.get("blueprint_generation", {})
            return generation if isinstance(generation, dict) else {}
        except SpriteArtifactStoreError as exc:
            raise SpriteError(str(exc)) from exc


def _safe_generation_error(error: BlueprintGenerationError) -> dict[str, object]:
    known_codes = (
        "side_view_symmetry_too_high",
        "side_view_missing_directional_feature",
        "side_view_missing_limb_depth",
        "front_view_symmetry_too_low",
    )
    codes = [code for code in known_codes if code in str(error)]
    return {"issue_codes": codes or ["blueprint_generation_failed"]}


def _elapsed_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)


__all__ = [
    "SpriteError",
    "SpriteService",
]
