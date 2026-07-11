from app.sprite_engine.character.skeleton import HumanoidTraits, build_humanoid_skeleton


def test_blacksmith_character_spec_compiles_semantic_parts_into_ordered_layers_and_masks():
    from app.sprite_engine.character.spec import CharacterSpec
    from app.sprite_engine.recipes.humanoid import compile_humanoid_character
    from app.sprite_engine.rendering.rasterizer import render_layer_masks

    character = CharacterSpec.model_validate(
        {
            "anatomy": {"height": "short", "build": "heavy", "head_size": "large"},
            "hair": {"style": "short_messy", "color": "#4d2d20"},
            "clothing": {"upper": "leather_apron", "lower": "work_pants", "footwear": "heavy_boots"},
            "equipment": {"hand": "blacksmith_hammer"},
            "materials": {"upper": "leather", "equipment": "metal"},
            "lighting": {"direction": "top_left"},
        }
    )
    skeleton = build_humanoid_skeleton(HumanoidTraits(height="short", build="heavy", head_size="large"))

    blueprint = compile_humanoid_character(
        "blacksmith",
        {
            "outline": "#202020",
            "skin": "#d49a6a",
            "hair": "#4d2d20",
            "shirt": "#6d3b24",
            "apron": "#87552f",
            "sleeve": "#6d3b24",
            "pants": "#394a66",
            "boots": "#2f241f",
            "equipment_wood": "#6b4226",
            "equipment_metal": "#9aa6b2",
            "shadow": "#3d552c",
            "highlight": "#d9e8a8",
        },
        character=character,
        skeleton=skeleton,
    )

    layers = [primitive.layer for primitive in blueprint.primitives]
    assert layers == sorted(layers, key=blueprint.layer_order.index)
    assert {"back_equipment", "pants", "boots", "torso", "hair", "front_equipment", "highlights"} <= set(layers)

    masks = render_layer_masks(blueprint, width=64, height=64)
    for layer_name in {"back_equipment", "pants", "boots", "torso", "hair", "front_equipment"}:
        assert masks[layer_name].getbbox() is not None
