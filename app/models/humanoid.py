"""Compatibility facade for the sprite engine's character skeleton API."""

from app.sprite_engine.character.skeleton import (
    BASE_CANVAS_SIZE,
    HumanoidBuild,
    HumanoidHeadSize,
    HumanoidHeight,
    HumanoidLegLength,
    HumanoidSkeleton,
    HumanoidTraits,
    build_humanoid_skeleton,
)

__all__ = [
    "BASE_CANVAS_SIZE",
    "HumanoidBuild",
    "HumanoidHeadSize",
    "HumanoidHeight",
    "HumanoidLegLength",
    "HumanoidSkeleton",
    "HumanoidTraits",
    "build_humanoid_skeleton",
]
