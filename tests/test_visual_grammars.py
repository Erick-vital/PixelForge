from __future__ import annotations

import asyncio

import pytest

from app.schemas.sprite import AssetSpec
from app.services.sprite_blueprint import BlueprintGenerationError, generate_sprite_blueprint
from app.sprite_engine.character.quadruped_skeleton import build_quadruped_skeleton
from app.sprite_engine.character.side_skeleton import build_humanoid_side_skeleton
from app.sprite_engine.grammar import default_grammar_registry
from app.sprite_engine.grammar.classification import classify_subject


@pytest.mark.parametrize(
    ("subject", "family", "archetype"),
    [
        ("warrior", "humanoid", "warrior"),
        ("knight", "humanoid", "warrior"),
        ("wizard", "humanoid", "wizard"),
        ("blacksmith", "humanoid", "blacksmith"),
        ("person", "humanoid", "generic"),
        ("pig", "quadruped", "pig"),
        ("boar", "quadruped", "pig"),
        ("wolf", "quadruped", "wolf"),
        ("dragon", "dragon", "dragon"),
        ("potion", "prop", "potion"),
        ("strange cloud", "unknown", "generic"),
    ],
)
def test_subject_classification(subject, family, archetype):
    assert classify_subject(subject) == (family, archetype)


def spec(family="humanoid", archetype="warrior", view="icon/front", **extra):
    return AssetSpec(family=family, archetype=archetype, subject=archetype, game_view=view, **extra)


def test_registry_resolves_complete_capabilities():
    assert default_grammar_registry.resolve(spec()).grammar_name == "humanoid_front"
    assert default_grammar_registry.resolve(spec(view="side-view")).grammar_name == "humanoid_side"
    assert default_grammar_registry.resolve(spec("quadruped", "pig", "side-view")).grammar_name == "quadruped_side"
    assert not default_grammar_registry.resolve(spec("unknown", "generic")).supported


def test_grammars_are_reproducible_and_structurally_distinct():
    warrior = default_grammar_registry.compile(spec(), seed=7)
    assert warrior == default_grammar_registry.compile(spec(), seed=7)
    wizard = default_grammar_registry.compile(spec(archetype="wizard"), seed=7)
    assert warrior.recipe == "humanoid_front/warrior"
    assert wizard.recipe == "humanoid_front/wizard"
    assert warrior.primitives != wizard.primitives
    assert warrior.material_roles["shirt"] == "metal"


def test_side_and_quadruped_skeleton_invariants():
    right = build_humanoid_side_skeleton("right")
    left = right.mirror_direction()
    assert right.nose_anchor[0] > right.head_center[0]
    assert left.nose_anchor[0] < left.head_center[0]
    assert right.ground_y == right.foot_front[1] == right.foot_back[1]
    pig = build_quadruped_skeleton()
    assert len(pig.feet) == 4
    assert all(y == pig.ground_y for _, y in pig.feet)


def test_generation_mode_precedence_and_controlled_error():
    generated = asyncio.run(generate_sprite_blueprint(spec(generation_mode="controlled"), strategy="auto"))
    assert generated.strategy == "procedural"
    assert generated.grammar == "humanoid_front"
    with pytest.raises(BlueprintGenerationError, match="No visual grammar"):
        asyncio.run(generate_sprite_blueprint(spec("unknown", generation_mode="controlled"), strategy="auto"))
    with pytest.raises(BlueprintGenerationError, match="No visual grammar"):
        asyncio.run(generate_sprite_blueprint(spec("unknown"), strategy="procedural"))
