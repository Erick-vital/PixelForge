from typing import Any

from app.schemas.sprite import AssetSpec, SpriteBlueprint, SpritePrimitive
from app.sprite_engine.character.skeleton import HumanoidTraits, build_humanoid_skeleton
from app.sprite_engine.character.spec import CharacterSpec
from app.sprite_engine.grammar.models import GrammarCapabilities
from app.sprite_engine.recipes.humanoid import compile_humanoid_character

PALETTE = {
    "outline": "#202020",
    "base": "#506fa8",
    "shadow": "#303b62",
    "highlight": "#e7efff",
    "accent": "#e0b44c",
    "skin": "#d49a6a",
    "hair": "#4d2d20",
    "shirt": "#506fa8",
    "apron": "#87552f",
    "sleeve": "#506fa8",
    "pants": "#303b62",
    "boots": "#2f241f",
    "equipment_wood": "#6b4226",
    "equipment_metal": "#aebcca",
}


class HumanoidFrontGrammar:
    name = "humanoid_front"
    skeleton_name = "HumanoidSkeleton"
    capabilities = GrammarCapabilities(
        "humanoid",
        frozenset({"icon/front"}),
        frozenset({"generic", "blacksmith", "warrior", "wizard"}),
        frozenset({"front_neutral"}),
    )

    def supports(self, spec: AssetSpec) -> bool:
        stance = spec.character.pose.stance if spec.character else "front_neutral"
        return (
            spec.family == self.capabilities.family
            and spec.game_view in self.capabilities.views
            and spec.archetype in self.capabilities.archetypes
            and stance in self.capabilities.poses
        )

    def compile(self, spec: AssetSpec, *, seed: int) -> SpriteBlueprint:
        character = (spec.character or CharacterSpec()).model_copy(deep=True)
        if spec.archetype == "warrior":
            _default(character.clothing, "headwear", "helmet")
            _default(character.clothing, "upper", "armor")
            _default(character.clothing, "lower", "armored_legs")
            _default(character.clothing, "footwear", "heavy_boots")
            _default(character.equipment, "hand", "sword")
            _default(character.equipment, "off_hand", "shield")
            _default(character.materials, "upper", "metal")
        elif spec.archetype == "wizard":
            _default(character.clothing, "headwear", "wizard_hat")
            _default(character.clothing, "upper", "robe")
            _default(character.clothing, "lower", "robe_lower")
            _default(character.equipment, "hand", "staff")
        elif spec.archetype == "blacksmith":
            _default(character.clothing, "upper", "leather_apron")
            _default(character.equipment, "hand", "blacksmith_hammer")
            _default(character.materials, "upper", "leather")
        anatomy = character.anatomy
        skeleton = build_humanoid_skeleton(
            HumanoidTraits(
                height=anatomy.height,
                build=anatomy.build,
                head_size=anatomy.head_size,
                leg_length=anatomy.leg_length,
            )
        )
        blueprint = compile_humanoid_character(spec.subject, dict(PALETTE), character=character, skeleton=skeleton)
        blueprint.recipe = f"humanoid_front/{spec.archetype}"
        blueprint.lighting_direction = character.lighting.direction
        blueprint.material_roles["shirt"] = character.materials.upper

        if character.equipment.off_hand == "shield":
            blueprint.primitives.append(
                SpritePrimitive(op="ellipse", fill="equipment_metal", layer="back_equipment", bbox=(14, 27, 25, 45))
            )
        if character.clothing.upper == "armor":
            blueprint.primitives.append(
                SpritePrimitive(
                    op="rectangle",
                    fill="shirt",
                    layer="torso",
                    bbox=(18, skeleton.shoulder_y, 46, skeleton.shoulder_y + 5),
                )
            )
        if character.clothing.footwear == "heavy_boots":
            blueprint.primitives.extend(
                [
                    SpritePrimitive(
                        op="rectangle",
                        fill="boots",
                        layer="boots",
                        bbox=(20, skeleton.leg_bottom_y - 4, 31, skeleton.leg_bottom_y),
                    ),
                    SpritePrimitive(
                        op="rectangle",
                        fill="boots",
                        layer="boots",
                        bbox=(33, skeleton.leg_bottom_y - 4, 44, skeleton.leg_bottom_y),
                    ),
                ]
            )
        if character.clothing.headwear == "helmet":
            blueprint.primitives.append(
                SpritePrimitive(op="rectangle", fill="equipment_metal", layer="hair", bbox=(21, 5, 43, 13))
            )
        elif character.clothing.headwear == "wizard_hat":
            blueprint.primitives.append(
                SpritePrimitive(op="polygon", fill="shirt", layer="hair", points=[(19, 12), (32, 1), (45, 12)])
            )
        if character.clothing.lower == "robe_lower":
            blueprint.primitives.append(
                SpritePrimitive(
                    op="polygon", fill="shirt", layer="pants", points=[(22, 42), (42, 42), (46, 57), (18, 57)]
                )
            )
        if character.equipment.hand == "sword":
            blueprint.primitives.extend(
                [
                    SpritePrimitive(
                        op="line", fill="equipment_wood", layer="front_equipment", points=[(44, 40), (47, 35)], width=2
                    ),
                    SpritePrimitive(
                        op="line", fill="equipment_metal", layer="front_equipment", points=[(47, 35), (53, 18)], width=3
                    ),
                ]
            )
        elif character.equipment.hand == "staff":
            blueprint.primitives.append(
                SpritePrimitive(
                    op="line", fill="equipment_wood", layer="front_equipment", points=[(45, 53), (49, 18)], width=2
                )
            )
        blueprint.primitives.sort(key=lambda primitive: blueprint.layer_order.index(primitive.layer))
        used = {primitive.fill for primitive in blueprint.primitives}
        blueprint.material_roles = {
            fill: material for fill, material in blueprint.material_roles.items() if fill in used
        }
        return blueprint


def _default(model: Any, field: str, value: str) -> None:
    if field not in model.model_fields_set:
        setattr(model, field, value)
