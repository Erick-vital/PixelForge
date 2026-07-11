from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class AnatomySpec(BaseModel):
    height: Literal["short", "average", "tall"] = "average"
    build: Literal["slim", "average", "broad", "heavy"] = "average"
    head_size: Literal["small", "average", "large"] = "average"
    leg_length: Literal["short", "average", "long"] = "average"


class PoseSpec(BaseModel):
    stance: Literal["front_neutral"] = "front_neutral"
    arm_pose: Literal["sides"] = "sides"


class FaceSpec(BaseModel):
    style: Literal["simple"] = "simple"


class HairSpec(BaseModel):
    style: Literal["none", "short", "short_messy"] = "none"
    color: str | None = None


class ClothingSpec(BaseModel):
    upper: Literal["none", "tunic", "leather_apron", "armor"] = "tunic"
    lower: Literal["none", "work_pants", "trousers"] = "trousers"
    footwear: Literal["none", "heavy_boots", "boots"] = "boots"


class EquipmentSpec(BaseModel):
    hand: Literal["none", "blacksmith_hammer"] = "none"


class MaterialSpec(BaseModel):
    upper: Literal["cloth", "leather", "metal"] = "cloth"
    equipment: Literal["wood", "metal"] = "wood"


class LightingSpec(BaseModel):
    direction: Literal["top_left", "top_right"] = "top_left"


class CharacterSpec(BaseModel):
    """Composable, bounded character identity compiled by a local recipe."""

    anatomy: AnatomySpec = AnatomySpec()
    pose: PoseSpec = PoseSpec()
    face: FaceSpec = FaceSpec()
    hair: HairSpec = HairSpec()
    clothing: ClothingSpec = ClothingSpec()
    equipment: EquipmentSpec = EquipmentSpec()
    materials: MaterialSpec = MaterialSpec()
    lighting: LightingSpec = LightingSpec()


__all__ = [
    "AnatomySpec",
    "CharacterSpec",
    "ClothingSpec",
    "EquipmentSpec",
    "FaceSpec",
    "HairSpec",
    "LightingSpec",
    "MaterialSpec",
    "PoseSpec",
]
