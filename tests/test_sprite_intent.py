from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import ValidationError

from app.schemas.sprite import AssetSpec, AssetSpecRequest
from app.services.sprite_interpretation import create_asset_spec_from_request_with_trace
from app.sprite_engine.grammar.templates import TemplateResolutionError, resolve_template


class FakeLlm:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    async def generate_text(self, **kwargs: object):  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        return type("LlmResult", (), {"text": json.dumps(self.payload)})()


def llm_spec(*, view: str = "side-view", stance: str = "front_neutral") -> FakeLlm:
    return FakeLlm(
        {
            "subject": "warrior",
            "game_view": view,
            "character": {"pose": {"stance": stance}},
        }
    )


def test_explicit_request_view_overrides_llm_view() -> None:
    spec, trace = asyncio.run(
        create_asset_spec_from_request_with_trace(
            AssetSpecRequest(prompt="draw a warrior", view="icon/front"),
            llm_spec(),
        )
    )

    assert spec.game_view == "icon/front"
    assert spec.character is not None
    assert spec.character.pose.stance == "front_neutral"
    assert trace.view_source == "explicit"
    assert trace.requested_view == "icon/front"


def test_unspecified_humanoid_view_uses_stable_front_default() -> None:
    spec, trace = asyncio.run(
        create_asset_spec_from_request_with_trace(AssetSpecRequest(prompt="draw a warrior"), llm_spec())
    )

    assert spec.game_view == "icon/front"
    assert trace.view_source == "default"


def test_template_precedes_explicit_request_view_and_normalizes_pose() -> None:
    spec, trace = asyncio.run(
        create_asset_spec_from_request_with_trace(
            AssetSpecRequest(prompt="draw a warrior", view="icon/front", template_id="warrior_side"),
            llm_spec(view="icon/front"),
        )
    )

    assert spec.family == "humanoid"
    assert spec.archetype == "warrior"
    assert spec.game_view == "side-view"
    assert spec.character is not None
    assert spec.character.pose.stance == "side_neutral"
    assert trace.view_source == "template"
    assert trace.template_id == "warrior_side"


def test_template_constrains_semantics_without_forcing_procedural_generation() -> None:
    llm = FakeLlm({"subject": "wizard", "character": {}})
    spec, trace = asyncio.run(
        create_asset_spec_from_request_with_trace(
            AssetSpecRequest(prompt="draw a wizard", template_id="wizard_front"),
            llm,
        )
    )

    assert spec.family == "humanoid"
    assert spec.archetype == "wizard"
    assert spec.game_view == "icon/front"
    assert spec.generation_mode == "exploratory"
    assert trace.template_id == "wizard_front"


def test_wizard_interpretation_reconciles_generic_fields_to_conventional_wizard() -> None:
    llm = FakeLlm(
        {
            "subject": "wizard",
            "shape": {"silhouette": "tall robed figure with pointed hat"},
            "character": {
                "clothing": {"headwear": "none", "upper": "tunic", "lower": "work_pants"},
                "equipment": {"hand": "none"},
            },
        }
    )

    spec, _ = asyncio.run(create_asset_spec_from_request_with_trace(AssetSpecRequest(prompt="draw a wizard"), llm))

    assert spec.character is not None
    assert spec.character.clothing.headwear == "wizard_hat"
    assert spec.character.clothing.upper == "robe"
    assert spec.character.clothing.lower == "robe_lower"
    assert spec.character.equipment.hand == "staff"


def test_wizard_reconciliation_preserves_explicit_user_replacements() -> None:
    llm = FakeLlm(
        {
            "subject": "wizard",
            "character": {
                "clothing": {"headwear": "none", "upper": "tunic", "lower": "trousers"},
                "equipment": {"hand": "hammer"},
            },
        }
    )

    spec, _ = asyncio.run(
        create_asset_spec_from_request_with_trace(
            AssetSpecRequest(prompt="draw a wizard without a hat holding a hammer"), llm
        )
    )

    assert spec.character is not None
    assert spec.character.clothing.headwear == "none"
    assert spec.character.equipment.hand == "hammer"


def test_wizard_reconciliation_preserves_explicit_staff_exclusion_or_replacement() -> None:
    llm = FakeLlm(
        {
            "subject": "wizard",
            "character": {
                "clothing": {"headwear": "none", "upper": "tunic", "lower": "trousers"},
                "equipment": {"hand": "none"},
            },
        }
    )

    spec, _ = asyncio.run(
        create_asset_spec_from_request_with_trace(AssetSpecRequest(prompt="mago sin bastón con una varita"), llm)
    )

    assert spec.character is not None
    assert spec.character.equipment.hand == "none"


def test_wolf_interpretation_populates_typed_quadruped_spec() -> None:
    llm = FakeLlm({"subject": "wolf", "game_view": "side-view", "quadruped": None})

    spec, _ = asyncio.run(create_asset_spec_from_request_with_trace(AssetSpecRequest(prompt="draw a wolf"), llm))

    assert spec.family == "quadruped"
    assert spec.quadruped is not None
    assert spec.quadruped.body_length == "long"
    assert spec.quadruped.head_shape == "wedge"
    assert spec.quadruped.snout_length == "long"
    assert spec.quadruped.ear_shape == "upright"
    assert spec.quadruped.tail_shape == "bushy"


def test_wolf_interpretation_merges_partial_anatomy_with_wolf_defaults() -> None:
    llm = FakeLlm({"subject": "wolf", "quadruped": {"tail_shape": "straight"}})

    spec, _ = asyncio.run(create_asset_spec_from_request_with_trace(AssetSpecRequest(prompt="create a wolf"), llm))

    assert spec.quadruped is not None
    assert spec.quadruped.head_shape == "wedge"
    assert spec.quadruped.snout_length == "long"
    assert spec.quadruped.tail_shape == "straight"


def test_asset_spec_prompt_requires_semantic_character_consistency() -> None:
    llm = FakeLlm({"subject": "wizard", "character": {}})

    asyncio.run(create_asset_spec_from_request_with_trace(AssetSpecRequest(prompt="draw a wizard"), llm))

    system_prompt = str(llm.calls[0]["system_prompt"])
    assert "wizard_hat" in system_prompt
    assert "staff" in system_prompt
    assert "semantically consistent" in system_prompt


def test_warrior_side_template_sets_required_constraints() -> None:
    result = resolve_template("warrior_side")

    assert result.constraints == {
        "family": "humanoid",
        "archetype": "warrior",
        "game_view": "side-view",
        "character.pose.stance": "side_neutral",
    }


def test_unknown_template_is_a_controlled_request_error() -> None:
    with pytest.raises(TemplateResolutionError, match="unknown template"):
        resolve_template("warrior_3d")


@pytest.mark.parametrize(
    ("view", "stance"),
    [("side-view", "front_neutral"), ("icon/front", "side_neutral")],
)
def test_incompatible_explicit_view_and_pose_is_rejected(view: str, stance: str) -> None:
    with pytest.raises(ValidationError, match="pose contradicts game_view"):
        AssetSpec(game_view=view, character={"pose": {"stance": stance}})


def test_view_with_omitted_humanoid_pose_is_reconciled() -> None:
    spec = AssetSpec(game_view="side-view", character={})

    assert spec.character is not None
    assert spec.character.pose.stance == "side_neutral"
