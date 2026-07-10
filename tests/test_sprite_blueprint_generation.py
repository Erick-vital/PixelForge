from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import ValidationError

from app.schemas.sprite import AssetSpec, SpriteBlueprint, SpritePrimitive
from app.services.llm_generation import LlmGenerationProviderError, LlmGenerationResult
from app.services.sprite import SpriteService
from app.services.sprite_artifact_store import SpriteArtifactStore
from app.services.sprite_blueprint import BlueprintGenerationError, generate_sprite_blueprint


def test_blueprint_without_outline_uses_legacy_disabled_default():
    blueprint = SpriteBlueprint.model_validate(
        {
            "recipe": "legacy",
            "subject": "legacy prop",
            "palette": {"base": "#123456"},
            "primitives": [{"op": "rectangle", "fill": "base", "bbox": [16, 16, 48, 48]}],
        }
    )

    assert blueprint.outline.enabled is False
    assert blueprint.outline.color_key == "outline"
    assert blueprint.outline.width == 1


def test_blueprint_accepts_a_bounded_outline_configuration():
    blueprint = SpriteBlueprint.model_validate(
        {
            "recipe": "outlined",
            "subject": "outlined prop",
            "palette": {"outline": "#101010", "base": "#123456"},
            "primitives": [{"op": "rectangle", "fill": "base", "bbox": [16, 16, 48, 48]}],
            "outline": {"enabled": True, "color_key": "outline", "width": 1},
        }
    )

    assert blueprint.outline.enabled is True
    assert blueprint.outline.width == 1


@pytest.mark.parametrize("width", [0, 5])
def test_blueprint_rejects_outline_width_outside_supported_range(width):
    with pytest.raises(ValidationError):
        SpriteBlueprint.model_validate(
            {
                "recipe": "outlined",
                "subject": "outlined prop",
                "palette": {"outline": "#101010", "base": "#123456"},
                "primitives": [{"op": "rectangle", "fill": "base", "bbox": [16, 16, 48, 48]}],
                "outline": {"enabled": True, "color_key": "outline", "width": width},
            }
        )


class FakeBlueprintLlm:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict[str, object]] = []

    async def generate_text(self, **kwargs: object) -> LlmGenerationResult:
        self.calls.append(kwargs)
        return LlmGenerationResult(text=self.text, provider="fake", model="fake-blueprint-model")


class SequencedBlueprintLlm:
    def __init__(self, texts: list[str]) -> None:
        self.texts = texts
        self.calls: list[dict[str, object]] = []

    async def generate_text(self, **kwargs: object) -> LlmGenerationResult:
        self.calls.append(kwargs)
        return LlmGenerationResult(text=self.texts[len(self.calls) - 1], provider="fake", model="fake-blueprint-model")


def _heart_spec() -> AssetSpec:
    return AssetSpec.model_validate(
        {
            "asset_type": "icon",
            "subject": "heart",
            "game_view": "icon/front",
            "style": "pixel art",
            "size": {"width": 64, "height": 64},
            "technical_constraints": {"pixel_art": True},
        }
    )


def test_llm_blueprint_generation_validates_and_normalizes_a_heart_blueprint():
    llm = FakeBlueprintLlm(
        """
        {
          "recipe": "heart icon",
          "subject": "red heart",
          "palette": {
            "outline": "#5a0d18",
            "base": "#d62839",
            "highlight": "#ff9aa2"
          },
          "primitives": [
            {"op": "polygon", "fill": "outline", "points": [[32, 54], [10, 33], [10, 20], [18, 12], [27, 12], [32, 19], [37, 12], [46, 12], [54, 20], [54, 33]]},
            {"op": "polygon", "fill": "base", "points": [[32, 50], [14, 31], [14, 22], [20, 16], [27, 16], [32, 23], [37, 16], [44, 16], [50, 22], [50, 31]]},
            {"op": "polygon", "fill": "highlight", "points": [[21, 20], [28, 20], [24, 29], [18, 27]]}
          ],
          "notes": ["heart health icon"]
        }
        """
    )

    generated = asyncio.run(generate_sprite_blueprint(_heart_spec(), strategy="llm_blueprint", seed=7, llm_service=llm))

    assert generated.strategy == "llm_blueprint"
    assert generated.blueprint.recipe == "llm_blueprint"
    assert generated.blueprint.subject == "heart"
    assert len(generated.blueprint.primitives) == 3
    assert generated.provider == "fake"
    assert generated.model == "fake-blueprint-model"
    assert llm.calls[0]["temperature"] == 0.0
    assert llm.calls[0]["max_tokens"] == 10_000


