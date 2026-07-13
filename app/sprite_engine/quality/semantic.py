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
