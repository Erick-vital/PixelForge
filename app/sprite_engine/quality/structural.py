from __future__ import annotations

from collections import deque

import numpy as np
from PIL import Image

from app.models.sprite_quality import SpriteQualityIssue, SpriteQualityReport

MIN_OCCUPANCY_RATIO = 0.08
MAX_OCCUPANCY_RATIO = 0.70


class SpriteQualityError(ValueError):
    def __init__(self, report: SpriteQualityReport) -> None:
        self.report = report
        codes = ", ".join(issue.code for issue in report.issues)
        super().__init__(f"Sprite quality validation failed: {codes}")


def evaluate_sprite_quality(
    image: Image.Image,
    *,
    min_occupancy: float = MIN_OCCUPANCY_RATIO,
    max_occupancy: float = MAX_OCCUPANCY_RATIO,
) -> SpriteQualityReport:
    """Validate structural raster properties independently from semantic quality."""

    alpha_mask = np.asarray(image.convert("RGBA").getchannel("A")) > 0
    component_sizes = _component_sizes(alpha_mask)
    occupancy_ratio = float(alpha_mask.mean())
    issues: list[SpriteQualityIssue] = []
    if len(component_sizes) != 1:
        issues.append(
            SpriteQualityIssue("component_count", f"expected 1 connected component, found {len(component_sizes)}")
        )
    if occupancy_ratio < min_occupancy:
        issues.append(
            SpriteQualityIssue(
                "occupancy_too_low", f"expected occupancy >= {min_occupancy:.2f}, found {occupancy_ratio:.4f}"
            )
        )
    if occupancy_ratio > max_occupancy:
        issues.append(
            SpriteQualityIssue(
                "occupancy_too_high", f"expected occupancy <= {max_occupancy:.2f}, found {occupancy_ratio:.4f}"
            )
        )
    isolated_pixel_count = sum(size == 1 for size in component_sizes)
    if isolated_pixel_count:
        issues.append(SpriteQualityIssue("isolated_pixels", f"found {isolated_pixel_count} isolated opaque pixels"))
    return SpriteQualityReport(
        passed=not issues,
        connected_components=len(component_sizes),
        occupancy_ratio=occupancy_ratio,
        isolated_pixel_count=isolated_pixel_count,
        issues=tuple(issues),
    )


def require_sprite_quality(image: Image.Image) -> SpriteQualityReport:
    report = evaluate_sprite_quality(image)
    if not report.passed:
        raise SpriteQualityError(report)
    return report


def _component_sizes(mask: np.ndarray) -> list[int]:
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    component_sizes: list[int] = []
    for y, x in zip(*np.where(mask), strict=True):
        if visited[y, x]:
            continue
        visited[y, x] = True
        queue: deque[tuple[int, int]] = deque([(y, x)])
        size = 0
        while queue:
            current_y, current_x = queue.popleft()
            size += 1
            for y_offset in (-1, 0, 1):
                for x_offset in (-1, 0, 1):
                    neighbor_y = current_y + y_offset
                    neighbor_x = current_x + x_offset
                    if (
                        (y_offset or x_offset)
                        and 0 <= neighbor_y < height
                        and 0 <= neighbor_x < width
                        and mask[neighbor_y, neighbor_x]
                        and not visited[neighbor_y, neighbor_x]
                    ):
                        visited[neighbor_y, neighbor_x] = True
                        queue.append((neighbor_y, neighbor_x))
        component_sizes.append(size)
    return component_sizes


__all__ = [
    "MAX_OCCUPANCY_RATIO",
    "MIN_OCCUPANCY_RATIO",
    "SpriteQualityError",
    "evaluate_sprite_quality",
    "require_sprite_quality",
]
