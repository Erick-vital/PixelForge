from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BASE_CANVAS_SIZE = 64

HumanoidHeight = Literal["short", "average", "tall"]
HumanoidBuild = Literal["slim", "average", "broad", "heavy"]
HumanoidHeadSize = Literal["small", "average", "large"]
HumanoidLegLength = Literal["short", "average", "long"]


@dataclass(frozen=True)
class HumanoidTraits:
    """User-visible proportions, intentionally separate from resolved coordinates."""

    height: HumanoidHeight = "average"
    build: HumanoidBuild = "average"
    head_size: HumanoidHeadSize = "average"
    leg_length: HumanoidLegLength = "average"


@dataclass(frozen=True)
class HumanoidSkeleton:
    center_x: int = 32
    ground_y: int = 58
    head_top_y: int = 6
    head_bottom_y: int = 31
    shoulder_y: int = 31
    arm_top_y: int = 32
    arm_bottom_y: int = 45
    waist_y: int = 43
    hip_y: int = 45
    leg_bottom_y: int = 58
    head_half_width: int = 13
    torso_half_width: int = 9
    hip_half_width: int = 7
    leg_half_width: int = 3
    leg_gap: int = 2
    arm_center_offset: int = 13
    arm_half_width: int = 3

    def __post_init__(self) -> None:
        if not 0 <= self.center_x < BASE_CANVAS_SIZE:
            raise ValueError("center_x must be within the base canvas")
        if not 0 <= self.head_top_y < self.head_bottom_y <= self.shoulder_y < self.waist_y < self.hip_y < self.ground_y:
            raise ValueError("humanoid anchors must be strictly ordered within the canvas")
        if not self.shoulder_y < self.arm_top_y < self.arm_bottom_y <= self.hip_y:
            raise ValueError("arm anchors must attach between the shoulder and hip")
        if self.leg_bottom_y != self.ground_y:
            raise ValueError("leg_bottom_y must match ground_y")
        if self.ground_y >= BASE_CANVAS_SIZE:
            raise ValueError("ground_y must be within the base canvas")
        if (
            min(
                self.head_half_width,
                self.torso_half_width,
                self.hip_half_width,
                self.leg_half_width,
                self.arm_center_offset,
                self.arm_half_width,
            )
            <= 0
        ):
            raise ValueError("humanoid widths must be positive")
        if self.leg_gap < 0:
            raise ValueError("leg_gap must not be negative")

    def mirror_x(self, x: int) -> int:
        return 2 * self.center_x - x


def build_humanoid_skeleton(traits: HumanoidTraits) -> HumanoidSkeleton:
    """Resolve bounded semantic proportions into a connected 64px humanoid skeleton."""

    total_height = {"short": 48, "average": 52, "tall": 56}[traits.height]
    head_height = {"small": 21, "average": 25, "large": 28}[traits.head_size]
    requested_leg_height = {"short": 11, "average": 13, "long": 17}[traits.leg_length]
    # A short body with a large head cannot also fit a maximum-length leg pair.
    # Preserve a minimum connected torso instead of emitting invalid coordinates.
    leg_height = min(requested_leg_height, total_height - head_height - 7)

    ground_y = 58
    head_top_y = ground_y - total_height
    head_bottom_y = head_top_y + head_height
    shoulder_y = head_bottom_y
    hip_y = ground_y - leg_height
    waist_y = hip_y - 2

    torso_half_width = {"slim": 7, "average": 9, "broad": 11, "heavy": 13}[traits.build]
    head_half_width = {"small": 10, "average": 13, "large": 15}[traits.head_size]
    hip_half_width = max(5, torso_half_width - 2)
    leg_half_width = {"slim": 2, "average": 3, "broad": 4, "heavy": 5}[traits.build]
    arm_half_width = max(2, leg_half_width)
    arm_center_offset = torso_half_width + arm_half_width + 1
    arm_top_y = shoulder_y + 1
    arm_bottom_y = hip_y

    return HumanoidSkeleton(
        ground_y=ground_y,
        head_top_y=head_top_y,
        head_bottom_y=head_bottom_y,
        shoulder_y=shoulder_y,
        arm_top_y=arm_top_y,
        arm_bottom_y=arm_bottom_y,
        waist_y=waist_y,
        hip_y=hip_y,
        leg_bottom_y=ground_y,
        head_half_width=head_half_width,
        torso_half_width=torso_half_width,
        hip_half_width=hip_half_width,
        leg_half_width=leg_half_width,
        leg_gap=2,
        arm_center_offset=arm_center_offset,
        arm_half_width=arm_half_width,
    )


__all__ = ["HumanoidSkeleton", "HumanoidTraits", "build_humanoid_skeleton"]
