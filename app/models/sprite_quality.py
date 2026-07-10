from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpriteQualityIssue:
    code: str
    message: str


@dataclass(frozen=True)
class SpriteQualityReport:
    passed: bool
    connected_components: int
    occupancy_ratio: float
    isolated_pixel_count: int
    issues: tuple[SpriteQualityIssue, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "connected_components": self.connected_components,
            "occupancy_ratio": self.occupancy_ratio,
            "isolated_pixel_count": self.isolated_pixel_count,
            "issues": [{"code": issue.code, "message": issue.message} for issue in self.issues],
        }
