from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import TypeAlias

import numpy as np
from PIL import Image

from app.schemas.sprite import AssetSpec, SpriteBlueprint, SpritePrimitive
from app.services.procedural_sprite import render_blueprint

# Side profiles must depart materially from their mirrored silhouette.  The value
# intentionally leaves room for compact torsos while rejecting frontal sprites.
SIDE_VIEW_MAX_MIRROR_OVERLAP = 0.88
# Front grammars may contain a small held item, but their silhouette remains
# predominantly symmetric.
FRONT_VIEW_MIN_MIRROR_OVERLAP = 0.70

SemanticMetric: TypeAlias = float | int | str


@dataclass(frozen=True)
class SemanticQualityReport:
    passed: bool
    issue_codes: tuple[str, ...]
    metrics: dict[str, SemanticMetric]

    def as_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "issue_codes": list(self.issue_codes),
            "metrics": self.metrics,
        }


class SemanticQualityError(ValueError):
    def __init__(self, report: SemanticQualityReport) -> None:
        self.report = report
        super().__init__(", ".join(report.issue_codes) or "semantic quality validation failed")


def evaluate_semantic_quality(
    spec: AssetSpec, blueprint: SpriteBlueprint, *, grammar_name: str | None
) -> SemanticQualityReport:
    """Evaluate deterministic view and grammar contracts before persistence.

    Raster symmetry measures the actual rendered silhouette; primitive checks
    complement it with explicit profile-face and limb-depth evidence, avoiding
    model-based image recognition.
    """
    issue_codes: list[str] = []
    metrics: dict[str, SemanticMetric] = {"required_view": spec.game_view}

    _append_grammar_contract_issues(spec, blueprint, grammar_name, issue_codes)
    if grammar_name is None:
        _append_llm_family_contract_issues(spec, blueprint, issue_codes, metrics)

    if spec.family == "humanoid" and spec.game_view in {"side-view", "icon/front"}:
        mirror_overlap = _mirror_overlap(spec, blueprint)
        metrics["mirror_overlap"] = mirror_overlap
        if spec.game_view == "side-view":
            if mirror_overlap >= SIDE_VIEW_MAX_MIRROR_OVERLAP:
                issue_codes.append("side_view_symmetry_too_high")
            if not _has_directional_profile_feature(blueprint):
                issue_codes.append("side_view_missing_directional_feature")
            if not _has_limb_depth(blueprint):
                issue_codes.append("side_view_missing_limb_depth")
        elif grammar_name is None and mirror_overlap < FRONT_VIEW_MIN_MIRROR_OVERLAP:
            # Grammar compilers have their own structural symmetry contracts and
            # may include intentionally asymmetric held equipment. LLM blueprints
            # need this raster-level guard because they lack that provenance.
            issue_codes.append("front_view_symmetry_too_low")

    return SemanticQualityReport(passed=not issue_codes, issue_codes=tuple(issue_codes), metrics=metrics)


def require_semantic_quality(
    spec: AssetSpec, blueprint: SpriteBlueprint, grammar_name: str | None = None
) -> SemanticQualityReport:
    report = evaluate_semantic_quality(spec, blueprint, grammar_name=grammar_name)
    if not report.passed:
        raise SemanticQualityError(report)
    return report


