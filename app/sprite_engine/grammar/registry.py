from app.schemas.sprite import AssetSpec, SpriteBlueprint
from app.sprite_engine.grammar.humanoid_front import HumanoidFrontGrammar
from app.sprite_engine.grammar.humanoid_side import HumanoidSideGrammar
from app.sprite_engine.grammar.models import GrammarResolution, VisualGrammar
from app.sprite_engine.grammar.quadruped_side import QuadrupedSideGrammar


class GrammarRegistry:
    def __init__(self, grammars: tuple[VisualGrammar, ...] | None = None):
        self.grammars = grammars or (HumanoidFrontGrammar(), HumanoidSideGrammar(), QuadrupedSideGrammar())

    def resolve(self, asset_spec: AssetSpec) -> GrammarResolution:
        for grammar in self.grammars:
            if grammar.supports(asset_spec):
                return GrammarResolution(grammar.name, True, "capability match", grammar)
        return GrammarResolution(
            None, False, f"no grammar supports {asset_spec.family} {asset_spec.game_view} {asset_spec.archetype}"
        )

    def compile(self, asset_spec: AssetSpec, *, seed: int) -> SpriteBlueprint:
        resolution = self.resolve(asset_spec)
        if resolution.grammar is None:
            raise ValueError(resolution.reason)
        return resolution.grammar.compile(asset_spec, seed=seed)


default_grammar_registry = GrammarRegistry()
