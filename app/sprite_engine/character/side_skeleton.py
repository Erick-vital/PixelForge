from dataclasses import dataclass, replace
from typing import Literal


@dataclass(frozen=True)
class HumanoidSideSkeleton:
    face_direction: Literal["left", "right"]
    body_axis_x: int = 31
    head_center: tuple[int, int] = (32, 17)
    nose_anchor: tuple[int, int] = (43, 18)
    shoulder_front: tuple[int, int] = (35, 31)
    shoulder_back: tuple[int, int] = (28, 32)
    hand_front: tuple[int, int] = (39, 44)
    hand_back: tuple[int, int] = (26, 43)
    hip: tuple[int, int] = (31, 44)
    knee_front: tuple[int, int] = (36, 51)
    knee_back: tuple[int, int] = (27, 51)
    foot_front: tuple[int, int] = (40, 58)
    foot_back: tuple[int, int] = (25, 58)
    ground_y: int = 58
    back_equipment_anchor: tuple[int, int] = (26, 35)

    def mirror_direction(self) -> "HumanoidSideSkeleton":
        def mirror(point: tuple[int, int]) -> tuple[int, int]:
            return (64 - point[0], point[1])

        fields = {
            name: mirror(getattr(self, name))
            for name in self.__dataclass_fields__
            if isinstance(getattr(self, name), tuple)
        }
        direction = "left" if self.face_direction == "right" else "right"
        return replace(self, face_direction=direction, **fields)


def build_humanoid_side_skeleton(direction: Literal["left", "right"] = "right") -> HumanoidSideSkeleton:
    skeleton = HumanoidSideSkeleton("right")
    return skeleton if direction == "right" else skeleton.mirror_direction()
