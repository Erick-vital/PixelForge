from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from app.schemas.sprite import (
    AssetSpec,
    AssetSpecRequest,
    GenerationPromptRequest,
    GenerationPromptResponse,
    ProcessingPlanRequest,
    ProcessingPlanResponse,
)
from app.schemas.settings import SettingsResponse
from app.services.settings import env_file_path, get_app_settings, get_llm_base_url, get_llm_default_model, get_llm_provider
from app.services.sprite import SpriteError, SpriteService

router = APIRouter(prefix="/api", tags=["api"])


def get_sprite_service() -> SpriteService:
    return SpriteService()


@router.post("/asset-spec", response_model=AssetSpec)
async def create_asset_spec(payload: AssetSpecRequest, service: SpriteService = Depends(get_sprite_service)) -> AssetSpec:
    try:
        return await service.create_asset_spec(payload)
    except SpriteError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/generation-prompt", response_model=GenerationPromptResponse)
def generation_prompt(payload: GenerationPromptRequest, service: SpriteService = Depends(get_sprite_service)) -> GenerationPromptResponse:
    return service.create_generation_prompt(payload.asset_spec)


@router.post("/processing-plan", response_model=ProcessingPlanResponse)
def processing_plan(payload: ProcessingPlanRequest, service: SpriteService = Depends(get_sprite_service)) -> ProcessingPlanResponse:
    return service.create_processing_plan(payload.asset_spec)


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
        llm_base_url=get_llm_base_url(provider=provider),
        env_file=env_file_path(),
        app_log_level=app_settings.log_level,
    )
