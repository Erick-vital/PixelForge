from app.schemas.sprite import AssetSpec, SpriteBlueprint, SpriteOutlineSpec, SpritePrimitive
from app.sprite_engine.character.quadruped_skeleton import build_quadruped_skeleton
from app.sprite_engine.character.quadruped_spec import QuadrupedSpec
from app.sprite_engine.grammar.models import GrammarCapabilities


class QuadrupedSideGrammar:
    name = "quadruped_side"
    skeleton_name = "QuadrupedSkeleton"
    capabilities = GrammarCapabilities(
        "quadruped", frozenset({"side-view"}), frozenset({"pig"}), frozenset({"side_neutral"})
    )

    def supports(self, spec: AssetSpec) -> bool:
        quadruped = spec.quadruped or QuadrupedSpec()
        return (
            spec.family == "quadruped"
            and spec.game_view in self.capabilities.views
            and spec.archetype in self.capabilities.archetypes
            and quadruped.pose in self.capabilities.poses
        )

    def compile(self, spec: AssetSpec, *, seed: int) -> SpriteBlueprint:
        quadruped = spec.quadruped or QuadrupedSpec(body_depth="heavy", leg_length="short")
        s = build_quadruped_skeleton(quadruped)
        palette = {"outline": "#44252c", "skin": "#e78da1", "shadow": "#b95873", "highlight": "#ffd1d8"}
        tail = _tail_points(s.tail_anchor, quadruped.tail_shape, quadruped.direction)
        primitives = [
            SpritePrimitive(op="line", fill="shadow", layer="back_equipment", points=tail, width=2),
            SpritePrimitive(op="ellipse", fill="skin", layer="torso", bbox=s.body_bbox),
        ]
        for anchor, foot in zip(s.leg_anchors, s.feet, strict=True):
            primitives.append(SpritePrimitive(op="line", fill="skin", layer="pants", points=[anchor, foot], width=5))
        if quadruped.head_shape == "round":
            primitives.append(SpritePrimitive(op="ellipse", fill="skin", layer="head", bbox=s.head_bbox))
        else:
            x0, y0, x1, y1 = s.head_bbox
            front_x = x1 if quadruped.direction == "right" else x0
            back_x = x0 if quadruped.direction == "right" else x1
            primitives.append(
                SpritePrimitive(
                    op="polygon",
                    fill="skin",
                    layer="head",
                    points=[(back_x, y0), (front_x, (y0 + y1) // 2), (back_x, y1)],
                )
            )
        sx, sy = s.snout_anchor
        snout_width = {"short": 4, "average": 6, "long": 8}[quadruped.snout_length]
        if quadruped.direction == "right":
            snout_bbox = (sx - snout_width, sy - 3, sx, sy + 3)
            eye = (s.head_center[0] + 3, s.head_center[1] - 3)
        else:
            snout_bbox = (sx, sy - 3, sx + snout_width, sy + 3)
            eye = (s.head_center[0] - 3, s.head_center[1] - 3)
        primitives.extend(
            [
                SpritePrimitive(op="rectangle", fill="skin", layer="head", bbox=snout_bbox),
                SpritePrimitive(op="polygon", fill="shadow", layer="head", points=list(s.ear_points)),
                SpritePrimitive(op="point", fill="outline", layer="head", points=[eye], size=2),
            ]
        )
        return SpriteBlueprint(
            recipe="quadruped_side/pig",
            subject=spec.subject,
            palette=palette,
            primitives=primitives,
            material_roles={"skin": "skin"},
            outline=SpriteOutlineSpec(enabled=True),
            notes=["four connected grounded legs", "snout forward and tail behind", f"direction:{quadruped.direction}"],
        )


def _tail_points(anchor: tuple[int, int], shape: str, direction: str) -> list[tuple[int, int]]:
    x, y = anchor
    sign = -1 if direction == "right" else 1
    if shape == "straight":
        return [anchor, (x + sign * 9, y - 4)]
    if shape == "bushy":
        return [anchor, (x + sign * 5, y - 7), (x + sign * 11, y - 3)]
    return [anchor, (x + sign * 7, y - 4), (x + sign * 5, y + 3), (x + sign * 2, y)]
