"""Render the reproducible front-grammar benchmark outside product artifacts."""

import json
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.schemas.sprite import AssetSpec  # noqa: E402
from app.services.procedural_sprite import render_blueprint  # noqa: E402
from app.sprite_engine.grammar import default_grammar_registry  # noqa: E402

FIXTURES = ROOT / "tests/fixtures/grammar_specs"
OUTPUT = Path("/tmp/pixelforge-grammar-front-contact-sheet.png")


def main() -> None:
    names = ("warrior_front", "wizard_front", "blacksmith_front")
    sheet = Image.new("RGBA", (64 * len(names), 80), "white")
    draw = ImageDraw.Draw(sheet)
    for index, name in enumerate(names):
        spec = AssetSpec.model_validate_json((FIXTURES / f"{name}.json").read_text())
        blueprint = default_grammar_registry.compile(spec, seed=0)
        rendered = render_blueprint(blueprint, width=64, height=64)
        sheet.alpha_composite(Image.open(BytesIO(rendered.png_bytes)), (index * 64, 0))
        draw.text((index * 64 + 2, 66), name.split("_")[0], fill="black")
    sheet.save(OUTPUT)
    print(json.dumps({"output": str(OUTPUT), "mode": sheet.mode, "size": sheet.size}))


if __name__ == "__main__":
    main()
