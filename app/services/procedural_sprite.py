from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from typing import Any, cast

import numpy as np
from PIL import Image, ImageDraw

from app.schemas.sprite import AssetSpec, SpriteBlueprint, SpritePrimitive

logger = logging.getLogger(__name__)

# Blueprints are authored in a fixed 64x64 coordinate space; render_blueprint
# scales primitives to the requested canvas size.
BASE_CANVAS_SIZE = 64


class ProceduralSpriteError(ValueError):
    pass


@dataclass(frozen=True)
class ProceduralSpriteResult:
    png_bytes: bytes
    report: dict[str, Any]


def render_procedural_sprite(asset_spec: AssetSpec, *, seed: int = 0) -> ProceduralSpriteResult:
    blueprint = build_sprite_blueprint(asset_spec, seed=seed)
    return render_blueprint(
        blueprint,
        width=asset_spec.size.width,
        height=asset_spec.size.height,
        seed=seed,
        max_colors=asset_spec.processing_profile.palette_max_colors,
    )


def build_sprite_blueprint(asset_spec: AssetSpec, *, seed: int = 0) -> SpriteBlueprint:
    rng = np.random.default_rng(seed)
    recipe = _recipe_for(asset_spec.subject)
    palette = _palette_for(asset_spec)
    logger.info(
        "procedural sprite blueprint built",
        extra={
            "subject": asset_spec.subject,
            "recipe": recipe,
            "seed": seed,
            "width": asset_spec.size.width,
            "height": asset_spec.size.height,
        },
    )
    if recipe == "baby_dragon":
        return _blueprint_for_baby_dragon(asset_spec.subject, palette, rng)
    if recipe == "potion":
        return _blueprint_for_potion(asset_spec.subject, palette, rng)
    if recipe == "sword":
        return _blueprint_for_sword(asset_spec.subject, palette, rng)
    return _blueprint_for_generic_prop(asset_spec.subject, palette, rng)


def _blueprint_for_baby_dragon(subject: str, palette: dict[str, str], rng: np.random.Generator) -> SpriteBlueprint:
    cx = 32 + int(rng.integers(-1, 2))
    cy = 34
    primitives = [
        _poly([(cx - 13, cy - 5), (cx - 27, cy - 15), (cx - 21, cy + 5), (cx - 12, cy + 3)], "outline"),
        _poly([(cx + 13, cy - 5), (cx + 27, cy - 15), (cx + 21, cy + 5), (cx + 12, cy + 3)], "outline"),
        _poly([(cx - 14, cy - 5), (cx - 24, cy - 12), (cx - 20, cy + 2), (cx - 12, cy + 1)], "shadow"),
        _poly([(cx + 14, cy - 5), (cx + 24, cy - 12), (cx + 20, cy + 2), (cx + 12, cy + 1)], "shadow"),
        _line([(cx + 8, cy + 10), (cx + 18, cy + 16), (cx + 22, cy + 9)], "outline", width=2),
        _line([(cx + 8, cy + 9), (cx + 17, cy + 14), (cx + 20, cy + 9)], "base", width=1),
        _ellipse((cx - 13, cy - 7, cx + 13, cy + 15), "outline"),
        _ellipse((cx - 11, cy - 5, cx + 11, cy + 13), "base"),
        _ellipse((cx - 9, cy + 2, cx + 9, cy + 13), "highlight"),
        _ellipse((cx - 15, cy - 22, cx + 15, cy + 6), "outline"),
        _ellipse((cx - 13, cy - 20, cx + 13, cy + 4), "base"),
        _poly([(cx - 8, cy - 18), (cx - 4, cy - 28), (cx - 1, cy - 17)], "outline"),
        _poly([(cx + 8, cy - 18), (cx + 4, cy - 28), (cx + 1, cy - 17)], "outline"),
        _poly([(cx - 7, cy - 18), (cx - 4, cy - 25), (cx - 2, cy - 17)], "accent"),
        _poly([(cx + 7, cy - 18), (cx + 4, cy - 25), (cx + 2, cy - 17)], "accent"),
        _point(cx - 6, cy - 9, "outline", size=2),
        _point(cx + 6, cy - 9, "outline", size=2),
        _point(cx - 5, cy - 10, "accent", size=1),
        _point(cx + 7, cy - 10, "accent", size=1),
        _ellipse((cx - 9, cy + 12, cx - 3, cy + 18), "outline"),
        _ellipse((cx + 3, cy + 12, cx + 9, cy + 18), "outline"),
        _ellipse((cx - 8, cy + 12, cx - 4, cy + 16), "base"),
        _ellipse((cx + 4, cy + 12, cx + 8, cy + 16), "base"),
    ]
    return SpriteBlueprint(
        recipe="baby_dragon",
        subject=subject,
        palette=palette,
        primitives=primitives,
        notes=["procedural dragon recipe", "compact top-down readable silhouette"],
    )


