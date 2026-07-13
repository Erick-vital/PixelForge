from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from app.schemas.settings import SettingsResponse
from app.schemas.sprite import (
    AssetSpec,
    AssetSpecRequest,
    RenderBlueprintRequest,
    RenderSpriteRequest,
    SpriteArtifactAssetSpecResponse,
    SpriteArtifactBlueprintResponse,
    SpriteBlueprintRequest,
)
from app.services.settings import (
    MissingLlmApiKeyError,
    env_file_path,
    get_app_settings,
    get_llm_base_url,
    get_llm_default_model,
    get_llm_provider,
)
from app.services.sprite import SpriteError, SpriteService

router = APIRouter(prefix="/api", tags=["api"])


def get_sprite_service() -> SpriteService:
    return SpriteService()


def _render_response(png: bytes, report: dict[str, object], *, artifact_id: str | None = None) -> Response:
    headers = {
        "X-PixelForge-Render-Recipe": str(report["recipe"]),
        "X-PixelForge-Render-Seed": str(report["seed"]),
        "X-PixelForge-Validation-Size": f"{report['width']}x{report['height']}",
        "X-PixelForge-Validation-Transparent": str(report["transparent"]).lower(),
        "X-PixelForge-Validation-Non-Empty": str(report["non_empty"]).lower(),
        "X-PixelForge-Validation-Colors": str(report["color_count"]),
    }
    quality = report.get("quality")
    if isinstance(quality, dict):
        headers.update(
            {
                "X-PixelForge-Quality-Passed": str(quality["passed"]).lower(),
                "X-PixelForge-Quality-Components": str(quality["connected_components"]),
                "X-PixelForge-Quality-Occupancy": str(quality["occupancy_ratio"]),
                "X-PixelForge-Quality-Isolated-Pixels": str(quality["isolated_pixel_count"]),
            }
        )
    if artifact_id:
        headers["X-PixelForge-Artifact-Id"] = artifact_id
    return Response(content=png, media_type="image/png", headers=headers)


@router.post("/asset-spec", response_model=SpriteArtifactAssetSpecResponse)
async def create_asset_spec(
    payload: AssetSpecRequest, service: SpriteService = Depends(get_sprite_service)
) -> SpriteArtifactAssetSpecResponse:
    try:
        asset_spec, artifact, decision_trace = await service.create_asset_spec(payload)
    except MissingLlmApiKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SpriteError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SpriteArtifactAssetSpecResponse(
        artifact_id=artifact.artifact_id,
        artifact_dir=str(artifact.artifact_dir),
        status=artifact.status,
        subject=artifact.subject,
        asset_spec=asset_spec,
        decision_trace=decision_trace,
    )


@router.post("/blueprint", response_model=SpriteArtifactBlueprintResponse)
async def blueprint(
    payload: SpriteBlueprintRequest, service: SpriteService = Depends(get_sprite_service)
) -> SpriteArtifactBlueprintResponse:
    try:
        blueprint, artifact = await service.create_sprite_blueprint(
            payload.artifact_id,
            strategy=payload.strategy,
            seed=payload.seed,
            provider=payload.provider,
            model=payload.model,
            base_url=payload.base_url,
        )
        asset_spec = service.get_asset_spec(payload.artifact_id)
    except SpriteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SpriteArtifactBlueprintResponse(
        artifact_id=artifact.artifact_id,
        artifact_dir=str(artifact.artifact_dir),
        status=artifact.status,
        subject=artifact.subject,
        asset_spec=asset_spec,
        blueprint=blueprint,
    )


@router.post("/render-sprite")
def render_sprite(payload: RenderSpriteRequest, service: SpriteService = Depends(get_sprite_service)) -> Response:
    try:
        png, report = service.render_sprite(payload.artifact_id, seed=payload.seed)
    except SpriteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _render_response(png, report, artifact_id=payload.artifact_id)


@router.post("/render-blueprint")
def render_blueprint(payload: RenderBlueprintRequest, service: SpriteService = Depends(get_sprite_service)) -> Response:
    try:
        png, report = service.render_blueprint(payload.artifact_id, seed=payload.seed)
    except SpriteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _render_response(png, report, artifact_id=payload.artifact_id)


@router.post("/process-sprite")
async def process_sprite(
    image: UploadFile = File(...),
    asset_spec_json: str = Form(...),
    service: SpriteService = Depends(get_sprite_service),
) -> Response:
    try:
        asset_spec = AssetSpec.model_validate(json.loads(asset_spec_json))
        png, report = service.process_sprite(await image.read(), asset_spec)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="asset_spec_json must be valid JSON") from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except SpriteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "X-PixelForge-Validation-Size": f"{report['width']}x{report['height']}",
            "X-PixelForge-Validation-Transparent": str(report["transparent"]).lower(),
            "X-PixelForge-Validation-Non-Empty": str(report["non_empty"]).lower(),
        },
    )


@router.get("/settings", response_model=SettingsResponse)
def settings() -> SettingsResponse:
    app_settings = get_app_settings()
    provider = get_llm_provider(settings=app_settings)
    return SettingsResponse(
        data_dir=str(app_settings.data_dir),
        items_dir=str(app_settings.items_dir),
        llm_provider=provider,
        llm_default_model=get_llm_default_model(provider),
        llm_base_url=get_llm_base_url(provider=provider, settings=app_settings),
        env_file=env_file_path(),
        app_log_level=app_settings.log_level,
    )
