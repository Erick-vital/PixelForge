from __future__ import annotations

import json
import logging
from base64 import b64encode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.schemas.sprite import AssetSpec, AssetSpecRequest, SpriteBlueprint
from app.services.settings import env_file_path, get_app_settings, get_llm_base_url, get_llm_default_model, get_llm_provider
from app.services.sprite import SpriteService

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
        "base_url": get_llm_base_url(provider=provider, settings=settings),
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
        blueprint = service.create_sprite_blueprint(asset_spec, seed=0)
    except ValueError as exc:  # includes SpriteError and pydantic ValidationError
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
            "asset_spec_json_text": json.dumps(asset_spec.model_dump(mode="json"), ensure_ascii=False),
            "generation_prompt": generation_prompt,
            "generation_prompt_json": generation_prompt.model_dump(mode="json"),
            "processing_plan": processing_plan,
            "processing_plan_json": processing_plan.model_dump(mode="json"),
            "blueprint": blueprint,
            "blueprint_json": blueprint.model_dump(mode="json"),
            "blueprint_json_text": json.dumps(blueprint.model_dump(mode="json"), ensure_ascii=False),
        },
    )


@router.post("/ui/sprite/render", response_class=HTMLResponse)
def render_sprite_ui(
    request: Request,
    asset_spec_json: str = Form(...),
    seed: int = Form(default=0),
    service: SpriteService = Depends(get_sprite_service),
) -> HTMLResponse:
    logger.info("sprite render ui request started", extra={"seed": seed, "asset_spec_chars": len(asset_spec_json)})
    try:
        asset_spec = AssetSpec.model_validate(json.loads(asset_spec_json))
        png, report = service.render_sprite(asset_spec, seed=seed)
    except ValueError as exc:  # includes JSONDecodeError, SpriteError, and pydantic ValidationError
        logger.warning("sprite render ui request failed", extra={"error": str(exc)})
        return templates.TemplateResponse(request=request, name="partials/error.html", context={"error": str(exc)}, status_code=400)

    encoded_png = b64encode(png).decode("ascii")
    logger.info("sprite render ui request completed", extra={"recipe": report["recipe"], "seed": report["seed"]})
    return templates.TemplateResponse(
        request=request,
        name="partials/sprite_preview.html",
        context={"png_data_uri": f"data:image/png;base64,{encoded_png}", "report": report},
    )


@router.post("/ui/sprite/render-blueprint", response_class=HTMLResponse)
def render_blueprint_ui(
    request: Request,
    blueprint_json: str = Form(...),
    width: int = Form(...),
    height: int = Form(...),
    seed: int = Form(default=0),
    service: SpriteService = Depends(get_sprite_service),
) -> HTMLResponse:
    logger.info("sprite blueprint render ui request started", extra={"seed": seed, "blueprint_chars": len(blueprint_json), "width": width, "height": height})
    try:
        blueprint = SpriteBlueprint.model_validate(json.loads(blueprint_json))
        png, report = service.render_blueprint(blueprint, width=width, height=height, seed=seed)
    except ValueError as exc:  # includes JSONDecodeError, SpriteError, and pydantic ValidationError
        logger.warning("sprite blueprint render ui request failed", extra={"error": str(exc)})
        return templates.TemplateResponse(request=request, name="partials/error.html", context={"error": str(exc)}, status_code=400)

    encoded_png = b64encode(png).decode("ascii")
    logger.info("sprite blueprint render ui request completed", extra={"recipe": report["recipe"], "seed": report["seed"]})
    return templates.TemplateResponse(
        request=request,
        name="partials/sprite_preview.html",
        context={"png_data_uri": f"data:image/png;base64,{encoded_png}", "report": report},
    )
