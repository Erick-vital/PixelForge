from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

AllowedAssetType = Literal["enemy", "prop", "icon"]
AllowedView = Literal["side-view", "top-down 3/4", "icon/front"]
AllowedResizeMode = Literal["nearest-neighbor"]
AllowedExportFormat = Literal["png"]


def _supported_sprite_dimension(value: int) -> int:
    if value not in {32, 64, 128}:
        raise ValueError("Supported sprite sizes are 32, 64, or 128 pixels")
    return value


SpriteDimension = Annotated[int, AfterValidator(_supported_sprite_dimension)]


class SpriteSize(BaseModel):
    width: SpriteDimension
    height: SpriteDimension


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


class PromptGuidance(BaseModel):
    target_prompt_tone: str = "concise game-asset prompt"
    include_size: bool = True
    include_style: bool = True
    include_negative_prompt: bool = True
    normalize_subject_to_english: bool = True


class ProcessingProfile(BaseModel):
    resize_mode: AllowedResizeMode = "nearest-neighbor"
    palette_max_colors: int = Field(default=24, ge=8, le=32)
    center_sprite: bool = True
    transparent_background: bool = True
    export_format: AllowedExportFormat = "png"


class AssetSpec(BaseModel):
    asset_type: AllowedAssetType = "prop"
    subject: str = "game asset"
    game_view: AllowedView = "icon/front"
    style: str = "pixel art"
    size: SpriteSize = Field(default_factory=lambda: SpriteSize(width=64, height=64))
    palette: PaletteSpec = Field(default_factory=PaletteSpec)
    shape: ShapeSpec = Field(default_factory=ShapeSpec)
    technical_constraints: TechnicalConstraints = Field(default_factory=TechnicalConstraints)
    prompt_guidance: PromptGuidance = Field(default_factory=PromptGuidance)
    processing_profile: ProcessingProfile = Field(default_factory=ProcessingProfile)


class AssetSpecRequest(BaseModel):
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    use_llm: bool = False
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None


class SpriteArtifactRef(BaseModel):
    artifact_id: str
    artifact_dir: str
    status: str
    subject: str


class SpriteArtifactAssetSpecResponse(SpriteArtifactRef):
    asset_spec: AssetSpec


class SpriteArtifactBlueprintResponse(SpriteArtifactRef):
    asset_spec: AssetSpec
    blueprint: SpriteBlueprint


class RenderSpriteRequest(BaseModel):
    artifact_id: str
    seed: int = 0


class SpriteBlueprintRequest(BaseModel):
    artifact_id: str
    seed: int = 0


class RenderBlueprintRequest(BaseModel):
    artifact_id: str
    seed: int = 0


class SpritePrimitive(BaseModel):
    op: Literal["ellipse", "rectangle", "polygon", "line", "point"]
    fill: str
    bbox: tuple[int, int, int, int] | None = None
    points: list[tuple[int, int]] = Field(default_factory=list)
    width: int | None = None
    size: int | None = None


class SpriteBlueprint(BaseModel):
    recipe: str
    subject: str
    palette: dict[str, str]
    primitives: list[SpritePrimitive]
    notes: list[str] = Field(default_factory=list)


class SpriteValidationReport(BaseModel):
    width: int
    height: int
    mode: str
    transparent: bool
    non_empty: bool
    notes: list[str] = Field(default_factory=list)


JsonObject = dict[str, Any]


SpriteArtifactBlueprintResponse.model_rebuild()
