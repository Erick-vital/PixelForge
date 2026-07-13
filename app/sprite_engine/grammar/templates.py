from __future__ import annotations

from dataclasses import dataclass

from app.schemas.sprite import AllowedView, AssetFamily


class TemplateResolutionError(ValueError):
    """Raised when a client asks for a template outside the bounded registry."""


@dataclass(frozen=True)
class SpriteTemplate:
    template_id: str
    family: AssetFamily
    archetype: str
    view: AllowedView
    character_stance: str | None = None

    @property
    def constraints(self) -> dict[str, str]:
        result = {
            "family": self.family,
            "archetype": self.archetype,
            "game_view": self.view,
        }
        if self.character_stance is not None:
            result["character.pose.stance"] = self.character_stance
        return result


_TEMPLATES: dict[str, SpriteTemplate] = {
    "warrior_front": SpriteTemplate(
        "warrior_front", "humanoid", "warrior", "icon/front", character_stance="front_neutral"
    ),
    "warrior_side": SpriteTemplate("warrior_side", "humanoid", "warrior", "side-view", character_stance="side_neutral"),
    "wizard_front": SpriteTemplate(
        "wizard_front", "humanoid", "wizard", "icon/front", character_stance="front_neutral"
    ),
    "pig_side": SpriteTemplate("pig_side", "quadruped", "pig", "side-view"),
}


def resolve_template(template_id: str) -> SpriteTemplate:
    try:
        return _TEMPLATES[template_id]
    except KeyError as exc:
        raise TemplateResolutionError(f"unknown template: {template_id}") from exc


__all__ = ["SpriteTemplate", "TemplateResolutionError", "resolve_template"]
