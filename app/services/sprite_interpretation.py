from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from app.schemas.sprite import (
    AllowedAssetType,
    AllowedView,
    AssetSpec,
    AssetSpecRequest,
    GenerationPromptResponse,
    PaletteSpec,
    ProcessingPlanResponse,
    ProcessingStep,
    PromptGuidance,
    ProcessingProfile,
    ShapeSpec,
    SpriteSize,
    TechnicalConstraints,
)
from app.services.llm_generation import LlmGenerationService

logger = logging.getLogger(__name__)


ASSET_SPEC_SYSTEM_PROMPT = """You convert user game-asset requests into strict JSON for the sprite pipeline.
Return only a JSON object with these keys:
asset_type: one of enemy, prop, icon
subject: concise English subject
game_view: one of side-view, top-down 3/4, icon/front
style: pixel art style phrase
size: {width: 32|64|128, height: 32|64|128}
palette: {main: string[], shadows: string[], accent: string[]}
shape: {silhouette: string, proportions: object}
technical_constraints: {transparent_background: true, pixel_art: true, readable_at_small_size: true}
prompt_guidance: {target_prompt_tone: string, include_size: boolean, include_style: boolean, include_negative_prompt: boolean, normalize_subject_to_english: boolean}
processing_profile: {resize_mode: nearest-neighbor, palette_max_colors: integer, center_sprite: boolean, transparent_background: boolean, export_format: png}
Scope limits: only 2D pixel-art enemy, prop, or icon assets.
"""


class SpriteSpecError(ValueError):
    pass


async def create_asset_spec_from_request(request: AssetSpecRequest, llm_service: LlmGenerationService | None = None) -> AssetSpec:
    if request.use_llm:
        llm = llm_service or LlmGenerationService()
        result = await llm.generate_text(
            system_prompt=ASSET_SPEC_SYSTEM_PROMPT,
            prompt=request.prompt,
            provider=request.provider,
            model=request.model,
            base_url=request.base_url,
            temperature=0.1,
            max_tokens=1200,
        )
        try:
            data = _extract_json_object(result.text)
            return AssetSpec.model_validate(data)
        except (ValueError, ValidationError) as exc:
            logger.warning("llm asset spec parse failed", extra={"error": str(exc)})
            raise SpriteSpecError(f"LLM did not return a valid Asset Spec JSON: {exc}") from exc
    return create_asset_spec_from_prompt(request.prompt)


def create_asset_spec_from_prompt(prompt: str) -> AssetSpec:
    normalized = _normalize(prompt)
    width, height = _detect_size(normalized)
    asset_type = _detect_asset_type(normalized)
    subject = _detect_subject(normalized)
    game_view = _detect_view(normalized)
    style = _detect_style(normalized, subject)
    palette = _detect_palette(normalized, subject)
    shape = _detect_shape(subject)
    return AssetSpec(
        asset_type=asset_type,
        subject=subject,
        game_view=game_view,
        style=style,
        size=SpriteSize(width=width, height=height),
        palette=palette,
        shape=shape,
        technical_constraints=TechnicalConstraints(
            transparent_background=True,
            pixel_art="pixel" in normalized,
            readable_at_small_size=True,
        ),
        prompt_guidance=PromptGuidance(),
        processing_profile=ProcessingProfile(),
    )


def create_generation_prompt(asset_spec: AssetSpec) -> GenerationPromptResponse:
    size = f"{asset_spec.size.width}x{asset_spec.size.height}"
    colors = _palette_words(asset_spec.palette)
    silhouette = asset_spec.shape.silhouette
    prompt_parts = [
        f"{size} pixel art sprite",
        f"{asset_spec.subject} {asset_spec.asset_type}",
        f"{asset_spec.game_view} view",
        asset_spec.style,
        silhouette,
    ]
    if colors:
        prompt_parts.append(f"palette: {colors}")
    if asset_spec.prompt_guidance.include_size:
        prompt_parts.append("transparent background")
    if asset_spec.prompt_guidance.include_style:
        prompt_parts.append("readable silhouette")
    prompt_parts.append("game-ready asset")
    return GenerationPromptResponse(
        prompt=", ".join(part for part in prompt_parts if part),
        negative_prompt="blurry, realistic, smooth gradients, complex background, oversized details, text, watermark, low readability",
    )


