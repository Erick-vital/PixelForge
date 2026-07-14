from __future__ import annotations

from app.schemas.sprite import AssetSpec, SpriteBlueprint, SpritePrimitive
from app.sprite_engine.quality.semantic import evaluate_semantic_quality


def _wizard_spec() -> AssetSpec:
    return AssetSpec.model_validate(
        {
            "family": "humanoid",
            "archetype": "wizard",
            "subject": "wizard",
            "game_view": "icon/front",
            "character": {
                "clothing": {"headwear": "wizard_hat", "upper": "robe", "lower": "robe_lower"},
                "equipment": {"hand": "staff"},
            },
        }
    )


def _blueprint(primitives: list[SpritePrimitive]) -> SpriteBlueprint:
    return SpriteBlueprint(
        recipe="llm_blueprint",
        subject="test",
        palette={"cloth": "#4267a8", "wood": "#805a36", "skin": "#d49a6a", "ground": "#333333"},
        material_roles={"cloth": "cloth", "wood": "wood", "skin": "skin"},
        primitives=primitives,
    )


def _wolf_spec() -> AssetSpec:
    return AssetSpec.model_validate(
        {
            "family": "quadruped",
            "archetype": "wolf",
            "subject": "wolf",
            "game_view": "side-view",
            "quadruped": {
                "body_length": "long",
                "body_depth": "slim",
                "leg_length": "long",
                "head_shape": "wedge",
                "snout_length": "long",
                "ear_shape": "upright",
                "tail_shape": "bushy",
            },
        }
    )


def test_wolf_rejects_non_directional_snout_and_reversed_leg_order() -> None:
    blueprint = _blueprint(
        [
            SpritePrimitive(op="ellipse", fill="cloth", layer="torso", bbox=(14, 26, 46, 42), part="body"),
            SpritePrimitive(op="ellipse", fill="cloth", layer="head", bbox=(42, 16, 58, 30), part="head"),
            SpritePrimitive(op="rectangle", fill="cloth", layer="head", bbox=(46, 20, 52, 26), part="snout"),
            SpritePrimitive(
                op="polygon", fill="cloth", layer="head", points=[(44, 17), (46, 10), (48, 17)], part="ear"
            ),
            SpritePrimitive(
                op="polygon", fill="cloth", layer="head", points=[(50, 17), (52, 10), (54, 17)], part="ear"
            ),
            SpritePrimitive(
                op="polygon", fill="cloth", layer="back_equipment", points=[(14, 30), (6, 24), (12, 40)], part="tail"
            ),
            SpritePrimitive(op="rectangle", fill="cloth", layer="arms", bbox=(18, 38, 21, 58), part="front_leg"),
            SpritePrimitive(op="rectangle", fill="cloth", layer="arms", bbox=(22, 38, 25, 58), part="front_leg"),
            SpritePrimitive(op="rectangle", fill="cloth", layer="pants", bbox=(36, 38, 39, 58), part="rear_leg"),
            SpritePrimitive(op="rectangle", fill="cloth", layer="pants", bbox=(40, 38, 43, 58), part="rear_leg"),
            SpritePrimitive(
                op="line", fill="ground", layer="base", points=[(10, 58), (54, 58)], width=1, part="ground"
            ),
        ]
    )

    report = evaluate_semantic_quality(_wolf_spec(), blueprint, grammar_name=None)

    assert "wolf_snout_not_directional" in report.issue_codes
    assert "wolf_leg_order_invalid" in report.issue_codes


def test_wolf_rejects_detached_anatomy_and_legs_above_ground() -> None:
    blueprint = _blueprint(
        [
            SpritePrimitive(op="ellipse", fill="cloth", layer="torso", bbox=(14, 26, 46, 42), part="body"),
            SpritePrimitive(op="ellipse", fill="cloth", layer="head", bbox=(52, 8, 60, 20), part="head"),
            SpritePrimitive(op="rectangle", fill="cloth", layer="head", bbox=(60, 12, 63, 17), part="snout"),
            SpritePrimitive(op="polygon", fill="cloth", layer="head", points=[(53, 9), (55, 3), (57, 9)], part="ear"),
            SpritePrimitive(op="polygon", fill="cloth", layer="head", points=[(57, 9), (59, 3), (61, 9)], part="ear"),
            SpritePrimitive(
                op="polygon", fill="cloth", layer="back_equipment", points=[(2, 10), (8, 8), (9, 14)], part="tail"
            ),
            SpritePrimitive(op="rectangle", fill="cloth", layer="arms", bbox=(36, 34, 39, 42), part="front_leg"),
            SpritePrimitive(op="rectangle", fill="cloth", layer="arms", bbox=(40, 34, 43, 42), part="front_leg"),
            SpritePrimitive(op="rectangle", fill="cloth", layer="pants", bbox=(18, 34, 21, 42), part="rear_leg"),
            SpritePrimitive(op="rectangle", fill="cloth", layer="pants", bbox=(22, 34, 25, 42), part="rear_leg"),
            SpritePrimitive(
                op="line", fill="ground", layer="base", points=[(10, 58), (54, 58)], width=1, part="ground"
            ),
        ]
    )

    report = evaluate_semantic_quality(_wolf_spec(), blueprint, grammar_name=None)

    assert "wolf_head_not_attached" in report.issue_codes
    assert "wolf_tail_not_attached" in report.issue_codes
    assert "wolf_legs_not_grounded" in report.issue_codes
    assert report.metrics["wolf_ground_y"] == 58
    assert report.metrics["wolf_leg_bottoms"] == "42,42,42,42"


