from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app


def test_asset_spec_endpoint_turns_prompt_into_structured_pixel_art_spec():
    response = TestClient(app).post(
        "/api/asset-spec",
        json={"prompt": "hazme un enemigo dragón bebé para un juego pixel art top-down, 64x64"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["asset_type"] == "enemy"
    assert body["subject"] == "baby dragon"
    assert body["game_view"] == "top-down 3/4"
    assert body["style"] == "pixel art fantasy"
    assert body["size"] == {"width": 64, "height": 64}
    assert body["technical_constraints"]["transparent_background"] is True
    assert body["technical_constraints"]["pixel_art"] is True
    assert body["prompt_guidance"]["target_prompt_tone"] == "concise game-asset prompt"
    assert body["processing_profile"]["resize_mode"] == "nearest-neighbor"
    assert body["processing_profile"]["palette_max_colors"] == 24


def test_generation_prompt_endpoint_creates_positive_and_negative_prompts():
    client = TestClient(app)
    spec = client.post(
        "/api/asset-spec",
        json={"prompt": "Quiero un dragón pequeño estilo pixel art, 64x64, para RPG top-down"},
    ).json()

    response = client.post("/api/generation-prompt", json={"asset_spec": spec})

    assert response.status_code == 200
    body = response.json()
    assert "64x64 pixel art sprite" in body["prompt"]
    assert "baby dragon" in body["prompt"]
    assert "top-down 3/4 view" in body["prompt"]
    assert "transparent background" in body["prompt"]
    assert "blurry" in body["negative_prompt"]
    assert "watermark" in body["negative_prompt"]


def test_generation_prompt_respects_prompt_guidance_flags():
    client = TestClient(app)
    spec = client.post(
        "/api/asset-spec",
        json={"prompt": "Quiero un dragón pequeño estilo pixel art, 64x64, para RPG top-down"},
    ).json()
    spec["prompt_guidance"].update({"include_size": False, "include_style": False, "include_negative_prompt": False})

    response = client.post("/api/generation-prompt", json={"asset_spec": spec})

    assert response.status_code == 200
    body = response.json()
    assert "64x64" not in body["prompt"]
    assert spec["style"] not in body["prompt"]
    assert "transparent background" in body["prompt"]
    assert body["negative_prompt"] == ""


def test_processing_plan_endpoint_returns_standard_pixel_art_pipeline_steps():
    spec = {
        "asset_type": "enemy",
        "subject": "baby dragon",
        "game_view": "top-down 3/4",
        "style": "pixel art fantasy",
        "size": {"width": 64, "height": 64},
        "palette": {"main": ["orange", "gold"], "shadows": ["purple"], "accent": ["yellow glow"]},
        "shape": {"silhouette": "small compact dragon", "proportions": {}},
        "technical_constraints": {"transparent_background": True, "pixel_art": True, "readable_at_small_size": True},
    }

    response = TestClient(app).post("/api/processing-plan", json={"asset_spec": spec})

    assert response.status_code == 200
    steps = response.json()["steps"]
    assert [step["name"] for step in steps] == [
        "canvas_setup",
        "sprite_positioning",
        "pixel_art_resize",
        "palette_limit",
        "export",
    ]
    assert "64x64 transparent canvas" in steps[0]["instruction"]
    assert "nearest-neighbor" in steps[2]["instruction"]
    assert "24 colors" in steps[3]["instruction"]


def test_process_sprite_endpoint_resizes_centers_and_returns_png_with_validation_report():
    source = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    for x in range(4, 12):
        for y in range(4, 12):
            source.putpixel((x, y), (255, 128, 0, 255))
    buffer = io.BytesIO()
    source.save(buffer, format="PNG")
    buffer.seek(0)

    spec = '{"size":{"width":64,"height":64},"technical_constraints":{"transparent_background":true,"pixel_art":true}}'
    response = TestClient(app).post(
        "/api/process-sprite",
        data={"asset_spec_json": spec},
        files={"image": ("dragon.png", buffer, "image/png")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    processed = Image.open(io.BytesIO(response.content))
    assert processed.size == (64, 64)
    assert processed.mode == "RGBA"
    assert processed.getbbox() is not None
    assert response.headers["x-pixelforge-validation-size"] == "64x64"
    assert response.headers["x-pixelforge-validation-transparent"] == "true"
