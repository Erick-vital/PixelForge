from __future__ import annotations

import logging
from dataclasses import dataclass

from app.schemas.sprite import AssetSpec, AssetSpecRequest, GenerationPromptResponse, ProcessingPlanResponse
from app.services.llm_generation import LlmGenerationService
from app.services.sprite_interpretation import (
    SpriteSpecError,
    create_asset_spec_from_request,
    create_generation_prompt,
    create_processing_plan,
)
from app.services.sprite_processing import SpriteProcessingError, process_sprite_image

logger = logging.getLogger(__name__)


class SpriteError(ValueError):
    pass


@dataclass
class SpriteService:
    llm_service: LlmGenerationService | None = None

    async def create_asset_spec(self, request: AssetSpecRequest) -> AssetSpec:
        logger.info(
            "sprite asset spec generation started",
            extra={"prompt_chars": len(request.prompt), "use_llm": request.use_llm},
        )
        try:
            spec = await create_asset_spec_from_request(request, llm_service=self.llm_service)
        except SpriteSpecError as exc:
            raise SpriteError(str(exc)) from exc
        logger.info(
            "sprite asset spec generation completed",
            extra={"asset_type": spec.asset_type, "subject": spec.subject, "width": spec.size.width, "height": spec.size.height},
        )
        return spec

    def create_generation_prompt(self, asset_spec: AssetSpec) -> GenerationPromptResponse:
        return create_generation_prompt(asset_spec)

    def create_processing_plan(self, asset_spec: AssetSpec) -> ProcessingPlanResponse:
        return create_processing_plan(asset_spec)

    def process_sprite(self, image_bytes: bytes, asset_spec: AssetSpec) -> tuple[bytes, dict[str, object]]:
        try:
            result = process_sprite_image(image_bytes, asset_spec)
        except SpriteProcessingError as exc:
            raise SpriteError(str(exc)) from exc
        return result.png_bytes, result.report


__all__ = [
    "SpriteError",
    "SpriteService",
]
