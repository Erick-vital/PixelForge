from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class SemanticModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnatomySpec(SemanticModel):
    height: Literal["short", "average", "tall"] = "average"
    build: Literal["slim", "average", "broad", "heavy"] = "average"
    head_size: Literal["small", "average", "large"] = "average"
    leg_length: Literal["short", "average", "long"] = "average"


class PoseSpec(SemanticModel):
    stance: Literal["front_neutral", "side_neutral"] = "front_neutral"
    arm_pose: Literal["sides"] = "sides"
    direction: Literal["left", "right"] = "right"


class FaceSpec(SemanticModel):
    style: Literal["simple"] = "simple"


class HairSpec(SemanticModel):
    style: Literal["none", "short", "short_messy"] = "none"
    color: str | None = None


class ClothingSpec(SemanticModel):
    headwear: Literal["none", "helmet", "wizard_hat"] = "none"
    upper: Literal["none", "tunic", "leather_apron", "armor", "robe"] = "tunic"
    lower: Literal["none", "work_pants", "trousers", "armored_legs", "robe_lower"] = "trousers"
    footwear: Literal["none", "heavy_boots", "boots"] = "boots"


class EquipmentSpec(SemanticModel):
    hand: Literal["none", "blacksmith_hammer", "hammer", "sword", "staff"] = "none"
    off_hand: Literal["none", "shield", "book"] = "none"


class MaterialSpec(SemanticModel):
    upper: Literal["cloth", "leather", "metal"] = "cloth"
    equipment: Literal["wood", "metal"] = "wood"


class LightingSpec(SemanticModel):
    direction: Literal["top_left", "top_right"] = "top_left"


class CharacterSpec(SemanticModel):
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
