from __future__ import annotations

from app.schemas.sprite import SpriteBlueprint, SpriteOutlineSpec, SpritePrimitive
from app.sprite_engine.character.skeleton import HumanoidSkeleton


def compile_humanoid_base(
    subject: str,
    palette: dict[str, str],
    skeleton: HumanoidSkeleton | None = None,
) -> SpriteBlueprint:
    skeleton = skeleton or HumanoidSkeleton()
    center_x = skeleton.center_x
    left_leg_center = center_x - skeleton.leg_gap - skeleton.leg_half_width
    right_leg_center = skeleton.mirror_x(left_leg_center)
    left_arm_center = center_x - skeleton.arm_center_offset
    right_arm_center = skeleton.mirror_x(left_arm_center)
    primitives = [
        SpritePrimitive(
            op="ellipse",
            fill="base",
            bbox=(
                center_x - skeleton.head_half_width,
                skeleton.head_top_y,
                center_x + skeleton.head_half_width,
                skeleton.head_bottom_y,
            ),
        ),
        SpritePrimitive(
            op="rectangle",
            fill="base",
            bbox=(
                left_arm_center - skeleton.arm_half_width,
                skeleton.arm_top_y,
                left_arm_center + skeleton.arm_half_width,
                skeleton.arm_bottom_y,
            ),
        ),
        SpritePrimitive(
            op="rectangle",
            fill="base",
            bbox=(
                right_arm_center - skeleton.arm_half_width,
                skeleton.arm_top_y,
                right_arm_center + skeleton.arm_half_width,
                skeleton.arm_bottom_y,
            ),
        ),
        SpritePrimitive(
            op="polygon",
            fill="shadow",
            points=[
                (center_x - skeleton.torso_half_width, skeleton.shoulder_y),
                (center_x + skeleton.torso_half_width, skeleton.shoulder_y),
                (center_x + skeleton.hip_half_width, skeleton.hip_y),
                (center_x - skeleton.hip_half_width, skeleton.hip_y),
            ],
        ),
        SpritePrimitive(
            op="rectangle",
            fill="base",
            bbox=(
                left_leg_center - skeleton.leg_half_width,
                skeleton.waist_y,
                left_leg_center + skeleton.leg_half_width,
                skeleton.leg_bottom_y,
            ),
        ),
        SpritePrimitive(
            op="rectangle",
            fill="base",
            bbox=(
                right_leg_center - skeleton.leg_half_width,
                skeleton.waist_y,
                right_leg_center + skeleton.leg_half_width,
                skeleton.leg_bottom_y,
            ),
        ),
        SpritePrimitive(op="line", fill="highlight", points=[(center_x, 12), (center_x, 24)], width=1),
    ]
    return SpriteBlueprint(
        recipe="humanoid_chibi",
        subject=subject,
        palette=palette,
        primitives=primitives,
        outline=SpriteOutlineSpec(enabled=True),
        notes=["procedural humanoid chibi base", "front-facing symmetric silhouette"],
    )


__all__ = ["compile_humanoid_base"]
