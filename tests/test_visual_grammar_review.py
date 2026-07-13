from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.sprite import AssetSpec, SpriteBlueprint
from app.services.llm_generation import LlmGenerationResult
from app.services.sprite_blueprint import generate_sprite_blueprint
from app.sprite_engine.character.quadruped_skeleton import build_quadruped_skeleton
from app.sprite_engine.character.quadruped_spec import QuadrupedSpec
from app.sprite_engine.grammar import default_grammar_registry
from app.sprite_engine.grammar.classification import classify_subject

FIXTURES = Path(__file__).parent / "fixtures" / "grammar_specs"


class FakeLlm:
    calls: list[dict[str, object]]

    def __init__(self) -> None:
        self.calls = []

    async def generate_text(self, **kwargs: object) -> LlmGenerationResult:
        self.calls.append(kwargs)
        return LlmGenerationResult(
            text='{"recipe":"free","subject":"cloud","palette":{"base":"#6699cc"},'
            '"primitives":[{"op":"ellipse","fill":"base","layer":"base","bbox":[12,12,52,52]}],'
            '"layer_order":["base"],"material_roles":{"base":"cloth"},"lighting_direction":"top_right"}',
            provider="fake",
            model="fake",
        )


def test_semantic_interpretation_contracts_forbid_free_geometry():
    for field in ("primitives", "points", "bbox", "anchors"):
        with pytest.raises(ValidationError):
            AssetSpec.model_validate({"subject": "warrior", field: []})
    with pytest.raises(ValidationError):
        AssetSpec.model_validate({"character": {"anatomy": {"anchor": [1, 2]}}})


def test_pose_capability_is_part_of_full_registry_resolution():
    front_wrong_pose = AssetSpec(
        family="humanoid",
        archetype="warrior",
        character={"pose": {"stance": "side_neutral"}},
    )
    assert not default_grammar_registry.resolve(front_wrong_pose).supported
    with pytest.raises(ValidationError, match="pose contradicts game_view"):
        AssetSpec(
            family="humanoid",
            archetype="warrior",
            game_view="side-view",
            character={"pose": {"stance": "front_neutral"}},
        )
    side_default = AssetSpec(family="humanoid", archetype="warrior", game_view="side-view", character={})
    assert side_default.character and side_default.character.pose.stance == "side_neutral"
    assert default_grammar_registry.resolve(side_default).grammar_name == "humanoid_side"


def test_front_slots_have_typed_geometry_and_preserve_explicit_choices():
    warrior = default_grammar_registry.compile(
        AssetSpec(family="humanoid", archetype="warrior", character={"equipment": {"hand": "hammer"}}), seed=9
    )
    wizard = default_grammar_registry.compile(AssetSpec(family="humanoid", archetype="wizard"), seed=9)
    assert any(p.layer == "back_equipment" and p.op == "ellipse" for p in warrior.primitives)  # shield
    assert not any(p.layer == "front_equipment" and p.fill == "equipment_metal" for p in warrior.primitives)
    assert any(p.layer == "hair" and p.op == "polygon" for p in wizard.primitives)
    assert any(p.layer == "pants" and p.op == "polygon" for p in wizard.primitives)
    heavy_boots = [p for p in warrior.primitives if p.layer == "boots" and p.bbox]
    assert max(p.bbox[3] for p in heavy_boots if p.bbox) == 58
    assert warrior.layer_order.index("back_equipment") < warrior.layer_order.index("front_equipment")


def test_quadruped_all_typed_fields_change_geometry_and_mirror():
    baseline = build_quadruped_skeleton(QuadrupedSpec())
    variants = [
        QuadrupedSpec(body_length="long"),
        QuadrupedSpec(body_depth="heavy"),
        QuadrupedSpec(leg_length="long"),
        QuadrupedSpec(head_shape="wedge"),
        QuadrupedSpec(snout_length="long"),
        QuadrupedSpec(ear_shape="upright"),
    ]
    assert all(build_quadruped_skeleton(value) != baseline for value in variants)
    left = build_quadruped_skeleton(QuadrupedSpec(direction="left"))
    assert left.snout_anchor[0] < left.head_center[0]
    for tail in ("curly", "straight", "bushy"):
        blueprint = default_grammar_registry.compile(
            AssetSpec(
                family="quadruped",
                archetype="pig",
                game_view="side-view",
                quadruped=QuadrupedSpec(tail_shape=tail),
            ),
            seed=3,
        )
        legs = [p for p in blueprint.primitives if p.layer == "pants"]
        assert len(legs) == 4 and all(p.points[-1][1] == 55 for p in legs)


def test_exploratory_lineage_is_explicit_even_with_capability_match():
    llm = FakeLlm()
    generated = asyncio.run(
        generate_sprite_blueprint(
            AssetSpec(family="humanoid", archetype="warrior", generation_mode="exploratory"),
            strategy="auto",
            llm_service=llm,
        )
    )
    assert generated.strategy == "llm_blueprint"
    assert generated.fallback_reason == "explicit exploratory generation mode"
    assert generated.blueprint.material_roles == {"base": "cloth"}
    assert generated.blueprint.lighting_direction == "top_right"


def test_benchmark_fixtures_are_reproducible_and_bounded():
    for path in sorted(FIXTURES.glob("*.json")):
        spec = AssetSpec.model_validate(json.loads(path.read_text(encoding="utf-8")))
        resolution = default_grammar_registry.resolve(spec)
        assert resolution.supported, path.name
        first = default_grammar_registry.compile(spec, seed=17)
        assert first == default_grammar_registry.compile(spec, seed=17)
        for primitive in first.primitives:
            coordinates = list(primitive.points)
            if primitive.bbox:
                x0, y0, x1, y1 = primitive.bbox
                coordinates.extend([(x0, y0), (x1, y1)])
            assert all(0 <= value <= 63 for point in coordinates for value in point)


def test_classification_matches_lexical_tokens_not_substrings():
    assert classify_subject("swordfish cloud").family == "unknown"
    assert classify_subject("a sword icon").archetype == "sword"


def test_historical_blueprint_defaults_remain_render_compatible():
    blueprint = SpriteBlueprint.model_validate(
        {
            "recipe": "historical",
            "subject": "old",
            "palette": {"base": "#123456"},
            "primitives": [{"op": "rectangle", "fill": "base", "bbox": [10, 10, 20, 20]}],
        }
    )
    assert blueprint.lighting_direction == "top_left"
    assert blueprint.material_roles == {}
