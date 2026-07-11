from __future__ import annotations

import io

from PIL import Image

from app.schemas.sprite import AssetSpec
from app.services.procedural_sprite import build_sprite_blueprint, render_blueprint
from app.services.sprite_blueprint import _resolve_strategy
from app.services.sprite_interpretation import create_asset_spec_from_prompt
from app.sprite_engine.character.skeleton import HumanoidSkeleton, HumanoidTraits, build_humanoid_skeleton
from app.sprite_engine.quality.structural import evaluate_sprite_quality


def test_default_chibi_skeleton_has_grounded_symmetric_anchors():
    skeleton = HumanoidSkeleton()
    assert skeleton.center_x == 32
    assert skeleton.ground_y == 58
    assert skeleton.mirror_x(25) == 39


def test_humanoid_skeleton_clamps_conflicting_traits_safely():
    skeleton = build_humanoid_skeleton(HumanoidTraits(height="short", head_size="large", leg_length="long"))
    assert skeleton.head_top_y < skeleton.shoulder_y < skeleton.waist_y < skeleton.hip_y < skeleton.ground_y


def test_character_recipe_maps_anatomy_to_distinct_safe_skeletons():
    short_heavy = AssetSpec.model_validate(
        {
            "subject": "human blacksmith",
            "character": {
                "anatomy": {"height": "short", "build": "heavy", "head_size": "large", "leg_length": "short"}
            },
        }
    )
    tall_slim = AssetSpec.model_validate(
        {
            "subject": "human ranger",
            "character": {"anatomy": {"height": "tall", "build": "slim", "head_size": "small", "leg_length": "long"}},
        }
    )
    short_blueprint = build_sprite_blueprint(short_heavy, seed=7)
    tall_blueprint = build_sprite_blueprint(tall_slim, seed=7)
    assert short_blueprint.recipe == tall_blueprint.recipe == "humanoid_character"
    assert _opaque_bbox(short_blueprint) != _opaque_bbox(tall_blueprint)


def test_non_llm_spanish_prompt_populates_character_spec_and_palette():
    spec = create_asset_spec_from_prompt(
        "un herrero humano bajito y gordo, con cabeza grande, armadura roja y detalles dorados"
    )
    assert spec.character is not None
    assert spec.character.anatomy.height == "short"
    assert spec.character.anatomy.build == "heavy"
    assert spec.character.anatomy.head_size == "large"
    assert spec.palette.main == ["red"]


def test_humanoid_recipe_has_quality_passing_layers():
    blueprint = build_sprite_blueprint(AssetSpec(subject="human"), seed=0)
    image = Image.open(io.BytesIO(render_blueprint(blueprint, width=64, height=64).png_bytes))
    assert evaluate_sprite_quality(image).passed
    assert image.getbbox() is not None


def test_auto_strategy_routes_side_view_humanoids_to_llm_blueprint():
    assert _resolve_strategy(AssetSpec(subject="humanoid person", game_view="side-view"), "auto") == "llm_blueprint"


def _opaque_bbox(blueprint) -> tuple[int, int, int, int]:
    image = Image.open(io.BytesIO(render_blueprint(blueprint, width=64, height=64).png_bytes))
    bbox = image.getbbox()
    assert bbox is not None
    return bbox
