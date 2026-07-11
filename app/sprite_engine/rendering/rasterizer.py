from __future__ import annotations

from collections import defaultdict

from PIL import Image, ImageDraw

from app.schemas.sprite import SpriteBlueprint, SpritePrimitive

BASE_CANVAS_SIZE = 64


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


def _scale_primitive(primitive: SpritePrimitive, scale_x: float, scale_y: float) -> SpritePrimitive:
    bbox = None
    if primitive.bbox is not None:
        bbox = tuple(
            round(value * (scale_x if index % 2 == 0 else scale_y)) for index, value in enumerate(primitive.bbox)
        )
    points = [(round(x * scale_x), round(y * scale_y)) for x, y in primitive.points]
    return primitive.model_copy(
        update={"bbox": bbox, "points": points, "width": primitive.width, "size": primitive.size}
    )


def _draw_mask_primitive(draw: ImageDraw.ImageDraw, primitive: SpritePrimitive) -> None:
    if primitive.op == "ellipse" and primitive.bbox is not None:
        draw.ellipse(primitive.bbox, fill=255)
    elif primitive.op == "rectangle" and primitive.bbox is not None:
        draw.rectangle(primitive.bbox, fill=255)
    elif primitive.op == "polygon":
        draw.polygon(primitive.points, fill=255)
    elif primitive.op == "line":
        draw.line(primitive.points, fill=255, width=primitive.width or 1)
    elif primitive.op == "point" and primitive.points:
        x, y = primitive.points[0]
        radius = max(0, (primitive.size or 1) - 1)
        draw.rectangle((x - radius, y - radius, x + radius, y + radius), fill=255)


__all__ = ["render_layer_masks"]
