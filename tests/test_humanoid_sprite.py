from __future__ import annotations

import io

from PIL import Image

from app.models.humanoid import HumanoidSkeleton
from app.services.humanoid_sprite import compile_humanoid_base
from app.services.procedural_sprite import render_blueprint
from app.services.sprite_quality import evaluate_sprite_quality


def test_default_chibi_skeleton_has_grounded_symmetric_anchors():
    skeleton = HumanoidSkeleton()

    assert skeleton.center_x == 32
    assert skeleton.ground_y == 58
    assert skeleton.mirror_x(25) == 39
    assert skeleton.head_top_y < skeleton.head_bottom_y < skeleton.ground_y


def test_humanoid_compiler_creates_a_quality_passing_chibi_blueprint():
    palette = {"outline": "#202020", "base": "#7a9b4f", "shadow": "#3d552c", "highlight": "#b5d178"}
    blueprint = compile_humanoid_base("human chibi", palette)

    result = render_blueprint(blueprint, width=64, height=64)
    image = Image.open(io.BytesIO(result.png_bytes))
    quality = evaluate_sprite_quality(image)

    assert blueprint.recipe == "humanoid_chibi"
    assert blueprint.outline.enabled is True
    assert quality.passed is True
    assert image.getbbox() is not None