def _blueprint_for_potion(subject: str, palette: dict[str, str], rng: np.random.Generator) -> SpriteBlueprint:
    cx = 32 + int(rng.integers(-1, 2))
    cy = 32 + int(rng.integers(-1, 2))
    primitives = [
        _ellipse((cx - 13, cy - 3, cx + 13, cy + 20), "outline"),
        _ellipse((cx - 11, cy - 1, cx + 11, cy + 18), "base"),
        _rectangle((cx - 6, cy - 17, cx + 6, cy - 2), "outline"),
        _rectangle((cx - 4, cy - 15, cx + 4, cy - 2), "highlight"),
        _rectangle((cx - 8, cy - 20, cx + 8, cy - 15), "outline"),
        _rectangle((cx - 6, cy - 19, cx + 6, cy - 16), "accent"),
        _poly([(cx - 9, cy + 8), (cx - 1, cy + 16), (cx - 11, cy + 16)], "shadow"),
        _point(cx + 5, cy + 4, "accent", size=2),
    ]
    return SpriteBlueprint(
        recipe="potion", subject=subject, palette=palette, primitives=primitives, notes=["procedural potion recipe"]
    )


def _blueprint_for_sword(subject: str, palette: dict[str, str], rng: np.random.Generator) -> SpriteBlueprint:
    # Horizontal jitter only: the blade-to-pommel span already covers cy-27..cy+31.
    cx = 32 + int(rng.integers(-1, 2))
    cy = 32
    primitives = [
        _poly([(cx, cy - 27), (cx + 7, cy + 2), (cx, cy + 11), (cx - 7, cy + 2)], "outline"),
        _poly([(cx, cy - 24), (cx + 4, cy + 1), (cx, cy + 8), (cx - 4, cy + 1)], "base"),
        _line([(cx, cy - 21), (cx, cy + 6)], "highlight", width=1),
        _rectangle((cx - 15, cy + 8, cx + 15, cy + 13), "outline"),
        _rectangle((cx - 12, cy + 9, cx + 12, cy + 11), "accent"),
        _rectangle((cx - 4, cy + 12, cx + 4, cy + 27), "outline"),
        _rectangle((cx - 2, cy + 13, cx + 2, cy + 24), "shadow"),
        _ellipse((cx - 5, cy + 23, cx + 5, cy + 31), "outline"),
        _ellipse((cx - 3, cy + 24, cx + 3, cy + 29), "accent"),
    ]
    return SpriteBlueprint(
        recipe="sword", subject=subject, palette=palette, primitives=primitives, notes=["procedural sword recipe"]
    )


