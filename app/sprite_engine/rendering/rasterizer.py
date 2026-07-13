from __future__ import annotations

from collections import defaultdict

import numpy as np
from PIL import Image, ImageDraw

from app.schemas.sprite import SpriteBlueprint, SpritePrimitive

BASE_CANVAS_SIZE = 64


def compose_blueprint_layers(
    blueprint: SpriteBlueprint, *, width: int, height: int
) -> tuple[Image.Image, dict[str, Image.Image]]:
    """Rasterize semantic layers as RGBA canvases, then alpha-composite them in declared order."""

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    masks = render_layer_masks(blueprint, width=width, height=height)
    grouped: dict[str, list[SpritePrimitive]] = defaultdict(list)
    for primitive in blueprint.primitives:
        grouped[primitive.layer].append(primitive)
    palette = {name: _rgba(color) for name, color in blueprint.palette.items()}
    scale_x = width / BASE_CANVAS_SIZE
    scale_y = height / BASE_CANVAS_SIZE

    for layer_name in blueprint.layer_order:
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        for primitive in grouped.get(layer_name, []):
            scaled = _scale_primitive(primitive, scale_x, scale_y)
            part = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            _draw_primitive(ImageDraw.Draw(part), scaled, _resolve_fill(scaled.fill, palette))
            material = blueprint.material_roles.get(primitive.fill)
            if material is not None:
                part = _apply_material_shading(part, material, blueprint.lighting_direction)
            layer = Image.alpha_composite(layer, part)
        canvas = Image.alpha_composite(canvas, layer)
    return canvas, masks


def render_layer_masks(blueprint: SpriteBlueprint, *, width: int, height: int) -> dict[str, Image.Image]:
    """Rasterize alpha masks per semantic layer for inspection and compositing."""

    masks: dict[str, Image.Image] = {}
    grouped: dict[str, list[SpritePrimitive]] = defaultdict(list)
    for primitive in blueprint.primitives:
        grouped[primitive.layer].append(primitive)
    for layer_name in blueprint.layer_order:
        primitives = grouped.get(layer_name, [])
        if not primitives:
            continue
        mask = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(mask)
        for primitive in primitives:
            _draw_mask_primitive(draw, _scale_primitive(primitive, width / BASE_CANVAS_SIZE, height / BASE_CANVAS_SIZE))
        masks[layer_name] = mask
    return masks


def _apply_material_shading(image: Image.Image, material: str, direction: str = "top_left") -> Image.Image:
    alpha = np.asarray(image.getchannel("A")) > 0
    if not alpha.any():
        return image
    padded = np.pad(alpha, 1, constant_values=False)
    if direction == "top_right":
        highlight = alpha & ~padded[0 : alpha.shape[0], 2 : alpha.shape[1] + 2]
        shadow = alpha & ~padded[2 : alpha.shape[0] + 2, 0 : alpha.shape[1]]
    else:
        highlight = alpha & ~padded[0 : alpha.shape[0], 0 : alpha.shape[1]]
        shadow = alpha & ~padded[2 : alpha.shape[0] + 2, 2 : alpha.shape[1] + 2]
    pixels = np.asarray(image).copy()
    shadow_factor, highlight_factor = {
        "cloth": (0.78, 1.10),
        "leather": (0.70, 1.08),
        "wood": (0.68, 1.05),
        "metal": (0.62, 1.34),
        "skin": (0.82, 1.08),
        "hair": (0.72, 1.04),
    }[material]
    rgb = pixels[..., :3].astype(np.float32)
    rgb[shadow] *= shadow_factor
    rgb[highlight] *= highlight_factor
    pixels[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return Image.fromarray(pixels, mode="RGBA")


def _scale_primitive(primitive: SpritePrimitive, scale_x: float, scale_y: float) -> SpritePrimitive:
    bbox = None
    if primitive.bbox is not None:
        bbox = tuple(
            round(value * (scale_x if index % 2 == 0 else scale_y)) for index, value in enumerate(primitive.bbox)
        )
    points = [(round(x * scale_x), round(y * scale_y)) for x, y in primitive.points]
    stroke_scale = min(scale_x, scale_y)
    return primitive.model_copy(
        update={
            "bbox": bbox,
            "points": points,
            "width": max(1, round((primitive.width or 1) * stroke_scale)),
            "size": max(1, round((primitive.size or 1) * stroke_scale)),
        }
    )


def _draw_mask_primitive(draw: ImageDraw.ImageDraw, primitive: SpritePrimitive) -> None:
    _draw_primitive(draw, primitive, 255)


def _draw_primitive(
    draw: ImageDraw.ImageDraw, primitive: SpritePrimitive, fill: int | tuple[int, int, int, int]
) -> None:
    if primitive.op == "ellipse" and primitive.bbox is not None:
        draw.ellipse(primitive.bbox, fill=fill)
    elif primitive.op == "rectangle" and primitive.bbox is not None:
        draw.rectangle(primitive.bbox, fill=fill)
    elif primitive.op == "polygon":
        draw.polygon(primitive.points, fill=fill)
    elif primitive.op == "line":
        draw.line(primitive.points, fill=fill, width=primitive.width or 1, joint="curve")
    elif primitive.op == "point" and primitive.points:
        x, y = primitive.points[0]
        size = primitive.size or 1
        draw.rectangle((x, y, x + size - 1, y + size - 1), fill=fill)


def _rgba(hex_color: str) -> tuple[int, int, int, int]:
    value = hex_color.removeprefix("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), 255)


def _resolve_fill(fill: str, palette: dict[str, tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    return palette[fill] if fill in palette else _rgba(fill)


__all__ = ["compose_blueprint_layers", "render_layer_masks"]
