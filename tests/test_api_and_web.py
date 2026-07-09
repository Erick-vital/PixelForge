from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


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
    assert 'Prompt to Sprite Processing Instructions' in sprite.text
    assert '<a href="/sprite" class="active" aria-current="page">' in sprite.text

    settings = client.get("/settings")
    assert settings.status_code == 200
    assert "APP_LLM_PROVIDER" in settings.text or "LLM" in settings.text


def test_sprite_api_turns_prompt_into_structured_asset_spec():
    response = TestClient(app).post(
        "/api/asset-spec",
        json={"prompt": "hazme un enemigo dragón bebé para un juego pixel art top-down, 64x64"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["subject"] == "baby dragon"
    assert body["size"] == {"width": 64, "height": 64}
    assert body["processing_profile"]["resize_mode"] == "nearest-neighbor"


def test_sprite_htmx_form_returns_structured_asset_spec_json():
    response = TestClient(app).post(
        "/ui/sprite/spec",
        data={"prompt": "Quiero un dragón pequeño estilo pixel art, 64x64, para un RPG top-down"},
    )

    assert response.status_code == 200
    assert "Sprite result" in response.text
    assert '"subject": "baby dragon"' in response.text
    assert '"width": 64' in response.text
    assert '"resize_mode": "nearest-neighbor"' in response.text
    assert "Generation prompt JSON" in response.text
    assert "Processing plan JSON" in response.text
