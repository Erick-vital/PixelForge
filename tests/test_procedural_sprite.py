from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.schemas.sprite import AssetSpec, SpriteBlueprint, SpritePrimitive
from app.services.procedural_sprite import build_sprite_blueprint, render_blueprint, render_procedural_sprite


def _baby_dragon_spec() -> AssetSpec:
    return AssetSpec.model_validate(
        {
            "asset_type": "enemy",
            "subject": "baby dragon",
            "game_view": "top-down 3/4",
            "style": "pixel art fantasy",
            "size": {"width": 64, "height": 64},
            "palette": {
                "main": ["orange", "dark red", "gold"],
                "shadows": ["purple", "dark blue"],
                "accent": ["yellow glow"],
            },
            "shape": {"silhouette": "small compact dragon with large head, tiny wings, curled tail", "proportions": {}},
            "technical_constraints": {
                "transparent_background": True,
                "pixel_art": True,
                "readable_at_small_size": True,
            },
        }
    )


def test_procedural_renderer_creates_deterministic_transparent_png_for_baby_dragon():
    spec = _baby_dragon_spec()

    blueprint = build_sprite_blueprint(spec, seed=123)
    assert blueprint.recipe == "baby_dragon"
    assert blueprint.primitives

    first = render_procedural_sprite(spec, seed=123)
    second = render_procedural_sprite(spec, seed=123)

    assert first.png_bytes == second.png_bytes
    image = Image.open(io.BytesIO(first.png_bytes))
    assert image.size == (64, 64)
    assert image.mode == "RGBA"
    assert image.getbbox() is not None
    assert first.report["width"] == 64
    assert first.report["height"] == 64
    assert first.report["transparent"] is True
    assert first.report["non_empty"] is True
    assert first.report["color_count"] <= 24
    assert "baby_dragon" in first.report["recipe"]


def test_renderer_draws_a_general_blueprint_without_subject_specific_code():
    blueprint = SpriteBlueprint(
        recipe="custom_blueprint",
        subject="mana gem",
        palette={
            "outline": "#10131f",
            "base": "#5b7cfa",
            "highlight": "#b7d4ff",
        },
        primitives=[
            SpritePrimitive(op="ellipse", bbox=(16, 16, 48, 48), fill="outline"),
            SpritePrimitive(op="ellipse", bbox=(19, 19, 45, 45), fill="base"),
            SpritePrimitive(op="polygon", points=[(32, 12), (42, 32), (32, 52), (22, 32)], fill="highlight"),
            SpritePrimitive(op="line", points=[(32, 18), (32, 46)], fill="outline", width=1),
        ],
        notes=["manual blueprint for renderer coverage"],
    )

    result = render_blueprint(blueprint, width=64, height=64, seed=0)
    image = Image.open(io.BytesIO(result.png_bytes))
    assert image.size == (64, 64)
    assert image.mode == "RGBA"
    assert image.getbbox() is not None
    assert result.report["recipe"] == "custom_blueprint"
    assert result.report["primitive_count"] == 4


def test_procedural_renderer_supports_first_phase_subject_recipes():
    cases = [
        ("potion", "potion"),
        ("sword", "sword"),
        ("baby dragon", "baby_dragon"),
    ]

    for subject, recipe in cases:
        spec = AssetSpec.model_validate({"subject": subject, "size": {"width": 64, "height": 64}})
        result = render_procedural_sprite(spec, seed=7)
        image = Image.open(io.BytesIO(result.png_bytes))
        assert image.size == (64, 64)
        assert image.getbbox() is not None
        assert result.report["recipe"] == recipe
        assert result.report["color_count"] <= 24


@pytest.mark.parametrize("size", [32, 128])
@pytest.mark.parametrize("subject", ["baby dragon", "potion", "sword", "mystery prop"])
def test_procedural_render_scales_content_with_canvas_size(subject, size):
    base_spec = AssetSpec.model_validate({"subject": subject, "size": {"width": 64, "height": 64}})
    spec = AssetSpec.model_validate({"subject": subject, "size": {"width": size, "height": size}})

    base_bbox = Image.open(io.BytesIO(render_procedural_sprite(base_spec, seed=5).png_bytes)).getbbox()
    bbox = Image.open(io.BytesIO(render_procedural_sprite(spec, seed=5).png_bytes)).getbbox()

    assert base_bbox is not None
    assert bbox is not None
    scale = size / 64
    tolerance = max(2, 2 * scale)
    for base_coord, coord in zip(base_bbox, bbox, strict=True):
        assert abs(coord - base_coord * scale) <= tolerance


@pytest.mark.parametrize("subject", ["potion", "sword", "baby dragon"])
def test_seed_changes_procedural_render(subject):
    spec = AssetSpec.model_validate({"subject": subject, "size": {"width": 64, "height": 64}})
    renders = {render_procedural_sprite(spec, seed=seed).png_bytes for seed in range(6)}
    assert len(renders) > 1


def test_render_blueprint_endpoint_rejects_unsupported_sizes():
    spec = _baby_dragon_spec().model_dump(mode="json")
    client = TestClient(app)
    blueprint = client.post("/api/blueprint", json={"asset_spec": spec, "seed": 0}).json()

    response = client.post("/api/render-blueprint", json={"blueprint": blueprint, "width": 50, "height": 64, "seed": 0})
    assert response.status_code == 422


def test_render_sprite_endpoint_returns_png_from_asset_spec():
    response = TestClient(app).post(
        "/api/render-sprite",
        json={"asset_spec": _baby_dragon_spec().model_dump(mode="json"), "seed": 123},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-pixelforge-render-recipe"] == "baby_dragon"
    assert response.headers["x-pixelforge-validation-size"] == "64x64"
    image = Image.open(io.BytesIO(response.content))
    assert image.size == (64, 64)
    assert image.getbbox() is not None


def test_blueprint_and_render_blueprint_endpoints_round_trip():
    client = TestClient(app)
    spec = _baby_dragon_spec().model_dump(mode="json")

    blueprint_response = client.post("/api/blueprint", json={"asset_spec": spec, "seed": 55})
    assert blueprint_response.status_code == 200
    blueprint = blueprint_response.json()
    assert blueprint["recipe"] == "baby_dragon"
    assert blueprint["primitives"]

    render_response = client.post(
        "/api/render-blueprint",
        json={"blueprint": blueprint, "width": 64, "height": 64, "seed": 55},
    )
    assert render_response.status_code == 200
    assert render_response.headers["content-type"] == "image/png"
    assert render_response.headers["x-pixelforge-render-recipe"] == "baby_dragon"
    image = Image.open(io.BytesIO(render_response.content))
    assert image.size == (64, 64)
