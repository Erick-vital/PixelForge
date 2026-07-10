from __future__ import annotations

import json
import logging
from base64 import b64encode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.schemas.sprite import AssetSpecRequest
from app.services.settings import (
    env_file_path,
    get_app_settings,
    get_llm_base_url,
    get_llm_default_model,
    get_llm_provider,
)
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
        asset_spec, artifact = await service.create_asset_spec(AssetSpecRequest(prompt=prompt))
        blueprint, _artifact = service.create_sprite_blueprint(artifact.artifact_id, seed=0)
    except ValueError as exc:  # includes SpriteError and pydantic ValidationError
        logger.warning("sprite ui request failed", extra={"error": str(exc)})
        return templates.TemplateResponse(
            request=request, name="partials/error.html", context={"error": str(exc)}, status_code=400
        )

    logger.info(
        "sprite ui request completed",
        extra={
            "artifact_id": artifact.artifact_id,
            "asset_type": asset_spec.asset_type,
            "subject": asset_spec.subject,
            "width": asset_spec.size.width,
            "height": asset_spec.size.height,
        },
    )
    return templates.TemplateResponse(
        request=request,
        name="partials/sprite_result.html",
        context={
            "prompt": prompt,
            "artifact_id": artifact.artifact_id,
            "artifact_dir": str(artifact.artifact_dir),
            "asset_spec": asset_spec,
            "asset_spec_json": asset_spec.model_dump(mode="json"),
            "asset_spec_json_text": json.dumps(asset_spec.model_dump(mode="json"), ensure_ascii=False),
            "blueprint": blueprint,
            "blueprint_json": blueprint.model_dump(mode="json"),
            "blueprint_json_text": json.dumps(blueprint.model_dump(mode="json"), ensure_ascii=False),
        },
    )


@router.post("/ui/sprite/render", response_class=HTMLResponse)
def render_sprite_ui(
    request: Request,
    artifact_id: str = Form(...),
    seed: int = Form(default=0),
    service: SpriteService = Depends(get_sprite_service),
) -> HTMLResponse:
    logger.info("sprite render ui request started", extra={"seed": seed, "artifact_id": artifact_id})
    try:
        png, report = service.render_sprite(artifact_id, seed=seed)
    except ValueError as exc:  # includes SpriteError and pydantic ValidationError
        logger.warning("sprite render ui request failed", extra={"error": str(exc)})
        return templates.TemplateResponse(
            request=request, name="partials/error.html", context={"error": str(exc)}, status_code=400
        )

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
    artifact_id: str = Form(...),
    seed: int = Form(default=0),
    service: SpriteService = Depends(get_sprite_service),
) -> HTMLResponse:
    logger.info(
        "sprite blueprint render ui request started",
        extra={"seed": seed, "artifact_id": artifact_id},
    )
    try:
        png, report = service.render_blueprint(artifact_id, seed=seed)
    except ValueError as exc:  # includes SpriteError and pydantic ValidationError
        logger.warning("sprite blueprint render ui request failed", extra={"error": str(exc)})
        return templates.TemplateResponse(
            request=request, name="partials/error.html", context={"error": str(exc)}, status_code=400
        )

    encoded_png = b64encode(png).decode("ascii")
    logger.info("sprite blueprint render ui request completed", extra={"recipe": report["recipe"], "seed": report["seed"]})
    return templates.TemplateResponse(
        request=request,
        name="partials/sprite_preview.html",
        context={"png_data_uri": f"data:image/png;base64,{encoded_png}", "report": report},
    )
