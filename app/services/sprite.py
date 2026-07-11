from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO

from PIL import Image

from app.models.sprite_artifact import SpriteArtifact
from app.schemas.sprite import AssetSpec, AssetSpecRequest, BlueprintStrategy, SpriteBlueprint
from app.services.llm_generation import LlmGenerationService
from app.services.procedural_sprite import ProceduralSpriteError, render_procedural_sprite
from app.services.procedural_sprite import (
    render_blueprint as render_blueprint_png,
)
from app.services.settings import get_app_settings
from app.services.sprite_artifact_store import SpriteArtifactStore, SpriteArtifactStoreError
from app.services.sprite_blueprint import BlueprintGenerationError, generate_sprite_blueprint
from app.services.sprite_interpretation import SpriteSpecError, create_asset_spec_from_request
from app.services.sprite_processing import SpriteProcessingError, process_sprite_image
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

    async def create_asset_spec(self, request: AssetSpecRequest) -> tuple[AssetSpec, SpriteArtifact]:
        logger.info(
            "sprite asset spec generation started",
            extra={"prompt_chars": len(request.prompt), "use_llm": request.use_llm},
        )
        try:
            spec = await create_asset_spec_from_request(request, llm_service=self.llm_service)
            artifact = self._store().create_asset_spec_artifact(prompt=request.prompt, asset_spec=spec)
        except SpriteSpecError as exc:
            raise SpriteError(str(exc)) from exc
        logger.info(
            "sprite asset spec generation completed",
            extra={
                "artifact_id": artifact.artifact_id,
                "asset_type": spec.asset_type,
                "subject": spec.subject,
                "width": spec.size.width,
                "height": spec.size.height,
            },
        )
        return spec, artifact

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
        try:
            asset_spec = store.read_asset_spec(artifact_id)
            generated = await generate_sprite_blueprint(
                asset_spec,
                strategy=strategy,
                seed=seed,
                llm_service=self.llm_service,
                provider=provider,
                model=model,
                base_url=base_url,
            )
            artifact = store.save_blueprint(
                artifact_id,
                generated.blueprint,
                generation={
                    "strategy": generated.strategy,
                    "provider": generated.provider,
                    "model": generated.model,
                    "seed": seed,
                },
            )
        except (BlueprintGenerationError, ProceduralSpriteError, SpriteArtifactStoreError) as exc:
            raise SpriteError(str(exc)) from exc
        logger.info(
            "sprite blueprint generation completed",
            extra={
                "artifact_id": artifact_id,
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
        try:
            artifact = store.load_artifact(artifact_id)
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
            store.save_render_png(artifact_id, result.png_bytes)
        except (ProceduralSpriteError, SpriteArtifactStoreError, SpriteQualityError) as exc:
            raise SpriteError(str(exc)) from exc
        return result.png_bytes, result.report

    def render_blueprint(self, artifact_id: str, *, seed: int = 0) -> tuple[bytes, dict[str, object]]:
        store = self._store()
        try:
            artifact = store.load_artifact(artifact_id)
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
            store.save_render_png(artifact_id, result.png_bytes)
        except (ProceduralSpriteError, SpriteArtifactStoreError, SpriteQualityError) as exc:
            raise SpriteError(str(exc)) from exc
        logger.info(
            "sprite blueprint render completed",
            extra={"artifact_id": artifact_id, "subject": artifact.subject, "seed": seed},
        )
        return result.png_bytes, result.report

    def get_asset_spec(self, artifact_id: str) -> AssetSpec:
        try:
            return self._store().read_asset_spec(artifact_id)
        except SpriteArtifactStoreError as exc:
            raise SpriteError(str(exc)) from exc


__all__ = [
    "SpriteError",
    "SpriteService",
]
