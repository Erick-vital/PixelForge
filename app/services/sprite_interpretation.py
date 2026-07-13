from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from app.schemas.sprite import (
    AllowedAssetType,
    AllowedView,
    AssetSpec,
    AssetSpecDecisionTrace,
    AssetSpecRequest,
    PaletteSpec,
    ProcessingProfile,
    PromptGuidance,
    ShapeSpec,
    SpriteSize,
    TechnicalConstraints,
)
from app.services.llm_generation import LlmGenerationService
from app.sprite_engine.character.spec import (
    AnatomySpec,
    CharacterSpec,
    ClothingSpec,
    EquipmentSpec,
    HairSpec,
    MaterialSpec,
)
from app.sprite_engine.grammar.classification import classify_subject
from app.sprite_engine.grammar.templates import SpriteTemplate, TemplateResolutionError, resolve_template

logger = logging.getLogger(__name__)


ASSET_SPEC_SYSTEM_PROMPT = """You convert user game-asset requests into strict JSON for the sprite pipeline.
Return only a JSON object with these keys:
asset_type: one of enemy, prop, icon
subject: concise English subject
game_view: one of side-view, top-down 3/4, icon/front
style: pixel art style phrase
size: {width: 32|64|128, height: 32|64|128}
palette: {main: string[], shadows: string[], accent: string[]}
shape: {silhouette: string, proportions: object mapping labels to short string values; use strings such as \"1.0\" for numeric ratios}
character: null for non-humanoids, otherwise {anatomy: {height: short|average|tall, build: slim|average|broad|heavy, head_size: small|average|large, leg_length: short|average|long}, pose: {stance: front_neutral, arm_pose: sides}, face: {style: simple}, hair: {style: none|short|short_messy, color: string|null}, clothing: {headwear: none|helmet|wizard_hat, upper: none|tunic|leather_apron|armor|robe, lower: none|work_pants|trousers|armored_legs|robe_lower, footwear: none|heavy_boots|boots}, equipment: {hand: none|blacksmith_hammer|hammer|sword|staff, off_hand: none|shield|book}, materials: {upper: cloth|leather|metal, equipment: wood|metal}, lighting: {direction: top_left|top_right}}
Keep concrete character fields semantically consistent with subject and shape.silhouette. For example, a conventional wizard should use wizard_hat, robe/robe_lower, and staff unless the user explicitly asks to omit or replace them. Do not emit generic none/tunic/trousers values that contradict the requested archetype.
technical_constraints: {transparent_background: true, pixel_art: true, readable_at_small_size: true}
prompt_guidance: {target_prompt_tone: string, include_size: boolean, include_style: boolean, include_negative_prompt: boolean, normalize_subject_to_english: boolean}
processing_profile: {resize_mode: nearest-neighbor, palette_max_colors: integer, center_sprite: boolean, transparent_background: boolean, export_format: png}
Scope limits: only 2D pixel-art enemy, prop, or icon assets.
"""


class SpriteSpecError(ValueError):
    pass


async def create_asset_spec_from_request(
    request: AssetSpecRequest, llm_service: LlmGenerationService | None = None
) -> AssetSpec:
    spec, _ = await create_asset_spec_from_request_with_trace(request, llm_service)
    return spec


async def create_asset_spec_from_request_with_trace(
    request: AssetSpecRequest, llm_service: LlmGenerationService | None = None
) -> tuple[AssetSpec, AssetSpecDecisionTrace]:
    try:
        template = resolve_template(request.template_id) if request.template_id else None
    except TemplateResolutionError as exc:
        raise SpriteSpecError(str(exc)) from exc

    if not request.use_llm:
        local_spec = create_asset_spec_from_prompt(request.prompt)
        return _apply_request_intent(local_spec.model_dump(mode="python"), request, template, apply_stable_default=True)

    llm = llm_service or LlmGenerationService()
    result = await llm.generate_text(
        system_prompt=ASSET_SPEC_SYSTEM_PROMPT,
        prompt=request.prompt,
        provider=request.provider,
        model=request.model,
        base_url=request.base_url,
        temperature=0.1,
        max_tokens=1200,
    )
    try:
        data = _extract_json_object(result.text)
        return _apply_request_intent(data, request, template, apply_stable_default=True)
    except (ValueError, ValidationError) as exc:
        logger.warning("llm asset spec parse failed", extra={"error": str(exc)})
        raise SpriteSpecError(f"LLM did not return a valid Asset Spec JSON: {exc}") from exc