def _append_llm_family_contract_issues(
    spec: AssetSpec,
    blueprint: SpriteBlueprint,
    issue_codes: list[str],
    metrics: dict[str, SemanticMetric],
) -> None:
    parts = {primitive.part for primitive in blueprint.primitives if primitive.part is not None}
    if spec.family == "humanoid" and spec.archetype == "wizard":
        required_parts = ["head", "hat", "robe"]
        held_part = None
        if spec.character and spec.character.equipment.hand != "none":
            held_part = "staff" if spec.character.equipment.hand == "staff" else "held_item"
            required_parts.extend(["hand", held_part])
        for part in required_parts:
            if part not in parts:
                issue_codes.append(f"wizard_missing_{part}")
        head = _part_bounds(blueprint, "head")
        hat = _part_bounds(blueprint, "hat")
        if head and hat and hat[3] > head[1] + 4:
            issue_codes.append("wizard_hat_not_above_head")
        held_item = _part_bounds(blueprint, held_part) if held_part else None
        hands = [_primitive_bounds(primitive) for primitive in blueprint.primitives if primitive.part == "hand"]
        if held_item and hands and not any(_bounds_touch(held_item, hand) for hand in hands):
            issue_codes.append("wizard_staff_not_held" if held_part == "staff" else "wizard_held_item_not_held")
        robe = _part_bounds(blueprint, "robe")
        belt = _part_bounds(blueprint, "belt")
        buckle = _part_bounds(blueprint, "buckle")
        if robe and belt and not _bounds_touch(robe, belt):
            issue_codes.append("wizard_belt_not_on_robe")
        if belt and buckle and _bounds_area(buckle) >= _bounds_area(belt):
            issue_codes.append("wizard_buckle_not_smaller_than_belt")

    if spec.family == "quadruped" and spec.archetype == "wolf":
        required = {"body", "head", "snout", "tail", "ground"}
        for part in required - parts:
            issue_codes.append(f"wolf_missing_{part}")
        if sum(primitive.part == "ear" for primitive in blueprint.primitives) < 2:
            issue_codes.append("wolf_missing_ears")
        if sum(primitive.part == "front_leg" for primitive in blueprint.primitives) < 2:
            issue_codes.append("wolf_missing_front_legs")
        if sum(primitive.part == "rear_leg" for primitive in blueprint.primitives) < 2:
            issue_codes.append("wolf_missing_rear_legs")
        body = _part_bounds(blueprint, "body")
        head = _part_bounds(blueprint, "head")
        snout = _part_bounds(blueprint, "snout")
        tail = _part_bounds(blueprint, "tail")
        ground = _part_bounds(blueprint, "ground")
        direction = spec.quadruped.direction if spec.quadruped else "right"
        if body and body[2] - body[0] <= body[3] - body[1]:
            issue_codes.append("wolf_body_not_longer_than_tall")
        if (
            head
            and snout
            and ((direction == "right" and snout[2] <= head[2]) or (direction == "left" and snout[0] >= head[0]))
        ):
            issue_codes.append("wolf_snout_not_directional")
        if body and head and not _bounds_touch(body, head):
            issue_codes.append("wolf_head_not_attached")
        if body and tail and not _bounds_touch(body, tail):
            issue_codes.append("wolf_tail_not_attached")
        leg_bounds = [
            _primitive_bounds(primitive)
            for primitive in blueprint.primitives
            if primitive.part in {"front_leg", "rear_leg"}
        ]
        if ground:
            metrics["wolf_ground_y"] = ground[3]
        if leg_bounds:
            metrics["wolf_leg_bottoms"] = ",".join(str(leg[3]) for leg in leg_bounds)
        front_centers = [
            _primitive_center_x(primitive) for primitive in blueprint.primitives if primitive.part == "front_leg"
        ]
        rear_centers = [
            _primitive_center_x(primitive) for primitive in blueprint.primitives if primitive.part == "rear_leg"
        ]
        if (
            front_centers
            and rear_centers
            and (
                (
                    direction == "right"
                    and sum(front_centers) / len(front_centers) <= sum(rear_centers) / len(rear_centers)
                )
                or (
                    direction == "left"
                    and sum(front_centers) / len(front_centers) >= sum(rear_centers) / len(rear_centers)
                )
            )
        ):
            issue_codes.append("wolf_leg_order_invalid")
        if (
            body
            and ground
            and any(not _bounds_touch(leg, body) or not _bounds_touch(leg, ground) for leg in leg_bounds)
        ):
            issue_codes.append("wolf_legs_not_grounded")


def _part_bounds(blueprint: SpriteBlueprint, part: str) -> tuple[int, int, int, int] | None:
    bounds = [_primitive_bounds(primitive) for primitive in blueprint.primitives if primitive.part == part]
    if not bounds:
        return None
    return (
        min(bound[0] for bound in bounds),
        min(bound[1] for bound in bounds),
        max(bound[2] for bound in bounds),
        max(bound[3] for bound in bounds),
    )


def _primitive_bounds(primitive: SpritePrimitive) -> tuple[int, int, int, int]:
    if primitive.bbox is not None:
        return primitive.bbox
    xs = _primitive_xs(primitive)
    ys = [point[1] for point in primitive.points]
    pad = (primitive.width or primitive.size or 1) // 2
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def _bounds_area(bounds: tuple[int, int, int, int]) -> int:
    return max(0, bounds[2] - bounds[0]) * max(0, bounds[3] - bounds[1])