def render_blueprint(
    blueprint: SpriteBlueprint, *, width: int, height: int, seed: int = 0, max_colors: int = 24
) -> ProceduralSpriteResult:
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    palette = {name: _rgba(hex_color) for name, hex_color in blueprint.palette.items()}

    logger.info(
        "procedural sprite render started",
        extra={
            "recipe": blueprint.recipe,
            "subject": blueprint.subject,
            "width": width,
            "height": height,
            "seed": seed,
            "primitive_count": len(blueprint.primitives),
        },
    )
    scale_x = width / BASE_CANVAS_SIZE
    scale_y = height / BASE_CANVAS_SIZE
    for primitive in blueprint.primitives:
        _render_primitive(draw, _scale_primitive(primitive, scale_x, scale_y), palette)

    canvas = _limit_palette(canvas, max_colors=max_colors)
    png = _to_png(canvas)
    report = _build_report(canvas, recipe=blueprint.recipe, seed=seed, primitive_count=len(blueprint.primitives))
    logger.info("procedural sprite render completed", extra={"output_bytes": len(png), **report})
    return ProceduralSpriteResult(png_bytes=png, report=report)


def _blueprint_for_generic_prop(subject: str, palette: dict[str, str], rng: np.random.Generator) -> SpriteBlueprint:
    cx = 32 + int(rng.integers(-2, 3))
    cy = 32 + int(rng.integers(-2, 3))
    primitives = [
        _ellipse((cx - 15, cy - 15, cx + 15, cy + 15), "outline"),
        _ellipse((cx - 12, cy - 12, cx + 12, cy + 12), "base"),
        _ellipse((cx - 8, cy - 8, cx + 4, cy + 4), "highlight"),
    ]
    return SpriteBlueprint(
        recipe="generic_prop",
        subject=subject,
        palette=palette,
        primitives=primitives,
        notes=["generic procedural prop recipe"],
    )


def _scale_primitive(primitive: SpritePrimitive, scale_x: float, scale_y: float) -> SpritePrimitive:
    if scale_x == 1 and scale_y == 1:
        return primitive
    bbox = None
    if primitive.bbox is not None:
        x0, y0, x1, y1 = primitive.bbox
        bbox = (round(x0 * scale_x), round(y0 * scale_y), round(x1 * scale_x), round(y1 * scale_y))
    points = [(round(x * scale_x), round(y * scale_y)) for x, y in primitive.points]
    stroke_scale = min(scale_x, scale_y)
    width = max(1, round(primitive.width * stroke_scale)) if primitive.width is not None else None
    size = max(1, round(primitive.size * stroke_scale)) if primitive.size is not None else None
    return SpritePrimitive(op=primitive.op, fill=primitive.fill, bbox=bbox, points=points, width=width, size=size)


def _render_primitive(
    draw: ImageDraw.ImageDraw, primitive: SpritePrimitive, palette: dict[str, tuple[int, int, int, int]]
) -> None:
    fill = _resolve_fill(primitive.fill, palette)
    if primitive.op == "ellipse":
        if primitive.bbox is None:
            raise ProceduralSpriteError("ellipse primitive requires bbox")
        draw.ellipse(primitive.bbox, fill=fill)
        return
    if primitive.op == "rectangle":
        if primitive.bbox is None:
            raise ProceduralSpriteError("rectangle primitive requires bbox")
        draw.rectangle(primitive.bbox, fill=fill)
        return
    if primitive.op == "polygon":
        if not primitive.points:
            raise ProceduralSpriteError("polygon primitive requires points")
        draw.polygon(primitive.points, fill=fill)
        return
    if primitive.op == "line":
        if not primitive.points:
            raise ProceduralSpriteError("line primitive requires points")
        draw.line(primitive.points, fill=fill, width=primitive.width or 1, joint="curve")
        return
    if primitive.op == "point":
        if not primitive.points:
            raise ProceduralSpriteError("point primitive requires at least one point")
        x, y = primitive.points[0]
        size = primitive.size or 1
        draw.rectangle((x, y, x + size - 1, y + size - 1), fill=fill)
        return
    raise ProceduralSpriteError(f"Unsupported primitive op: {primitive.op}")


def _recipe_for(subject: str) -> str:
    normalized = subject.lower().replace(" ", "_")
    if "dragon" in normalized:
        return "baby_dragon"
    if "potion" in normalized:
        return "potion"
    if "sword" in normalized:
        return "sword"
    return "generic_prop"


