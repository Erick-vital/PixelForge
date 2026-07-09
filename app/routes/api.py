from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from app.routes.helpers import WorkflowHttpError, run_workflow_for_request
from app.schemas.sprite import (
    AssetSpec,
    AssetSpecRequest,
    GenerationPromptRequest,
    GenerationPromptResponse,
    ProcessingPlanRequest,
    ProcessingPlanResponse,
)
from app.schemas.workflow import SettingsResponse, WorkflowRunRequest, WorkflowRunResponse
from app.services.settings import env_file_path, get_app_settings, get_llm_base_url, get_llm_default_model, get_llm_provider
from app.services.sprite_mvp import SpriteMvpError, SpriteMvpService, create_generation_prompt, create_processing_plan, process_sprite_image
from app.services.workflow_service import WorkflowService, build_workflow_service_from_env

router = APIRouter(prefix="/api", tags=["api"] )


def get_workflow_service() -> WorkflowService:
    return build_workflow_service_from_env()


def get_sprite_mvp_service() -> SpriteMvpService:
    return SpriteMvpService()


@router.post("/asset-spec", response_model=AssetSpec)
async def create_asset_spec(payload: AssetSpecRequest, service: SpriteMvpService = Depends(get_sprite_mvp_service)) -> AssetSpec:
    try:
        return await service.create_asset_spec(payload)
    except SpriteMvpError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/generation-prompt", response_model=GenerationPromptResponse)
def generation_prompt(payload: GenerationPromptRequest) -> GenerationPromptResponse:
    return create_generation_prompt(payload.asset_spec)


@router.post("/processing-plan", response_model=ProcessingPlanResponse)
def processing_plan(payload: ProcessingPlanRequest) -> ProcessingPlanResponse:
    return create_processing_plan(payload.asset_spec)


@router.post("/process-sprite")
async def process_sprite(image: UploadFile = File(...), asset_spec_json: str = Form(...)) -> Response:
    try:
        asset_spec = AssetSpec.model_validate(json.loads(asset_spec_json))
        png, report = process_sprite_image(await image.read(), asset_spec)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="asset_spec_json must be valid JSON") from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except SpriteMvpError as exc:
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


@router.post("/workflow/run", response_model=WorkflowRunResponse)
async def run_workflow(payload: WorkflowRunRequest, service: WorkflowService = Depends(get_workflow_service)) -> WorkflowRunResponse:
    try:
        result = await run_workflow_for_request(service, payload, source="api")
    except WorkflowHttpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return WorkflowRunResponse.model_validate(result.to_response_dict())


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
