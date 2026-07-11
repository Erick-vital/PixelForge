"""Compatibility facade for structural sprite quality checks."""

from app.sprite_engine.quality.structural import (
    MAX_OCCUPANCY_RATIO,
    MIN_OCCUPANCY_RATIO,
    SpriteQualityError,
    evaluate_sprite_quality,
    require_sprite_quality,
)

__all__ = [
    "MAX_OCCUPANCY_RATIO",
    "MIN_OCCUPANCY_RATIO",
    "SpriteQualityError",
    "evaluate_sprite_quality",
    "require_sprite_quality",
]
