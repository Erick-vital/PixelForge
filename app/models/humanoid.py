from __future__ import annotations

from dataclasses import dataclass

BASE_CANVAS_SIZE = 64


@dataclass(frozen=True)
class HumanoidSkeleton:
    center_x: int = 32
    ground_y: int = 58
    head_top_y: int = 6
    head_bottom_y: int = 31
    shoulder_y: int = 31
    waist_y: int = 43
    hip_y: int = 45
    leg_bottom_y: int = 58
    head_half_width: int = 13
    torso_half_width: int = 9
    hip_half_width: int = 7
    leg_half_width: int = 3
    leg_gap: int = 2

    def __post_init__(self) -> None:
        if not 0 <= self.center_x < BASE_CANVAS_SIZE:
            raise ValueError("center_x must be within the base canvas")
        if not 0 <= self.head_top_y < self.head_bottom_y <= self.shoulder_y < self.waist_y < self.hip_y < self.ground_y:
            raise ValueError("humanoid anchors must be strictly ordered within the canvas")
        if self.leg_bottom_y != self.ground_y:
            raise ValueError("leg_bottom_y must match ground_y")
        if self.ground_y >= BASE_CANVAS_SIZE:
            raise ValueError("ground_y must be within the base canvas")
        if min(self.head_half_width, self.torso_half_width, self.hip_half_width, self.leg_half_width) <= 0:
            raise ValueError("humanoid widths must be positive")
        if self.leg_gap < 0:
            raise ValueError("leg_gap must not be negative")

    def mirror_x(self, x: int) -> int:
        return 2 * self.center_x - x
