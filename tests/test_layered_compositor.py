from app.schemas.sprite import SpriteBlueprint, SpritePrimitive


def test_layered_compositor_preserves_layer_occlusion_and_adds_local_material_shading():
    from app.sprite_engine.rendering.rasterizer import compose_blueprint_layers

    blueprint = SpriteBlueprint(
        recipe="test",
        subject="test asset",
        palette={"cloth": "#8090a0", "metal": "#8090a0"},
        primitives=[
            SpritePrimitive(op="rectangle", fill="cloth", layer="torso", bbox=(8, 8, 22, 22)),
            SpritePrimitive(op="rectangle", fill="metal", layer="front_equipment", bbox=(14, 14, 28, 28)),
        ],
        layer_order=["torso", "front_equipment"],
    ).model_copy(update={"material_roles": {"cloth": "cloth", "metal": "metal"}})

    image, masks = compose_blueprint_layers(blueprint, width=64, height=64)

    assert masks["torso"].getbbox() is not None
    assert masks["front_equipment"].getbbox() is not None
    assert image.getpixel((14, 14)) != image.getpixel((10, 10))
    assert len({image.getpixel((x, 8)) for x in range(8, 23)}) > 1
    assert len({image.getpixel((x, 14)) for x in range(14, 29)}) > 1
