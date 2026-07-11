from __future__ import annotations

from app.schemas.sprite import DEFAULT_LAYER_ORDER, SpriteBlueprint, SpriteOutlineSpec, SpritePrimitive
from app.sprite_engine.character.skeleton import HumanoidSkeleton
from app.sprite_engine.character.spec import CharacterSpec


def compile_humanoid_character(
    subject: str,
    palette: dict[str, str],
    *,
    character: CharacterSpec,
    skeleton: HumanoidSkeleton,
) -> SpriteBlueprint:
    """Compile bounded character parts into generic primitives in semantic layer order."""

    center_x = skeleton.center_x
    left_leg_center = center_x - skeleton.leg_gap - skeleton.leg_half_width
    right_leg_center = skeleton.mirror_x(left_leg_center)
    left_arm_center = center_x - skeleton.arm_center_offset
    right_arm_center = skeleton.mirror_x(left_arm_center)
    primitives: list[SpritePrimitive] = []

    if character.equipment.hand == "blacksmith_hammer":
        primitives.extend(
            [
                SpritePrimitive(
                    op="line",
                    fill="equipment_wood",
                    layer="back_equipment",
                    points=[
                        (right_arm_center + 2, skeleton.shoulder_y + 4),
                        (right_arm_center + 8, skeleton.hip_y + 6),
                    ],
                    width=2,
                ),
                SpritePrimitive(
                    op="rectangle",
                    fill="equipment_metal",
                    layer="back_equipment",
                    bbox=(
                        right_arm_center + 5,
                        skeleton.shoulder_y + 1,
                        right_arm_center + 11,
                        skeleton.shoulder_y + 5,
                    ),
                ),
            ]
        )

    for leg_center in (left_leg_center, right_leg_center):
        primitives.append(
            SpritePrimitive(
                op="rectangle",
                fill="pants",
                layer="pants",
                bbox=(
                    leg_center - skeleton.leg_half_width,
                    skeleton.waist_y,
                    leg_center + skeleton.leg_half_width,
                    skeleton.leg_bottom_y - 3,
                ),
            )
        )
        primitives.append(
            SpritePrimitive(
                op="rectangle",
                fill="boots",
                layer="boots",
                bbox=(
                    leg_center - skeleton.leg_half_width - 1,
                    skeleton.leg_bottom_y - 3,
                    leg_center + skeleton.leg_half_width + 1,
                    skeleton.leg_bottom_y,
                ),
            )
        )

    primitives.append(
        SpritePrimitive(
            op="polygon",
            fill="shirt",
            layer="torso",
            points=[
                (center_x - skeleton.torso_half_width, skeleton.shoulder_y),
                (center_x + skeleton.torso_half_width, skeleton.shoulder_y),
                (center_x + skeleton.hip_half_width, skeleton.hip_y),
                (center_x - skeleton.hip_half_width, skeleton.hip_y),
            ],
        )
    )
    if character.clothing.upper == "leather_apron":
        primitives.append(
            SpritePrimitive(
                op="polygon",
                fill="apron",
                layer="torso",
                points=[
                    (center_x - skeleton.torso_half_width + 3, skeleton.shoulder_y + 2),
                    (center_x + skeleton.torso_half_width - 3, skeleton.shoulder_y + 2),
                    (center_x + skeleton.hip_half_width - 2, skeleton.hip_y),
                    (center_x - skeleton.hip_half_width + 2, skeleton.hip_y),
                ],
            )
        )

    for arm_center in (left_arm_center, right_arm_center):
        primitives.append(
            SpritePrimitive(
                op="rectangle",
                fill="sleeve",
                layer="arms",
                bbox=(
                    arm_center - skeleton.arm_half_width,
                    skeleton.arm_top_y,
                    arm_center + skeleton.arm_half_width,
                    skeleton.arm_bottom_y - 3,
                ),
            )
        )
        primitives.append(
            SpritePrimitive(
                op="rectangle",
                fill="skin",
                layer="arms",
                bbox=(
                    arm_center - skeleton.arm_half_width + 1,
                    skeleton.arm_bottom_y - 3,
                    arm_center + skeleton.arm_half_width - 1,
                    skeleton.arm_bottom_y,
                ),
            )
        )

    primitives.extend(
        [
            SpritePrimitive(
                op="ellipse",
                fill="skin",
                layer="head",
                bbox=(
                    center_x - skeleton.head_half_width,
                    skeleton.head_top_y,
                    center_x + skeleton.head_half_width,
                    skeleton.head_bottom_y,
                ),
            ),
            SpritePrimitive(
                op="point", fill="outline", layer="head", points=[(center_x - 5, skeleton.head_top_y + 13)], size=2
            ),
            SpritePrimitive(
                op="point", fill="outline", layer="head", points=[(center_x + 5, skeleton.head_top_y + 13)], size=2
            ),
        ]
    )
    if character.hair.style != "none":
        primitives.append(
            SpritePrimitive(
                op="polygon",
                fill="hair",
                layer="hair",
                points=[
                    (center_x - skeleton.head_half_width + 2, skeleton.head_top_y + 7),
                    (center_x - skeleton.head_half_width + 4, skeleton.head_top_y + 1),
                    (center_x - 2, skeleton.head_top_y - 2),
                    (center_x + skeleton.head_half_width - 3, skeleton.head_top_y + 3),
                    (center_x + skeleton.head_half_width - 2, skeleton.head_top_y + 10),
                    (center_x, skeleton.head_top_y + 6),
                ],
            )
        )

    if character.equipment.hand == "blacksmith_hammer":
        primitives.append(
            SpritePrimitive(
                op="rectangle",
                fill="equipment_metal",
                layer="front_equipment",
                bbox=(
                    right_arm_center + 5,
                    skeleton.arm_bottom_y - 2,
                    right_arm_center + 11,
                    skeleton.arm_bottom_y + 2,
                ),
            )
        )
    primitives.extend(
        [
            SpritePrimitive(
                op="line",
                fill="shadow",
                layer="shadows",
                points=[(center_x - 3, skeleton.hip_y - 3), (center_x - 3, skeleton.hip_y - 1)],
                width=1,
            ),
            SpritePrimitive(
                op="line",
                fill="highlight",
                layer="highlights",
                points=[(center_x - 5, skeleton.head_top_y + 6), (center_x - 2, skeleton.head_top_y + 4)],
                width=1,
            ),
        ]
    )
    primitives.sort(key=lambda primitive: DEFAULT_LAYER_ORDER.index(primitive.layer))
    return SpriteBlueprint(
        recipe="humanoid_character",
        subject=subject,
        palette=palette,
        primitives=primitives,
        layer_order=list(DEFAULT_LAYER_ORDER),
        outline=SpriteOutlineSpec(enabled=True),
        notes=["procedural compositional humanoid", "semantic layers and masks", "front-facing symmetric pose"],
    )


__all__ = ["compile_humanoid_character"]
