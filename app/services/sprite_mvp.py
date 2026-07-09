from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from PIL import Image
from pydantic import ValidationError

from app.schemas.sprite import (
    AssetSpec,
    AssetSpecRequest,
    GenerationPromptResponse,
    PaletteSpec,
    ProcessingPlanResponse,
    ProcessingStep,
    ShapeSpec,
    SpriteSize,
    TechnicalConstraints,
)
from app.services.llm_generation import LlmGenerationService

logger = logging.getLogger(__name__)


class SpriteMvpError(ValueError):
    pass


@dataclass
class SpriteMvpService:
    llm_service: LlmGenerationService | None = None

    async def create_asset_spec(self, request: AssetSpecRequest) -> AssetSpec:
        logger.info(
            "sprite asset spec generation started",
            extra={"prompt_chars": len(request.prompt), "use_llm": request.use_llm},
        )
        if request.use_llm:
            spec = await self._create_asset_spec_with_llm(request)
        else:
            spec = create_asset_spec_from_prompt(request.prompt)
        logger.info(
            "sprite asset spec generation completed",
            extra={"asset_type": spec.asset_type, "subject": spec.subject, "width": spec.size.width, "height": spec.size.height},
        )
        return spec

    async def _create_asset_spec_with_llm(self, request: AssetSpecRequest) -> AssetSpec:
        llm = self.llm_service or LlmGenerationService()
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
            raise SpriteMvpError(f"LLM did not return a valid Asset Spec JSON: {exc}") from exc


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
    prompt_parts.extend([
        "transparent background",
        "readable silhouette",
        "game-ready asset",
    ])
    return GenerationPromptResponse(
        prompt=", ".join(part for part in prompt_parts if part),
        negative_prompt="blurry, realistic, smooth gradients, complex background, oversized details, text, watermark, low readability",
    )


def create_processing_plan(asset_spec: AssetSpec) -> ProcessingPlanResponse:
    size = f"{asset_spec.size.width}x{asset_spec.size.height}"
    return ProcessingPlanResponse(
        steps=[
            ProcessingStep(name="canvas_setup", instruction=f"Create a {size} transparent canvas."),
            ProcessingStep(
                name="sprite_positioning",
                instruction=f"Center the {asset_spec.subject} sprite with 4px margin around the bounding box when possible.",
            ),
            ProcessingStep(name="pixel_art_resize", instruction="Use nearest-neighbor scaling only; never bicubic or smooth resampling."),
            ProcessingStep(name="palette_limit", instruction="Reduce color count to 16-24 colors while preserving the main palette and shadow readability."),
            ProcessingStep(name="export", instruction="Export PNG with transparent background."),
        ]
    )


def process_sprite_image(image_bytes: bytes, asset_spec: AssetSpec) -> tuple[bytes, dict[str, Any]]:
    logger.info(
        "sprite image processing started",
        extra={"input_bytes": len(image_bytes), "target_width": asset_spec.size.width, "target_height": asset_spec.size.height},
    )
    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGBA")
    except Exception as exc:  # Pillow raises multiple exception types for invalid images.
        raise SpriteMvpError(f"Invalid image upload: {exc}") from exc

    bbox = image.getbbox()
    if bbox is not None:
        image = image.crop(bbox)

    target_width = asset_spec.size.width
    target_height = asset_spec.size.height
    margin = 4 if min(target_width, target_height) >= 32 else 0
    max_width = max(1, target_width - margin * 2)
    max_height = max(1, target_height - margin * 2)
    scale = min(max_width / image.width, max_height / image.height) if image.width and image.height else 1
    new_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    resized = image.resize(new_size, Image.Resampling.NEAREST)

    canvas = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    x = (target_width - resized.width) // 2
    y = (target_height - resized.height) // 2
    canvas.alpha_composite(resized, (x, y))

    output = BytesIO()
    canvas.save(output, format="PNG")
    png = output.getvalue()
    report = {
        "width": target_width,
        "height": target_height,
        "mode": canvas.mode,
        "transparent": _has_transparency(canvas),
        "non_empty": canvas.getbbox() is not None,
        "notes": ["resized with nearest-neighbor", "centered on transparent canvas", "exported as PNG"],
    }
    logger.info("sprite image processing completed", extra={"output_bytes": len(png), **report})
    return png, report


ASSET_SPEC_SYSTEM_PROMPT = """You convert user game-asset requests into strict JSON for a small MVP.
Return only a JSON object with these keys:
asset_type: one of enemy, prop, icon
subject: concise English subject
game_view: one of side-view, top-down 3/4, icon/front
style: pixel art style phrase
size: {width: 32|64|128, height: 32|64|128}
palette: {main: string[], shadows: string[], accent: string[]}
shape: {silhouette: string, proportions: object}
technical_constraints: {transparent_background: true, pixel_art: true, readable_at_small_size: true}
Scope limits: only 2D pixel-art enemy, prop, or icon assets.
"""


def _detect_size(text: str) -> tuple[int, int]:
    match = re.search(r"\b(32|64|128)\s*x\s*(32|64|128)\b", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    single = re.search(r"\b(32|64|128)\b", text)
    if single:
        value = int(single.group(1))
        return value, value
    return 64, 64


def _detect_asset_type(text: str) -> str:
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


def _detect_view(text: str) -> str:
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


def _has_transparency(image: Image.Image) -> bool:
    alpha = image.getchannel("A")
    return alpha.getextrema()[0] < 255
