from app.models.humanoid import HumanoidSkeleton as LegacyHumanoidSkeleton
from app.services.humanoid_sprite import compile_humanoid_base as legacy_compile_humanoid_base
from app.services.sprite_quality import evaluate_sprite_quality as legacy_evaluate_sprite_quality


def test_sprite_engine_exposes_initial_domain_modules_and_legacy_imports_remain_compatible():
    from app.sprite_engine.character.skeleton import HumanoidSkeleton
    from app.sprite_engine.quality.structural import evaluate_sprite_quality
    from app.sprite_engine.recipes.humanoid import compile_humanoid_base

    assert HumanoidSkeleton is LegacyHumanoidSkeleton
    assert compile_humanoid_base is legacy_compile_humanoid_base
    assert evaluate_sprite_quality is legacy_evaluate_sprite_quality
