from __future__ import annotations

import asyncio
import json

import pytest

from app.schemas.sprite import AssetSpec
from app.services.llm_generation import LlmGenerationResult
from app.services.sprite import SpriteError, SpriteService
from app.services.sprite_artifact_store import SpriteArtifactStore
from app.services.sprite_blueprint import BlueprintGenerationError, generate_sprite_blueprint


class FakeLlm:
    def __init__(self, texts: list[str]) -> None:
        self.texts = texts
        self.calls: list[dict[str, object]] = []

    async def generate_text(self, **kwargs: object) -> LlmGenerationResult:
        self.calls.append(kwargs)
        return LlmGenerationResult(text=self.texts[len(self.calls) - 1], provider="fake", model="fake")


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


def _blueprint(*, profile: bool) -> str:
    primitives: list[dict[str, object]] = [
        {"op": "ellipse", "fill": "skin", "layer": "head", "bbox": [23, 7, 41, 28]},
        {"op": "rectangle", "fill": "metal", "layer": "torso", "bbox": [25, 28, 39, 45]},
    ]
    if profile:
        primitives[0] = {"op": "ellipse", "fill": "skin", "layer": "head", "bbox": [22, 7, 39, 28]}
        primitives.extend(
            [
                {"op": "polygon", "fill": "skin", "layer": "head", "points": [[38, 14], [49, 18], [38, 22]]},
                {"op": "line", "fill": "cloth", "layer": "pants", "points": [[28, 44], [22, 51], [23, 57]], "width": 5},
                {"op": "line", "fill": "cloth", "layer": "pants", "points": [[35, 44], [39, 50], [42, 57]], "width": 5},
            ]
        )
    else:
        primitives.extend(
            [
                {"op": "line", "fill": "cloth", "layer": "pants", "points": [[29, 44], [29, 57]], "width": 5},
                {"op": "line", "fill": "cloth", "layer": "pants", "points": [[35, 44], [35, 57]], "width": 5},
            ]
        )
    return json.dumps(
        {
            "recipe": "candidate",
            "subject": "warrior",
            "palette": {"skin": "#d49a6a", "metal": "#aebcca", "cloth": "#4267a8"},
            "material_roles": {"skin": "skin", "metal": "metal", "cloth": "cloth"},
            "primitives": primitives,
        }
    )


def test_llm_front_like_candidate_for_side_spec_triggers_one_semantic_repair() -> None:
    llm = FakeLlm([_blueprint(profile=False), _blueprint(profile=True)])

    generated = asyncio.run(generate_sprite_blueprint(_side_warrior_spec(), strategy="llm_blueprint", llm_service=llm))

    assert len(llm.calls) == 2
    assert generated.blueprint.recipe == "llm_blueprint"
    repair_payload = json.loads(str(llm.calls[1]["prompt"]))
    diagnostics = repair_payload["diagnostics"]
    assert diagnostics["semantic_issue_codes"] == [
        "side_view_symmetry_too_high",
        "side_view_missing_directional_feature",
    ]
    assert diagnostics["required_view"] == "side-view"
    assert diagnostics["direction"] == "right"
    assert repair_payload["untrusted_candidate"] == _blueprint(profile=False)
    assert repair_payload["asset_spec"]["game_view"] == "side-view"


def test_llm_semantic_repair_failure_returns_controlled_error() -> None:
    llm = FakeLlm([_blueprint(profile=False), _blueprint(profile=False)])

    with pytest.raises(BlueprintGenerationError, match="side_view_symmetry_too_high"):
        asyncio.run(generate_sprite_blueprint(_side_warrior_spec(), strategy="llm_blueprint", llm_service=llm))

    assert len(llm.calls) == 2


def test_service_marks_double_semantic_failure_without_success_files(tmp_path) -> None:
    llm = FakeLlm([_blueprint(profile=False), _blueprint(profile=False)])
    store = SpriteArtifactStore(data_dir=tmp_path / "data", items_dir=tmp_path / "items")
    artifact = store.create_asset_spec_artifact(prompt="warrior", asset_spec=_side_warrior_spec())

    with pytest.raises(SpriteError, match="side_view_symmetry_too_high"):
        asyncio.run(
            SpriteService(llm_service=llm, artifact_store=store).create_sprite_blueprint(
                artifact.artifact_id, strategy="llm_blueprint"
            )
        )

    failed = store.load_artifact(artifact.artifact_id)
    metadata = store.read_metadata(artifact.artifact_id)
    assert failed.status == "blueprint_failed"
    assert failed.blueprint_json_path is not None and not failed.blueprint_json_path.exists()
    assert failed.render_png_path is not None and not failed.render_png_path.exists()
    assert metadata["generation_error"]["issue_codes"] == [
        "side_view_symmetry_too_high",
        "side_view_missing_directional_feature",
    ]