def test_llm_blueprint_generation_repairs_one_malformed_json_response():
    llm = SequencedBlueprintLlm(
        [
            '{"recipe":"plate","subject":"plate of food","palette":{"base":"#e8c39e"},"primitives":[{"op":"ellipse" "fill":"base","bbox":[4,4,60,60]}]}',
            '{"recipe":"plate","subject":"plate of food","palette":{"base":"#e8c39e"},"primitives":[{"op":"ellipse","fill":"base","bbox":[4,4,60,60]}]}',
        ]
    )

    generated = asyncio.run(generate_sprite_blueprint(_heart_spec(), strategy="llm_blueprint", seed=0, llm_service=llm))

    assert generated.blueprint.recipe == "llm_blueprint"
    assert len(llm.calls) == 2
    assert "Repair the candidate" in str(llm.calls[1]["system_prompt"])


def test_llm_blueprint_generation_rejects_an_undeclared_palette_fill():
    llm = FakeBlueprintLlm(
        """
        {
          "recipe": "bad heart",
          "subject": "heart",
          "palette": {"base": "#d62839"},
          "primitives": [
            {"op": "ellipse", "fill": "missing", "bbox": [12, 12, 52, 52]}
          ]
        }
        """
    )

    with pytest.raises(BlueprintGenerationError, match="unknown palette key"):
        asyncio.run(generate_sprite_blueprint(_heart_spec(), strategy="llm_blueprint", seed=0, llm_service=llm))


def test_auto_uses_known_procedural_recipe_without_an_llm_call():
    llm = FakeBlueprintLlm("this must not be used")
    dragon = AssetSpec.model_validate({"subject": "baby dragon", "size": {"width": 64, "height": 64}})

    generated = asyncio.run(generate_sprite_blueprint(dragon, strategy="auto", seed=3, llm_service=llm))

    assert generated.strategy == "procedural"
    assert generated.blueprint.recipe == "baby_dragon"
    assert llm.calls == []


def test_llm_blueprint_generation_wraps_provider_errors():
    class FailingBlueprintLlm:
        async def generate_text(self, **kwargs: object) -> LlmGenerationResult:
            raise LlmGenerationProviderError("provider unavailable")

    with pytest.raises(BlueprintGenerationError, match="provider unavailable"):
        asyncio.run(
            generate_sprite_blueprint(_heart_spec(), strategy="llm_blueprint", llm_service=FailingBlueprintLlm())
        )


def test_service_persists_llm_blueprint_generation_lineage(tmp_path):
    llm = FakeBlueprintLlm(
        """
        {
          "recipe": "heart icon",
          "subject": "heart",
          "palette": {"outline": "#5a0d18", "base": "#d62839"},
          "primitives": [
            {"op": "polygon", "fill": "outline", "points": [[32, 54], [10, 33], [10, 20], [18, 12], [27, 12], [32, 19], [37, 12], [46, 12], [54, 20], [54, 33]]},
            {"op": "polygon", "fill": "base", "points": [[32, 50], [14, 31], [14, 22], [20, 16], [27, 16], [32, 23], [37, 16], [44, 16], [50, 22], [50, 31]]}
          ]
        }
        """
    )
    store = SpriteArtifactStore(data_dir=tmp_path / "data", items_dir=tmp_path / "items")
    artifact = store.create_asset_spec_artifact(prompt="heart", asset_spec=_heart_spec())
    service = SpriteService(llm_service=llm, artifact_store=store)

    blueprint, saved_artifact = asyncio.run(
        service.create_sprite_blueprint(artifact.artifact_id, strategy="auto", seed=11)
    )

    metadata = json.loads((saved_artifact.artifact_dir / "metadata.json").read_text(encoding="utf-8"))
    assert blueprint.recipe == "llm_blueprint"
    assert saved_artifact.status == "blueprint_ready"
    assert metadata["created_at"]
    assert metadata["updated_at"]
    assert metadata["blueprint_generation"] == {
        "strategy": "llm_blueprint",
        "provider": "fake",
        "model": "fake-blueprint-model",
        "seed": 11,
    }


def test_render_sprite_prefers_a_persisted_blueprint_over_the_generic_recipe(tmp_path):
    store = SpriteArtifactStore(data_dir=tmp_path / "data", items_dir=tmp_path / "items")
    artifact = store.create_asset_spec_artifact(prompt="heart", asset_spec=_heart_spec())
    blueprint = SpriteBlueprint(
        recipe="llm_blueprint",
        subject="heart",
        palette={"outline": "#5a0d18", "base": "#d62839"},
        primitives=[
            SpritePrimitive(
                op="polygon", fill="outline", points=[(32, 54), (10, 20), (27, 12), (32, 19), (37, 12), (54, 20)]
            ),
            SpritePrimitive(
                op="polygon", fill="base", points=[(32, 50), (14, 22), (27, 16), (32, 23), (37, 16), (50, 22)]
            ),
        ],
    )
    store.save_blueprint(artifact.artifact_id, blueprint, generation={"strategy": "llm_blueprint", "seed": 0})

    png, report = SpriteService(artifact_store=store).render_sprite(artifact.artifact_id, seed=9)

    assert png
    assert report["recipe"] == "llm_blueprint"
