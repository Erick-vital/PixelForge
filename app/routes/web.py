from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.routes.helpers import WorkflowHttpError, run_workflow_for_request
from app.schemas.workflow import WorkflowRunRequest
from app.services.settings import env_file_path, get_app_settings, get_llm_base_url, get_llm_default_model, get_llm_provider
from app.services.workflow_service import WorkflowService, build_workflow_service_from_env

router = APIRouter(tags=["web"] )
templates = Jinja2Templates(directory="app/templates")


def get_workflow_service() -> WorkflowService:
    return build_workflow_service_from_env()


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="pages/home.html")


@router.get("/workflow", response_class=HTMLResponse)
def workflow_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="pages/workflow.html")


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request) -> HTMLResponse:
    settings = get_app_settings()
    provider = get_llm_provider(settings=settings)
    context = {
        "settings": settings,
        "provider": provider,
        "default_model": get_llm_default_model(provider),
        "base_url": get_llm_base_url(provider=provider),
        "env_file": env_file_path(),
    }
    return templates.TemplateResponse(request=request, name="pages/settings.html", context=context)


@router.get("/llm", response_class=HTMLResponse)
def llm_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="pages/llm.html")


@router.post("/ui/workflow/run", response_class=HTMLResponse)
async def run_workflow_ui(
    request: Request,
    title: str = Form(...),
    input_text: str = Form(...),
    use_llm: bool = Form(default=False),
    provider: str = Form(default=""),
    model: str = Form(default=""),
    base_url: str = Form(default=""),
    service: WorkflowService = Depends(get_workflow_service),
) -> HTMLResponse:
    try:
        payload = WorkflowRunRequest(
            title=title,
            input_text=input_text,
            use_llm=use_llm,
            provider=provider.strip() or None,
            model=model.strip() or None,
            base_url=base_url.strip() or None,
        )
        result = await run_workflow_for_request(service, payload, source="ui")
    except ValueError as exc:
        return templates.TemplateResponse(request=request, name="partials/error.html", context={"error": str(exc)}, status_code=400)
    except WorkflowHttpError as exc:
        return templates.TemplateResponse(request=request, name="partials/error.html", context={"error": exc.detail}, status_code=exc.status_code)
    return templates.TemplateResponse(request=request, name="partials/result.html", context={"result": result})