def _palette_for(asset_spec: AssetSpec) -> dict[str, str]:
    subject = asset_spec.subject.lower()
    if "dragon" in subject:
        return {
            "outline": "#2a1520",
            "base": "#d55a22",
            "shadow": "#672c62",
            "highlight": "#f5a43b",
            "accent": "#ffd95a",
        }
    if "potion" in subject:
        return {
            "outline": "#1c1f3a",
            "base": "#277bd3",
            "shadow": "#17417a",
            "highlight": "#7fe8ff",
            "accent": "#ffffff",
        }
    if "sword" in subject:
        return {
            "outline": "#20222b",
            "base": "#b9c8d8",
            "shadow": "#55606f",
            "highlight": "#ffffff",
            "accent": "#d8a43d",
        }
    return {
        "outline": "#202020",
        "base": "#7a9b4f",
        "shadow": "#3d552c",
        "highlight": "#b5d178",
        "accent": "#fff18f",
    }


def _limit_palette(image: Image.Image, *, max_colors: int) -> Image.Image:
    if max_colors >= 256:
        return image
    alpha = image.getchannel("A")
    # Flatten transparent pixels onto the dominant opaque color so their RGB
    # (usually black) does not claim a palette slot or skew the median cut.
    flattened = Image.new("RGB", image.size, _dominant_opaque_color(image))
    flattened.paste(image.convert("RGB"), mask=alpha)
    quantized = flattened.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT).convert("RGBA")
    quantized.putalpha(alpha)
    return quantized


def _dominant_opaque_color(image: Image.Image) -> tuple[int, int, int]:
    colors = image.getcolors(maxcolors=image.width * image.height) or []
    opaque = [
        (count, cast(tuple[int, int, int, int], color))
        for count, color in colors
        if cast(tuple[int, int, int, int], color)[3] > 0
    ]
    if not opaque:
        return (0, 0, 0)
    _count, (red, green, blue, _alpha) = max(opaque)
    return (red, green, blue)


def _build_report(image: Image.Image, *, recipe: str, seed: int, primitive_count: int) -> dict[str, Any]:
    colors = image.getcolors(maxcolors=4096) or []
    opaque_colors = [
        cast(tuple[int, int, int, int], color)
        for _count, color in colors
        if cast(tuple[int, int, int, int], color)[3] > 0
    ]
    alpha = image.getchannel("A")
    min_alpha, _max_alpha = cast(tuple[int, int], alpha.getextrema())
    return {
        "width": image.width,
        "height": image.height,
        "mode": image.mode,
        "transparent": min_alpha < 255,
        "non_empty": image.getbbox() is not None,
        "color_count": len(set(opaque_colors)),
        "recipe": recipe,
        "seed": seed,
        "primitive_count": primitive_count,
        "notes": ["rendered procedurally", "limited palette", "transparent png"],
    }


def _to_png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _rgba(hex_color: str) -> tuple[int, int, int, int]:
    value = hex_color.removeprefix("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), 255)


def _resolve_fill(fill: str, palette: dict[str, tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    if fill in palette:
        return palette[fill]
    return _rgba(fill)


def _ellipse(bbox: tuple[int, int, int, int], fill: str) -> SpritePrimitive:
    return SpritePrimitive(op="ellipse", bbox=bbox, fill=fill)


def _rectangle(bbox: tuple[int, int, int, int], fill: str) -> SpritePrimitive:
    return SpritePrimitive(op="rectangle", bbox=bbox, fill=fill)


def _poly(points: list[tuple[int, int]], fill: str) -> SpritePrimitive:
    return SpritePrimitive(op="polygon", points=points, fill=fill)


def _line(points: list[tuple[int, int]], fill: str, *, width: int) -> SpritePrimitive:
    return SpritePrimitive(op="line", points=points, fill=fill, width=width)


def _point(x: int, y: int, fill: str, *, size: int = 1) -> SpritePrimitive:
    return SpritePrimitive(op="point", points=[(x, y)], fill=fill, size=size)


__all__ = [
    "ProceduralSpriteError",
    "ProceduralSpriteResult",
    "build_sprite_blueprint",
    "render_blueprint",
    "render_procedural_sprite",
]
