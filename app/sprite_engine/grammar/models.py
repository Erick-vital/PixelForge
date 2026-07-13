from dataclasses import dataclass
from typing import Protocol

from app.schemas.sprite import AssetSpec, SpriteBlueprint


@dataclass(frozen=True)
class GrammarCapabilities:
    family: str
    views: frozenset[str]
    archetypes: frozenset[str]
    poses: frozenset[str]


class VisualGrammar(Protocol):
    name: str
    capabilities: GrammarCapabilities
    skeleton_name: str

    def supports(self, asset_spec: AssetSpec) -> bool: ...
    def compile(self, asset_spec: AssetSpec, *, seed: int) -> SpriteBlueprint: ...


@dataclass(frozen=True)
class GrammarResolution:
    grammar_name: str | None
    supported: bool
    reason: str
    grammar: VisualGrammar | None = None
