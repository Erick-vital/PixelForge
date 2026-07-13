from app.schemas.sprite import AssetSpec, SpriteBlueprint
from app.sprite_engine.grammar.models import GrammarCapabilities


class LegacyRecipeGrammar:
    """Adapter for historically supported dragon/prop recipes; geometry remains in the legacy service."""

    name = "legacy_recipe"
    skeleton_name = "none"
    capabilities = GrammarCapabilities("legacy", frozenset(), frozenset(), frozenset())

    def supports(self, asset_spec: AssetSpec) -> bool:
        return False

    def compile(self, asset_spec: AssetSpec, *, seed: int) -> SpriteBlueprint:
        raise NotImplementedError
