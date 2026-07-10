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


def test_outline_pass_adds_a_one_pixel_ring_without_changing_the_shape_interior():
    blueprint = SpriteBlueprint(
        recipe="outlined_square",
        subject="outlined square",
        palette={"outline": "#101010", "base": "#5b7cfa"},
        primitives=[SpritePrimitive(op="rectangle", bbox=(20, 20, 43, 43), fill="base")],
        outline={"enabled": True, "color_key": "outline", "width": 1},
    )

    image = Image.open(io.BytesIO(render_blueprint(blueprint, width=64, height=64).png_bytes)).convert("RGBA")

    assert image.getpixel((20, 20)) == (91, 124, 250, 255)
    assert image.getpixel((19, 20)) == (16, 16, 16, 255)
    assert image.getpixel((20, 19)) == (16, 16, 16, 255)
    assert image.getpixel((19, 19)) == (16, 16, 16, 255)
    assert image.getpixel((18, 20))[3] == 0


def test_outline_pass_does_not_wrap_when_a_shape_touches_canvas_edge():
    blueprint = SpriteBlueprint(
        recipe="edge_square",
        subject="edge square",
        palette={"outline": "#101010", "base": "#5b7cfa"},
        primitives=[SpritePrimitive(op="rectangle", bbox=(0, 20, 3, 23), fill="base")],
        outline={"enabled": True, "color_key": "outline", "width": 1},
    )

    image = Image.open(io.BytesIO(render_blueprint(blueprint, width=64, height=64).png_bytes)).convert("RGBA")

    assert image.getpixel((63, 20))[3] == 0
    assert image.getpixel((4, 20)) == (16, 16, 16, 255)


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


def test_render_blueprint_endpoint_rejects_unknown_artifact_id():
    response = TestClient(app).post("/api/render-blueprint", json={"artifact_id": "sprite_missing", "seed": 0})
    assert response.status_code == 400


def test_render_sprite_endpoint_returns_png_from_asset_artifact():
    client = TestClient(app)
    artifact = client.post(
        "/api/asset-spec",
        json={"prompt": "hazme un enemigo dragón bebé para un juego pixel art top-down, 64x64", "use_llm": False},
    ).json()

    response = client.post("/api/render-sprite", json={"artifact_id": artifact["artifact_id"], "seed": 123})

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-pixelforge-render-recipe"] == "baby_dragon"
    assert response.headers["x-pixelforge-validation-size"] == "64x64"
    assert response.headers["x-pixelforge-artifact-id"] == artifact["artifact_id"]
    image = Image.open(io.BytesIO(response.content))
    assert image.size == (64, 64)
    assert image.getbbox() is not None


def test_blueprint_and_render_blueprint_endpoints_round_trip():
    client = TestClient(app)
    artifact = client.post(
        "/api/asset-spec",
        json={"prompt": "hazme un enemigo dragón bebé para un juego pixel art top-down, 64x64", "use_llm": False},
    ).json()

    blueprint_response = client.post("/api/blueprint", json={"artifact_id": artifact["artifact_id"], "seed": 55})
    assert blueprint_response.status_code == 200
    blueprint = blueprint_response.json()
    assert blueprint["artifact_id"] == artifact["artifact_id"]
    assert blueprint["blueprint"]["recipe"] == "baby_dragon"
    assert blueprint["blueprint"]["primitives"]

    render_response = client.post(
        "/api/render-blueprint",
        json={"artifact_id": artifact["artifact_id"], "seed": 55},
    )
    assert render_response.status_code == 200
    assert render_response.headers["content-type"] == "image/png"
    assert render_response.headers["x-pixelforge-render-recipe"] == "baby_dragon"
    assert render_response.headers["x-pixelforge-artifact-id"] == artifact["artifact_id"]
    image = Image.open(io.BytesIO(render_response.content))
    assert image.size == (64, 64)
