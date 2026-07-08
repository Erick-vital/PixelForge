from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.routes.helpers import WorkflowHttpError, run_workflow_for_request
from app.schemas.workflow import SettingsResponse, WorkflowRunRequest, WorkflowRunResponse
from app.services.settings import env_file_path, get_app_settings, get_llm_base_url, get_llm_default_model, get_llm_provider
from app.services.workflow_service import WorkflowService, build_workflow_service_from_env

router = APIRouter(prefix="/api", tags=["api"] )


def get_workflow_service() -> WorkflowService:
    return build_workflow_service_from_env()


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
