from __future__ import annotations

import asyncio
import json
import logging

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.sprite import AssetSpec
from app.services.llm_generation import LlmGenerationResult
from app.services.logging_config import JsonFormatter
from app.services.sprite import SpriteService
from app.services.sprite_artifact_store import SpriteArtifactStore
from app.services.trace_context import log_context


class FakeBlueprintLlm:
    async def generate_text(self, **kwargs: object) -> LlmGenerationResult:
        return LlmGenerationResult(
            text=(
                '{"recipe":"heart","subject":"heart","palette":{"base":"#d62839"},'
                '"primitives":[{"op":"ellipse","fill":"base","bbox":[16,16,48,48]}]}'
            ),
            provider="fake",
            model="fake-model",
        )


def _heart_spec() -> AssetSpec:
    return AssetSpec.model_validate(
        {
            "asset_type": "icon",
            "subject": "heart",
            "game_view": "icon/front",
            "size": {"width": 64, "height": 64},
        }
    )


def test_json_formatter_includes_active_trace_context() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "completed", (), None)

    with log_context(request_id="req_test", operation_id="op_test", artifact_id="sprite_test"):
        payload = json.loads(JsonFormatter().format(record))

    assert payload["request_id"] == "req_test"
    assert payload["operation_id"] == "op_test"
    assert payload["artifact_id"] == "sprite_test"


def test_http_middleware_returns_and_logs_request_id() -> None:
    response = TestClient(app).get("/health", headers={"X-Request-Id": "req_client"})

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "req_client"


def test_artifact_trace_records_blueprint_and_render_lifecycle(tmp_path) -> None:
    store = SpriteArtifactStore(data_dir=tmp_path / "data", items_dir=tmp_path / "items")
    artifact = store.create_asset_spec_artifact(prompt="heart", asset_spec=_heart_spec())
    service = SpriteService(llm_service=FakeBlueprintLlm(), artifact_store=store)

    asyncio.run(service.create_sprite_blueprint(artifact.artifact_id, strategy="llm_blueprint", seed=7))
    service.render_blueprint(artifact.artifact_id, seed=7)

    events = store.read_trace_events(artifact.artifact_id)

    assert [event["event_type"] for event in events] == [
        "artifact.created",
        "blueprint.generation.started",
        "blueprint.generation.completed",
        "render.started",
        "render.completed",
    ]
    assert all(event["event_schema_version"] == 1 for event in events)
    assert all(event["artifact_id"] == artifact.artifact_id for event in events)
    assert events[2]["details"]["duration_ms"] >= 0
    assert events[2]["details"]["provider"] == "fake"
    assert events[4]["details"]["output_bytes"] > 0
