from dataclasses import dataclass

from app.sprite_engine.character.quadruped_spec import QuadrupedSpec


@dataclass(frozen=True)
class QuadrupedSkeleton:
    body_bbox: tuple[int, int, int, int]
    head_bbox: tuple[int, int, int, int]
    head_center: tuple[int, int]
    snout_anchor: tuple[int, int]
    tail_anchor: tuple[int, int]
    leg_anchors: tuple[tuple[int, int], ...]
    feet: tuple[tuple[int, int], ...]
    ear_points: tuple[tuple[int, int], ...]
    ground_y: int = 55
    direction: str = "right"

    def mirror_direction(self) -> "QuadrupedSkeleton":
        def point(value: tuple[int, int]) -> tuple[int, int]:
            return (63 - value[0], value[1])

        def bbox(value: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
            return (63 - value[2], value[1], 63 - value[0], value[3])

        return QuadrupedSkeleton(
            bbox(self.body_bbox),
            bbox(self.head_bbox),
            point(self.head_center),
            point(self.snout_anchor),
            point(self.tail_anchor),
            tuple(point(item) for item in reversed(self.leg_anchors)),
            tuple(point(item) for item in reversed(self.feet)),
            tuple(point(item) for item in self.ear_points),
            self.ground_y,
            "left" if self.direction == "right" else "right",
        )


def build_quadruped_skeleton(spec: QuadrupedSpec | None = None) -> QuadrupedSkeleton:
    spec = spec or QuadrupedSpec()
    x0, x1 = {"short": (17, 45), "average": (13, 47), "long": (9, 49)}[spec.body_length]
    y0, y1 = {"slim": (28, 42), "average": (25, 43), "heavy": (22, 45)}[spec.body_depth]
    leg_top = {"short": y1 - 2, "average": y1 - 5, "long": y1 - 8}[spec.leg_length]
    anchors = ((x0 + 5, leg_top), (x0 + 11, leg_top), (x1 - 11, leg_top), (x1 - 5, leg_top))
    feet = tuple((x, 55) for x, _ in anchors)
    head_width = 14 if spec.head_shape == "round" else 17
    head_height = 18 if spec.head_shape == "round" else 16
    head_bbox = (x1 - 2, y0, min(59, x1 - 2 + head_width), y0 + head_height)
    head_center = ((head_bbox[0] + head_bbox[2]) // 2, (head_bbox[1] + head_bbox[3]) // 2)
    # Resolve from the center so average and long snouts do not collapse to
    # the same clamped coordinate at the edge of the 64px canvas.
    snout_x = min(62, head_center[0] + {"short": 3, "average": 5, "long": 7}[spec.snout_length])
    ear_top = y0 - {"floppy": 1, "triangular": 7, "upright": 10}[spec.ear_shape]
    ear_points = ((head_bbox[0] + 3, y0 + 3), (head_bbox[0] + 5, ear_top), (head_bbox[0] + 8, y0 + 4))
    skeleton = QuadrupedSkeleton(
        (x0, y0, x1, y1),
        head_bbox,
        head_center,
        (snout_x, head_center[1] + 3),
        (x0, y0 + 7),
        anchors,
        feet,
        ear_points,
    )
    return skeleton.mirror_direction() if spec.direction == "left" else skeleton
