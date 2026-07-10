from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app


def test_asset_spec_endpoint_creates_sprite_artifact_and_structured_pixel_art_spec():
    response = TestClient(app).post(
        "/api/asset-spec",
        json={"prompt": "hazme un enemigo dragón bebé para un juego pixel art top-down, 64x64"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["artifact_id"].startswith("sprite_")
    assert body["status"] == "asset_spec_ready"
    assert body["subject"] == "baby dragon"
    assert body["asset_spec"]["asset_type"] == "enemy"
    assert body["asset_spec"]["game_view"] == "top-down 3/4"
    assert body["asset_spec"]["style"] == "pixel art fantasy"
    assert body["asset_spec"]["size"] == {"width": 64, "height": 64}
    assert body["asset_spec"]["technical_constraints"]["transparent_background"] is True
    assert body["asset_spec"]["technical_constraints"]["pixel_art"] is True
    assert body["asset_spec"]["prompt_guidance"]["target_prompt_tone"] == "concise game-asset prompt"
    assert body["asset_spec"]["processing_profile"]["resize_mode"] == "nearest-neighbor"
    assert body["asset_spec"]["processing_profile"]["palette_max_colors"] == 24


def test_blueprint_endpoint_uses_sprite_artifact_id_and_persists_blueprint():
    client = TestClient(app)
    artifact = client.post(
        "/api/asset-spec",
        json={"prompt": "Quiero un dragón pequeño estilo pixel art, 64x64, para un RPG top-down"},
    ).json()

    response = client.post("/api/blueprint", json={"artifact_id": artifact["artifact_id"], "seed": 123})

    assert response.status_code == 200
    body = response.json()
    assert body["artifact_id"] == artifact["artifact_id"]
    assert body["status"] == "blueprint_ready"
    assert body["asset_spec"]["subject"] == "baby dragon"
    assert body["blueprint"]["recipe"] == "baby_dragon"
    assert body["blueprint"]["subject"] == "baby dragon"
    assert len(body["blueprint"]["primitives"]) > 0


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
