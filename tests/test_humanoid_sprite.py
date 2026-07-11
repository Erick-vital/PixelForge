from __future__ import annotations

import io

from PIL import Image

from app.models.humanoid import HumanoidSkeleton, HumanoidTraits, build_humanoid_skeleton
from app.schemas.sprite import AssetSpec
from app.services.humanoid_sprite import compile_humanoid_base
from app.services.procedural_sprite import build_sprite_blueprint, render_blueprint
from app.services.sprite_blueprint import _resolve_strategy
from app.services.sprite_interpretation import create_asset_spec_from_prompt
from app.services.sprite_quality import evaluate_sprite_quality


def test_default_chibi_skeleton_has_grounded_symmetric_anchors():
    skeleton = HumanoidSkeleton()

    assert skeleton.center_x == 32
    assert skeleton.ground_y == 58
    assert skeleton.mirror_x(25) == 39
    assert skeleton.head_top_y < skeleton.head_bottom_y < skeleton.ground_y


def test_humanoid_skeleton_clamps_conflicting_short_large_head_long_leg_traits_safely():
    skeleton = build_humanoid_skeleton(HumanoidTraits(height="short", head_size="large", leg_length="long"))

    assert skeleton.head_top_y < skeleton.shoulder_y < skeleton.waist_y < skeleton.hip_y < skeleton.ground_y
    assert skeleton.arm_top_y < skeleton.arm_bottom_y <= skeleton.hip_y


def test_humanoid_compiler_adds_symmetric_attached_arms():
    palette = {"outline": "#202020", "base": "#7a9b4f", "shadow": "#3d552c", "highlight": "#b5d178"}
    skeleton = HumanoidSkeleton()
    blueprint = compile_humanoid_base("human chibi", palette, skeleton=skeleton)

    arm_bboxes = [
        primitive.bbox
        for primitive in blueprint.primitives
        if primitive.op == "rectangle" and primitive.bbox and primitive.bbox[1] == skeleton.arm_top_y
    ]

    assert arm_bboxes == [(16, 32, 22, 45), (42, 32, 48, 45)]


def test_humanoid_compiler_creates_a_quality_passing_chibi_blueprint():
    palette = {"outline": "#202020", "base": "#7a9b4f", "shadow": "#3d552c", "highlight": "#b5d178"}
    blueprint = compile_humanoid_base("human chibi", palette)

    result = render_blueprint(blueprint, width=64, height=64)
    image = Image.open(io.BytesIO(result.png_bytes))
    quality = evaluate_sprite_quality(image)

    assert blueprint.recipe == "humanoid_chibi"
    assert blueprint.outline.enabled is True
    assert quality.passed is True
    assert image.getbbox() is not None


def test_humanoid_recipe_maps_typed_traits_to_distinct_safe_skeletons():
    short_heavy = AssetSpec.model_validate(
        {
            "subject": "human blacksmith",
            "humanoid": {
                "height": "short",
                "build": "heavy",
                "head_size": "large",
                "leg_length": "short",
            },
        }
    )
    tall_slim = AssetSpec.model_validate(
        {
            "subject": "human ranger",
            "humanoid": {
                "height": "tall",
                "build": "slim",
                "head_size": "small",
                "leg_length": "long",
            },
        }
    )

    short_blueprint = build_sprite_blueprint(short_heavy, seed=7)
    tall_blueprint = build_sprite_blueprint(tall_slim, seed=7)

    assert short_blueprint.recipe == tall_blueprint.recipe == "humanoid_chibi"
    assert _opaque_bbox(short_blueprint) != _opaque_bbox(tall_blueprint)
    assert _opaque_height(short_blueprint) < _opaque_height(tall_blueprint)
    assert _opaque_width(short_blueprint) > _opaque_width(tall_blueprint)


def test_humanoid_recipe_preserves_requested_semantic_palette_roles():
    spec = AssetSpec.model_validate(
        {
            "subject": "human knight",
            "palette": {"main": ["red", "steel"], "shadows": ["dark red"], "accent": ["gold"]},
        }
    )

    blueprint = build_sprite_blueprint(spec, seed=0)

    assert blueprint.palette["base"] == "#b83a3a"
    assert blueprint.palette["accent"] == "#d8a43d"


def test_humanoid_recipe_preserves_llm_hex_palette_values():
    spec = AssetSpec.model_validate(
        {
            "subject": "humanoid person",
            "palette": {
                "main": ["#c68642", "#8d5524"],
                "shadows": ["#5a3921"],
                "accent": ["#f2d16b"],
            },
        }
    )

    blueprint = build_sprite_blueprint(spec, seed=0)

    assert blueprint.palette["base"] == "#c68642"
    assert blueprint.palette["shadow"] == "#5a3921"
    assert blueprint.palette["accent"] == "#f2d16b"


def test_non_llm_spanish_prompt_populates_humanoid_traits_and_palette():
    spec = create_asset_spec_from_prompt(
        "un herrero humano bajito y gordo, con cabeza grande, armadura roja y detalles dorados"
    )

    assert spec.humanoid is not None
    assert spec.humanoid.height == "short"
    assert spec.humanoid.build == "heavy"
    assert spec.humanoid.head_size == "large"
    assert spec.palette.main == ["red"]
    assert spec.palette.accent == ["gold"]


def test_auto_strategy_routes_side_view_humanoids_to_llm_blueprint():
    spec = AssetSpec.model_validate({"subject": "humanoid person", "game_view": "side-view"})

    assert _resolve_strategy(spec, "auto") == "llm_blueprint"


def _opaque_bbox(blueprint) -> tuple[int, int, int, int]:
    image = Image.open(io.BytesIO(render_blueprint(blueprint, width=64, height=64).png_bytes))
    bbox = image.getbbox()
    assert bbox is not None
    return bbox


def _opaque_height(blueprint) -> int:
    _left, top, _right, bottom = _opaque_bbox(blueprint)
    return bottom - top


def _opaque_width(blueprint) -> int:
    left, _top, right, _bottom = _opaque_bbox(blueprint)
    return right - left
