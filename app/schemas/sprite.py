from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator
from typing_extensions import Annotated

AllowedAssetType = Literal["enemy", "prop", "icon"]
AllowedView = Literal["side-view", "top-down 3/4", "icon/front"]


class SpriteSize(BaseModel):
    width: int = Field(ge=32, le=128)
    height: int = Field(ge=32, le=128)

    @field_validator("width", "height")
    @classmethod
    def supported_mvp_size(cls, value: int) -> int:
        if value not in {32, 64, 128}:
            raise ValueError("MVP supports only 32, 64, or 128 pixels")
        return value


class PaletteSpec(BaseModel):
    main: list[str] = Field(default_factory=list)
    shadows: list[str] = Field(default_factory=list)
    accent: list[str] = Field(default_factory=list)


class ShapeSpec(BaseModel):
    silhouette: str = "clear readable compact silhouette"
    proportions: dict[str, str] = Field(default_factory=dict)


class TechnicalConstraints(BaseModel):
    transparent_background: bool = True
    pixel_art: bool = True
    readable_at_small_size: bool = True


class AssetSpec(BaseModel):
    asset_type: AllowedAssetType = "prop"
    subject: str = "game asset"
    game_view: AllowedView = "icon/front"
    style: str = "pixel art"
    size: SpriteSize = Field(default_factory=lambda: SpriteSize(width=64, height=64))
    palette: PaletteSpec = Field(default_factory=PaletteSpec)
    shape: ShapeSpec = Field(default_factory=ShapeSpec)
    technical_constraints: TechnicalConstraints = Field(default_factory=TechnicalConstraints)


class AssetSpecRequest(BaseModel):
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    use_llm: bool = False
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None


class GenerationPromptRequest(BaseModel):
    asset_spec: AssetSpec


class GenerationPromptResponse(BaseModel):
    prompt: str
    negative_prompt: str


class ProcessingPlanRequest(BaseModel):
    asset_spec: AssetSpec


class ProcessingStep(BaseModel):
    name: str
    instruction: str


class ProcessingPlanResponse(BaseModel):
    steps: list[ProcessingStep]


class SpriteValidationReport(BaseModel):
    width: int
    height: int
    mode: str
    transparent: bool
    non_empty: bool
    notes: list[str] = Field(default_factory=list)


class SpriteMvpResponse(BaseModel):
    asset_spec: AssetSpec
    generation_prompt: GenerationPromptResponse
    processing_plan: ProcessingPlanResponse


JsonObject = dict[str, Any]
