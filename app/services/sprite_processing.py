from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from typing import Any, cast

from PIL import Image

from app.schemas.sprite import AssetSpec

logger = logging.getLogger(__name__)


class SpriteProcessingError(ValueError):
    pass


@dataclass(frozen=True)
class SpriteProcessingResult:
    png_bytes: bytes
    report: dict[str, Any]


def process_sprite_image(image_bytes: bytes, asset_spec: AssetSpec) -> SpriteProcessingResult:
    logger.info(
        "sprite image processing started",
        extra={
            "input_bytes": len(image_bytes),
            "target_width": asset_spec.size.width,
            "target_height": asset_spec.size.height,
        },
    )
    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGBA")
    except Exception as exc:  # Pillow raises multiple exception types for invalid images.
        raise SpriteProcessingError(f"Invalid image upload: {exc}") from exc

    bbox = image.getbbox()
    if bbox is not None:
        image = image.crop(bbox)

    target_width = asset_spec.size.width
    target_height = asset_spec.size.height
    profile = asset_spec.processing_profile
    margin = 4 if profile.center_sprite and min(target_width, target_height) >= 32 else 0
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
    return SpriteProcessingResult(png_bytes=png, report=report)


def _has_transparency(image: Image.Image) -> bool:
    alpha = image.getchannel("A")
    left, _right = cast(tuple[int, int], alpha.getextrema())
    return left < 255
