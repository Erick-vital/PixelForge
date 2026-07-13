from __future__ import annotations

from app.schemas.sprite import AssetSpec, SpriteBlueprint, SpritePrimitive
from app.sprite_engine.quality.semantic import evaluate_semantic_quality


def _side_warrior_spec() -> AssetSpec:
    return AssetSpec.model_validate(
        {
            "family": "humanoid",
            "archetype": "warrior",
            "subject": "warrior",
            "game_view": "side-view",
            "character": {"pose": {"stance": "side_neutral", "direction": "right"}},
        }
    )


def _front_warrior_spec() -> AssetSpec:
    return AssetSpec.model_validate(
        {
            "family": "humanoid",
            "archetype": "warrior",
            "subject": "warrior",
            "game_view": "icon/front",
            "character": {"pose": {"stance": "front_neutral"}},
        }
    )


def _front_symmetric_blueprint() -> SpriteBlueprint:
    return SpriteBlueprint(
        recipe="llm_blueprint",
        subject="warrior",
        palette={"skin": "#d49a6a", "metal": "#aebcca", "cloth": "#4267a8"},
        material_roles={"skin": "skin", "metal": "metal", "cloth": "cloth"},
        primitives=[
            SpritePrimitive(op="ellipse", fill="skin", layer="head", bbox=(23, 7, 41, 28)),
            SpritePrimitive(op="rectangle", fill="metal", layer="torso", bbox=(25, 28, 39, 45)),
            SpritePrimitive(op="line", fill="cloth", layer="pants", points=[(29, 44), (29, 57)], width=5),
            SpritePrimitive(op="line", fill="cloth", layer="pants", points=[(35, 44), (35, 57)], width=5),
        ],
    )


def _valid_side_profile_blueprint() -> SpriteBlueprint:
    return SpriteBlueprint(
        recipe="llm_blueprint",
        subject="warrior",
        palette={"skin": "#d49a6a", "metal": "#aebcca", "cloth": "#4267a8"},
        material_roles={"skin": "skin", "metal": "metal", "cloth": "cloth"},
        primitives=[
            SpritePrimitive(op="ellipse", fill="skin", layer="head", bbox=(22, 7, 39, 28)),
            SpritePrimitive(op="polygon", fill="skin", layer="head", points=[(38, 14), (49, 18), (38, 22)]),
            SpritePrimitive(op="rectangle", fill="metal", layer="torso", bbox=(25, 28, 39, 45)),
            SpritePrimitive(op="line", fill="cloth", layer="pants", points=[(28, 44), (22, 51), (23, 57)], width=5),
            SpritePrimitive(op="line", fill="cloth", layer="pants", points=[(35, 44), (39, 50), (42, 57)], width=5),
            SpritePrimitive(op="line", fill="metal", layer="front_equipment", points=[(39, 35), (54, 24)], width=3),
        ],
    )


def test_side_view_rejects_front_symmetric_humanoid_blueprint() -> None:
    result = evaluate_semantic_quality(_side_warrior_spec(), _front_symmetric_blueprint(), grammar_name=None)

    assert result.passed is False
    assert "side_view_symmetry_too_high" in result.issue_codes
    assert "side_view_missing_directional_feature" in result.issue_codes


def test_side_view_accepts_profile_with_directional_face_and_limb_offset() -> None:
    result = evaluate_semantic_quality(_side_warrior_spec(), _valid_side_profile_blueprint(), grammar_name=None)

    assert result.passed is True


def test_front_view_rejects_strongly_asymmetric_profile_blueprint() -> None:
    result = evaluate_semantic_quality(_front_warrior_spec(), _valid_side_profile_blueprint(), grammar_name=None)

    assert "front_view_symmetry_too_low" in result.issue_codes
