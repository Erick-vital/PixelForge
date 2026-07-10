from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SpriteArtifact:
    artifact_id: str
    artifact_dir: Path
    asset_spec_json_path: Path
    blueprint_json_path: Path | None = None
    render_png_path: Path | None = None
    status: str = "asset_spec_ready"
    title: str = ""
    prompt: str = ""
    subject: str = ""