def test_wolf_requires_tagged_anatomical_parts() -> None:
    blueprint = _blueprint(
        [
            SpritePrimitive(op="ellipse", fill="cloth", layer="torso", bbox=(14, 26, 46, 42), part="body"),
            SpritePrimitive(op="ellipse", fill="cloth", layer="head", bbox=(42, 16, 58, 30), part="head"),
        ]
    )

    report = evaluate_semantic_quality(_wolf_spec(), blueprint, grammar_name=None)

    assert report.passed is False
    assert "wolf_missing_snout" in report.issue_codes
    assert "wolf_missing_ears" in report.issue_codes
    assert "wolf_missing_tail" in report.issue_codes
    assert "wolf_missing_front_legs" in report.issue_codes
    assert "wolf_missing_rear_legs" in report.issue_codes
    assert "wolf_missing_ground" in report.issue_codes


def test_wizard_rejects_buckle_larger_than_detached_belt() -> None:
    blueprint = _blueprint(
        [
            SpritePrimitive(op="ellipse", fill="skin", layer="head", bbox=(24, 12, 40, 28), part="head"),
            SpritePrimitive(op="polygon", fill="cloth", layer="hair", points=[(25, 13), (39, 13), (32, 4)], part="hat"),
            SpritePrimitive(op="rectangle", fill="cloth", layer="torso", bbox=(20, 28, 44, 54), part="robe"),
            SpritePrimitive(op="rectangle", fill="skin", layer="arms", bbox=(42, 37, 47, 43), part="hand"),
            SpritePrimitive(
                op="line", fill="wood", layer="front_equipment", points=[(45, 12), (45, 56)], width=2, part="staff"
            ),
            SpritePrimitive(op="rectangle", fill="wood", layer="front_equipment", bbox=(2, 2, 18, 12), part="belt"),
            SpritePrimitive(op="rectangle", fill="skin", layer="front_equipment", bbox=(2, 2, 20, 14), part="buckle"),
        ]
    )

    report = evaluate_semantic_quality(_wizard_spec(), blueprint, grammar_name=None)

    assert "wizard_belt_not_on_robe" in report.issue_codes
    assert "wizard_buckle_not_smaller_than_belt" in report.issue_codes


def test_wizard_rejects_misplaced_hat_and_detached_staff() -> None:
    blueprint = _blueprint(
        [
            SpritePrimitive(op="ellipse", fill="skin", layer="head", bbox=(24, 12, 40, 28), part="head"),
            SpritePrimitive(
                op="polygon", fill="cloth", layer="hair", points=[(25, 52), (39, 52), (32, 44)], part="hat"
            ),
            SpritePrimitive(op="rectangle", fill="cloth", layer="torso", bbox=(20, 28, 44, 54), part="robe"),
            SpritePrimitive(op="rectangle", fill="skin", layer="arms", bbox=(42, 37, 47, 43), part="hand"),
            SpritePrimitive(
                op="line", fill="wood", layer="front_equipment", points=[(56, 10), (56, 56)], width=2, part="staff"
            ),
        ]
    )

    report = evaluate_semantic_quality(_wizard_spec(), blueprint, grammar_name=None)

    assert "wizard_hat_not_above_head" in report.issue_codes
    assert "wizard_staff_not_held" in report.issue_codes


def test_wizard_requires_tagged_hat_robe_hand_and_staff() -> None:
    blueprint = _blueprint(
        [
            SpritePrimitive(op="ellipse", fill="skin", layer="head", bbox=(24, 12, 40, 28), part="head"),
            SpritePrimitive(op="rectangle", fill="cloth", layer="torso", bbox=(20, 28, 44, 54), part="robe"),
        ]
    )

    report = evaluate_semantic_quality(_wizard_spec(), blueprint, grammar_name=None)

    assert report.passed is False
    assert "wizard_missing_hat" in report.issue_codes
    assert "wizard_missing_hand" in report.issue_codes
    assert "wizard_missing_staff" in report.issue_codes
