from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.routes import api as api_routes
from app.schemas.sprite import AssetSpec
from app.services.settings import MissingLlmApiKeyError, get_app_settings
from app.services.sprite_artifact_store import SpriteArtifactStore


def test_pages_render_with_active_menu():
    client = TestClient(app)

    home = client.get("/")
    assert home.status_code == 200
    assert "PixelForge" in home.text
    assert 'href="/sprite"' in home.text
    assert 'href="/settings"' in home.text
    assert 'href="/llm"' in home.text

    sprite = client.get("/sprite")
    assert sprite.status_code == 200
    assert 'hx-post="/ui/sprite/spec"' in sprite.text
    assert 'hx-target="#results"' in sprite.text
    assert 'name="blueprint_strategy"' in sprite.text
    assert '<option value="exploratory" selected>' in sprite.text
    assert "Creativo: blueprint diseñado por IA" in sprite.text
    assert "Prompt to Sprite" in sprite.text
    assert '<a href="/sprite" class="active" aria-current="page">' in sprite.text

    settings = client.get("/settings")
    assert settings.status_code == 200
    assert "APP_LLM_PROVIDER" in settings.text or "LLM" in settings.text


def test_sprite_api_turns_prompt_into_structured_asset_spec():
    response = TestClient(app).post(
        "/api/asset-spec",
        json={"prompt": "hazme un enemigo dragón bebé para un juego pixel art top-down, 64x64", "use_llm": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["artifact_id"].startswith("sprite_")
    assert body["asset_spec"]["subject"] == "baby dragon"
    assert body["asset_spec"]["size"] == {"width": 64, "height": 64}
    assert body["asset_spec"]["processing_profile"]["resize_mode"] == "nearest-neighbor"


def test_sprite_api_accepts_template_and_returns_persisted_decision_trace():
    response = TestClient(app).post(
        "/api/asset-spec",
        json={"prompt": "draw a warrior", "use_llm": False, "template_id": "warrior_side"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["asset_spec"]["game_view"] == "side-view"
    assert body["decision_trace"] == {
        "view_source": "template",
        "template_id": "warrior_side",
        "requested_view": None,
    }
    metadata = json.loads((Path(body["artifact_dir"]) / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["decision_trace"] == body["decision_trace"]


def test_sprite_api_without_view_returns_deterministic_front_decision():
    response = TestClient(app).post(
        "/api/asset-spec",
        json={"prompt": "draw a warrior", "use_llm": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["asset_spec"]["game_view"] == "icon/front"
    assert body["decision_trace"]["view_source"] == "default"


def test_sprite_htmx_form_returns_structured_asset_spec_json():
    response = TestClient(app).post(
        "/ui/sprite/spec",
        data={
            "prompt": "Quiero un caballero estilo pixel art, 64x64, vista frontal",
            "use_llm": "false",
            "generation_mode": "controlled",
            "blueprint_strategy": "procedural",
        },
    )

    assert response.status_code == 200
    assert "Sprite result" in response.text
    assert "Receta generada:" in response.text
    assert "Artifact ID:" in response.text
    assert "Blueprint JSON" in response.text
    assert '"subject": "human"' in response.text
    assert '"width": 64' in response.text
    assert '"resize_mode": "nearest-neighbor"' in response.text
    assert 'hx-post="/ui/sprite/render-blueprint"' in response.text
    assert 'name="artifact_id"' in response.text
    assert 'name="seed"' in response.text


def test_sprite_htmx_displays_requested_and_resolved_decisions():
    response = TestClient(app).post(
        "/ui/sprite/spec",
        data={
            "prompt": "draw a warrior",
            "use_llm": "false",
            "view": "side-view",
            "template_id": "warrior_side",
            "generation_mode": "controlled",
            "blueprint_strategy": "procedural",
        },
    )

    assert response.status_code == 200
    assert "Requested view:" in response.text
    assert "Resolved view:" in response.text
    assert "View source:" in response.text
    assert "Template:" in response.text
    assert "Requested strategy:" in response.text
    assert "Resolved strategy:" in response.text
    assert "Grammar/IA:" in response.text
    assert "Semantic report:" in response.text


def test_sprite_render_htmx_returns_preview_image():
    client = TestClient(app)
    artifact = client.post(
        "/api/asset-spec",
        json={"prompt": "Quiero un caballero estilo pixel art, 64x64, vista frontal", "use_llm": False},
    ).json()

    blueprint = client.post(
        "/api/blueprint",
        json={"artifact_id": artifact["artifact_id"], "strategy": "procedural", "seed": 123},
    ).json()

    response = client.post(
        "/ui/sprite/render-blueprint",
        data={"artifact_id": blueprint["artifact_id"], "seed": "123"},
    )

    assert response.status_code == 200
    assert "Procedural PNG preview" in response.text
    assert "data:image/png;base64," in response.text
    assert "humanoid_front/warrior" in response.text


def test_asset_spec_returns_service_unavailable_when_llm_credentials_are_missing():
    class MissingCredentialsSpriteService:
        async def create_asset_spec(self, payload):
            raise MissingLlmApiKeyError("Missing LLM API key")

    app.dependency_overrides[api_routes.get_sprite_service] = MissingCredentialsSpriteService
    try:
        response = TestClient(app).post("/api/asset-spec", json={"prompt": "draw a sprite"})
    finally:
        app.dependency_overrides.pop(api_routes.get_sprite_service, None)

    assert response.status_code == 503
    assert response.json() == {"detail": "Missing LLM API key"}


def test_blueprint_returns_bad_request_for_an_invalid_persisted_asset_spec():
    settings = get_app_settings()
    store = SpriteArtifactStore(data_dir=settings.data_dir, items_dir=settings.items_dir)
    asset_spec = AssetSpec.model_validate(
        {
            "subject": "human",
            "family": "humanoid",
            "game_view": "icon/front",
            "character": {"pose": {"stance": "front_neutral"}},
        }
    )
    artifact = store.create_asset_spec_artifact(prompt="human", asset_spec=asset_spec)
    stored_spec = json.loads(artifact.asset_spec_json_path.read_text(encoding="utf-8"))
    stored_spec["character"]["pose"]["stance"] = "side_neutral"
    artifact.asset_spec_json_path.write_text(json.dumps(stored_spec), encoding="utf-8")

    response = TestClient(app).post(
        "/api/blueprint", json={"artifact_id": artifact.artifact_id, "strategy": "procedural"}
    )

    assert response.status_code == 400
    assert "invalid Asset Spec" in response.json()["detail"]