def _bounds_touch(left: tuple[int, int, int, int], right: tuple[int, int, int, int], *, tolerance: int = 1) -> bool:
    return not (
        left[2] < right[0] - tolerance
        or right[2] < left[0] - tolerance
        or left[3] < right[1] - tolerance
        or right[3] < left[1] - tolerance
    )


def _append_grammar_contract_issues(
    spec: AssetSpec, blueprint: SpriteBlueprint, grammar_name: str | None, issue_codes: list[str]
) -> None:
    if grammar_name is None:
        return
    expected = {
        "humanoid_front": ("humanoid", "icon/front"),
        "humanoid_side": ("humanoid", "side-view"),
        "quadruped_side": ("quadruped", "side-view"),
    }.get(grammar_name)
    if expected is None or (spec.family, spec.game_view) != expected:
        issue_codes.append("grammar_family_or_view_conflict")
        return
    if not blueprint.recipe.startswith(f"{grammar_name}/"):
        issue_codes.append("grammar_recipe_mismatch")
    used_layers = {primitive.layer for primitive in blueprint.primitives}
    if not used_layers or not used_layers.issubset(set(blueprint.layer_order)):
        issue_codes.append("grammar_invalid_layers")
    fills = {primitive.fill for primitive in blueprint.primitives}
    if not set(blueprint.material_roles).issubset(fills):
        issue_codes.append("grammar_invalid_material_roles")
    required = {"torso", "head"} if spec.family == "humanoid" else {"torso", "pants", "head"}
    if not required.issubset(used_layers):
        issue_codes.append("grammar_missing_semantic_layers")
    if spec.archetype == "warrior" and "metal" not in blueprint.material_roles.values():
        issue_codes.append("warrior_missing_metal")
    if spec.archetype == "wizard" and not any(
        primitive.layer == "hair" and primitive.op == "polygon" for primitive in blueprint.primitives
    ):
        issue_codes.append("wizard_missing_headwear")


def _mirror_overlap(spec: AssetSpec, blueprint: SpriteBlueprint) -> float:
    rendered = render_blueprint(
        blueprint,
        width=spec.size.width,
        height=spec.size.height,
        max_colors=spec.processing_profile.palette_max_colors,
    )
    alpha = np.asarray(Image.open(BytesIO(rendered.png_bytes)).convert("RGBA"))[:, :, 3] > 0
    ys, xs = np.where(alpha)
    if not len(xs):
        return 0.0
    cropped = alpha[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    mirrored = np.fliplr(cropped)
    union = np.logical_or(cropped, mirrored).sum()
    return round(float(np.logical_and(cropped, mirrored).sum() / union) if union else 0.0, 4)


def _has_directional_profile_feature(blueprint: SpriteBlueprint) -> bool:
    """Look for a head or front-equipment primitive extending off its base."""
    head_boxes = [primitive.bbox for primitive in blueprint.primitives if primitive.layer == "head" and primitive.bbox]
    if not head_boxes:
        return False
    left = min(box[0] for box in head_boxes)
    right = max(box[2] for box in head_boxes)
    for primitive in blueprint.primitives:
        if primitive.layer not in {"head", "front_equipment"}:
            continue
        xs = _primitive_xs(primitive)
        if xs and (min(xs) < left or max(xs) > right):
            return True
    return False


def _has_limb_depth(blueprint: SpriteBlueprint) -> bool:
    limb_primitives = [primitive for primitive in blueprint.primitives if primitive.layer in {"pants", "arms", "boots"}]
    if len(limb_primitives) < 2:
        return False
    centers = [_primitive_center_x(primitive) for primitive in limb_primitives]
    return max(centers) - min(centers) >= 6.0


def _primitive_xs(primitive: SpritePrimitive) -> list[int]:
    if primitive.bbox is not None:
        return [primitive.bbox[0], primitive.bbox[2]]
    return [point[0] for point in primitive.points]


def _primitive_center_x(primitive: SpritePrimitive) -> float:
    xs = _primitive_xs(primitive)
    return sum(xs) / len(xs) if xs else 0.0


__all__ = [
    "SemanticQualityError",
    "SemanticQualityReport",
    "evaluate_semantic_quality",
    "require_semantic_quality",
]