def _apply_request_intent(
    data: dict[str, Any],
    request: AssetSpecRequest,
    template: SpriteTemplate | None,
    *,
    apply_stable_default: bool,
) -> tuple[AssetSpec, AssetSpecDecisionTrace]:
    """Apply bounded client intent before validating the interpreted AssetSpec.

    The raw dictionary retains the interpretation provenance long enough to avoid
    treating an LLM-supplied pose as a client-explicit contradiction.
    """
    resolved = dict(data)
    classification = classify_subject(str(resolved.get("subject", "game asset")))
    if resolved.get("family", "unknown") == "unknown":
        resolved["family"] = classification.family
        resolved["archetype"] = classification.archetype

    if template is not None:
        resolved.update(
            family=template.family,
            archetype=template.archetype,
            game_view=template.view,
        )
        view_source = "template"
    elif request.view is not None:
        resolved["game_view"] = request.view
        view_source = "explicit"
    elif apply_stable_default and resolved.get("family") in {"humanoid", "prop", "unknown"}:
        # The LLM may describe a view, but is not allowed to select the product default
        # for families covered by the stable front-view policy.
        resolved["game_view"] = "icon/front"
        view_source = "default"
    else:
        view_source = "llm_inferred"

    # Templates constrain semantic intent only. The caller independently chooses
    # whether that intent is designed by the LLM or compiled by a local grammar.
    resolved["generation_mode"] = request.generation_mode

    if resolved.get("family") == "humanoid":
        character = resolved.get("character")
        character_data = dict(character) if isinstance(character, dict) else {}
        pose = character_data.get("pose")
        pose_data = dict(pose) if isinstance(pose, dict) else {}
        if resolved.get("game_view") in {"side-view", "icon/front"} and view_source != "llm_inferred":
            pose_data["stance"] = "side_neutral" if resolved["game_view"] == "side-view" else "front_neutral"
        if pose_data:
            character_data["pose"] = pose_data
        resolved["character"] = character_data

    spec = AssetSpec.model_validate(resolved)
    return spec, AssetSpecDecisionTrace(
        view_source=view_source,
        template_id=template.template_id if template is not None else None,
        requested_view=request.view,
    )


def create_asset_spec_from_prompt(prompt: str) -> AssetSpec:
    normalized = _normalize(prompt)
    width, height = _detect_size(normalized)
    asset_type = _detect_asset_type(normalized)
    subject = _detect_subject(normalized)
    game_view = _detect_view(normalized)
    style = _detect_style(normalized, subject)
    palette = _detect_palette(normalized, subject)
    shape = _detect_shape(subject)
    classification = classify_subject(subject if subject != "human" else normalized)
    return AssetSpec(
        family=classification.family,
        archetype=classification.archetype,
        asset_type=asset_type,
        subject=subject,
        game_view=game_view,
        style=style,
        size=SpriteSize(width=width, height=height),
        palette=palette,
        shape=shape,
        character=_detect_character_spec(normalized, subject),
        technical_constraints=TechnicalConstraints(
            transparent_background=True,
            pixel_art="pixel" in normalized,
            readable_at_small_size=True,
        ),
        prompt_guidance=PromptGuidance(),
        processing_profile=ProcessingProfile(),
    )


