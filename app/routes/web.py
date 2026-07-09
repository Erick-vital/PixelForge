from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.schemas.sprite import AssetSpecRequest
from app.services.settings import env_file_path, get_app_settings, get_llm_base_url, get_llm_default_model, get_llm_provider
from app.services.sprite import SpriteError, SpriteService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="app/templates")


def get_sprite_service() -> SpriteService:
    return SpriteService()


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="pages/home.html")


@router.get("/sprite", response_class=HTMLResponse)
def sprite_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="pages/sprite.html")


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


@router.post("/ui/sprite/spec", response_class=HTMLResponse)
async def run_sprite_spec_ui(
    request: Request,
    prompt: str = Form(...),
    service: SpriteService = Depends(get_sprite_service),
) -> HTMLResponse:
    logger.info("sprite ui request started", extra={"prompt_chars": len(prompt)})
    try:
        asset_spec = await service.create_asset_spec(AssetSpecRequest(prompt=prompt))
        generation_prompt = service.create_generation_prompt(asset_spec)
        processing_plan = service.create_processing_plan(asset_spec)
    except (ValueError, SpriteError) as exc:
        logger.warning("sprite ui request failed", extra={"error": str(exc)})
        return templates.TemplateResponse(request=request, name="partials/error.html", context={"error": str(exc)}, status_code=400)

    logger.info(
        "sprite ui request completed",
        extra={"asset_type": asset_spec.asset_type, "subject": asset_spec.subject, "width": asset_spec.size.width, "height": asset_spec.size.height},
    )
    return templates.TemplateResponse(
        request=request,
        name="partials/sprite_result.html",
        context={
            "prompt": prompt,
            "asset_spec": asset_spec,
            "asset_spec_json": asset_spec.model_dump(mode="json"),
            "generation_prompt": generation_prompt,
            "generation_prompt_json": generation_prompt.model_dump(mode="json"),
            "processing_plan": processing_plan,
            "processing_plan_json": processing_plan.model_dump(mode="json"),
        },
    )