def create_processing_plan(asset_spec: AssetSpec) -> ProcessingPlanResponse:
    size = f"{asset_spec.size.width}x{asset_spec.size.height}"
    profile = asset_spec.processing_profile
    return ProcessingPlanResponse(
        steps=[
            ProcessingStep(name="canvas_setup", instruction=f"Create a {size} transparent canvas."),
            ProcessingStep(
                name="sprite_positioning",
                instruction="Center the sprite within the canvas and keep visual mass balanced.",
            ),
            ProcessingStep(name="pixel_art_resize", instruction=f"Use {profile.resize_mode} scaling only; never bicubic or smooth resampling."),
            ProcessingStep(
                name="palette_limit",
                instruction=f"Reduce color count to {profile.palette_max_colors} colors while preserving the main palette and shadow readability.",
            ),
            ProcessingStep(name="export", instruction=f"Export {profile.export_format.upper()} with transparent background."),
        ]
    )


def _detect_size(text: str) -> tuple[int, int]:
    match = re.search(r"\b(32|64|128)\s*x\s*(32|64|128)\b", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    single = re.search(r"\b(32|64|128)\b", text)
    if single:
        value = int(single.group(1))
        return value, value
    return 64, 64


def _detect_asset_type(text: str) -> AllowedAssetType:
    if any(word in text for word in ["enemy", "enemigo", "monster", "monstruo", "boss"]):
        return "enemy"
    if any(word in text for word in ["icon", "ícono", "icono", "ui", "item"]):
        return "icon"
    return "prop"


def _detect_subject(text: str) -> str:
    if "dragon" in text or "dragón" in text or "dragon" in _strip_accents(text):
        if any(word in text for word in ["baby", "bebé", "bebe", "small", "pequeño", "pequeno"]):
            return "baby dragon"
        return "dragon"
    if "chest" in text or "cofre" in text:
        return "treasure chest"
    if "potion" in text or "poción" in text or "pocion" in text:
        return "potion"
    if "sword" in text or "espada" in text:
        return "sword"
    return "game asset"


def _detect_view(text: str) -> AllowedView:
    if "top-down" in text or "top down" in text or "rpg" in text:
        return "top-down 3/4"
    if "side" in text or "plataforma" in text or "platform" in text:
        return "side-view"
    return "icon/front"


def _detect_style(text: str, subject: str) -> str:
    fantasy_subjects = {"baby dragon", "dragon", "treasure chest", "potion", "sword"}
    if "pixel" in text and subject in fantasy_subjects:
        return "pixel art fantasy"
    if "pixel" in text:
        return "pixel art"
    return "pixel art"


def _detect_palette(text: str, subject: str) -> PaletteSpec:
    if "dragon" in subject:
        return PaletteSpec(main=["orange", "dark red", "gold"], shadows=["purple", "dark blue"], accent=["yellow glow"])
    if subject == "treasure chest":
        return PaletteSpec(main=["brown", "gold"], shadows=["dark brown"], accent=["bright gold"])
    if subject == "potion":
        return PaletteSpec(main=["blue", "cyan"], shadows=["dark blue"], accent=["white shine"])
    return PaletteSpec(main=["limited readable colors"], shadows=["dark outline"], accent=["small highlight"])


def _detect_shape(subject: str) -> ShapeSpec:
    if "dragon" in subject:
        return ShapeSpec(
            silhouette="small compact dragon with large head, tiny wings, curled tail",
            proportions={"head": "large", "body": "small", "wings": "small", "tail": "curled"},
        )
    return ShapeSpec(silhouette=f"clear compact {subject} silhouette", proportions={})


def _palette_words(palette: PaletteSpec) -> str:
    return ", ".join([*palette.main, *palette.shadows, *palette.accent])


def _normalize(text: str) -> str:
    return text.strip().lower()


def _strip_accents(text: str) -> str:
    return text.translate(str.maketrans({"ó": "o", "é": "e", "í": "i", "á": "a", "ú": "u", "ñ": "n"}))


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).removesuffix("```").strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found")
    data = json.loads(stripped[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("top-level JSON is not an object")
    return data