def _detect_size(text: str) -> tuple[int, int]:
    match = re.search(r"\b(32|64|128)\s*x\s*(32|64|128)\b", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    single = re.search(r"\b(32|64|128)\b", text)
    if single:
        value = int(single.group(1))
        return value, value
    return 64, 64


def _detect_asset_type(text: str) -> AllowedAssetType:
    if any(word in text for word in ["enemy", "enemigo", "monster", "monstruo", "boss"]):
        return "enemy"
    if any(word in text for word in ["icon", "ícono", "icono", "ui", "item"]):
        return "icon"
    return "prop"


def _detect_subject(text: str) -> str:
    if "dragon" in text or "dragón" in text or "dragon" in _strip_accents(text):
        if any(word in text for word in ["baby", "bebé", "bebe", "small", "pequeño", "pequeno"]):
            return "baby dragon"
        return "dragon"
    if "chest" in text or "cofre" in text:
        return "treasure chest"
    if "potion" in text or "poción" in text or "pocion" in text:
        return "potion"
    if "sword" in text or "espada" in text:
        return "sword"
    if any(
        word in text for word in ["human", "humano", "persona", "person", "knight", "caballero", "ranger", "blacksmith"]
    ):
        return "human"
    return "game asset"


def _detect_view(text: str) -> AllowedView:
    if "top-down" in text or "top down" in text or "rpg" in text:
        return "top-down 3/4"
    if "side" in text or "plataforma" in text or "platform" in text:
        return "side-view"
    return "icon/front"


def _detect_style(text: str, subject: str) -> str:
    fantasy_subjects = {"baby dragon", "dragon", "treasure chest", "potion", "sword"}
    if "pixel" in text and subject in fantasy_subjects:
        return "pixel art fantasy"
    return "pixel art"


def _detect_palette(text: str, subject: str) -> PaletteSpec:
    if "dragon" in subject:
        return PaletteSpec(main=["orange", "dark red", "gold"], shadows=["purple", "dark blue"], accent=["yellow glow"])
    if subject == "treasure chest":
        return PaletteSpec(main=["brown", "gold"], shadows=["dark brown"], accent=["bright gold"])
    if subject == "potion":
        return PaletteSpec(main=["blue", "cyan"], shadows=["dark blue"], accent=["white shine"])
    colors = {
        "red": ["red", "rojo", "roja"],
        "blue": ["blue", "azul"],
        "green": ["green", "verde"],
        "brown": ["brown", "marrón", "marron"],
        "steel": ["steel", "acero"],
        "white": ["white", "blanco", "blanca"],
        "black": ["black", "negro", "negra"],
    }
    main = [name for name, aliases in colors.items() if any(alias in text for alias in aliases)]
    accent = ["gold"] if any(word in text for word in ["gold", "dorado", "dorada"]) else []
    if main or accent:
        return PaletteSpec(main=main or ["limited readable colors"], shadows=[], accent=accent)
    return PaletteSpec(main=["limited readable colors"], shadows=["dark outline"], accent=["small highlight"])


def _detect_character_spec(text: str, subject: str) -> CharacterSpec | None:
    if subject != "human":
        return None
    anatomy = AnatomySpec(
        height="short"
        if any(word in text for word in ["short", "bajito", "baja", "low"])
        else "tall"
        if any(word in text for word in ["tall", "alto", "alta"])
        else "average",
        build="heavy"
        if any(word in text for word in ["heavy", "fat", "gordo", "gorda", "robusto", "robusta"])
        else "slim"
        if any(word in text for word in ["slim", "thin", "delgado", "delgada"])
        else "average",
        head_size="large"
        if any(word in text for word in ["large head", "big head", "cabeza grande"])
        else "small"
        if any(word in text for word in ["small head", "cabeza pequeña", "cabeza pequena"])
        else "average",
        leg_length="short"
        if any(word in text for word in ["short legs", "piernas cortas"])
        else "long"
        if any(word in text for word in ["long legs", "piernas largas"])
        else "average",
    )
    return CharacterSpec(
        anatomy=anatomy,
        hair=HairSpec(
            style="short_messy" if any(word in text for word in ["messy hair", "cabello despeinado"]) else "none"
        ),
        clothing=ClothingSpec(
            upper="armor"
            if any(word in text for word in ["warrior", "knight", "caballero"])
            else "leather_apron"
            if any(word in text for word in ["apron", "delantal"])
            else "tunic"
        ),
        equipment=EquipmentSpec(
            hand="sword"
            if any(word in text for word in ["warrior", "knight", "caballero"])
            else "blacksmith_hammer"
            if any(word in text for word in ["hammer", "martillo"])
            else "none"
        ),
        materials=MaterialSpec(
            upper="metal"
            if any(word in text for word in ["warrior", "knight", "caballero"])
            else "leather"
            if any(word in text for word in ["leather", "cuero"])
            else "cloth"
        ),
    )


def _detect_shape(subject: str) -> ShapeSpec:
    if "dragon" in subject:
        return ShapeSpec(
            silhouette="small compact dragon with large head, tiny wings, curled tail",
            proportions={"head": "large", "body": "small", "wings": "small", "tail": "curled"},
        )
    return ShapeSpec(silhouette=f"clear compact {subject} silhouette", proportions={})


def _normalize(text: str) -> str:
    return text.strip().lower()


def _strip_accents(text: str) -> str:
    return text.translate(str.maketrans({"ó": "o", "é": "e", "í": "i", "á": "a", "ú": "u", "ñ": "n"}))


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).removesuffix("```").strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found")
    data = json.loads(stripped[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("top-level JSON is not an object")
    return data
