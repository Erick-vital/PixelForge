from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.models.sprite_artifact import SpriteArtifact
from app.schemas.sprite import AssetSpec, SpriteBlueprint

logger = logging.getLogger(__name__)


class SpriteArtifactStoreError(ValueError):
    pass


class SpriteArtifactStore:
    def __init__(self, *, data_dir: Path, items_dir: Path) -> None:
        self.data_dir = data_dir
        self.items_dir = items_dir
        self.db_path = data_dir / "app.sqlite"
        self.sprite_items_dir = items_dir / "sprite-artifacts"

    def init_db(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sprite_items_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sprite_artifacts (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    artifact_dir TEXT NOT NULL,
                    asset_spec_json_path TEXT NOT NULL,
                    blueprint_json_path TEXT,
                    render_png_path TEXT
                )
                """
            )
            conn.commit()

    def create_asset_spec_artifact(self, *, prompt: str, asset_spec: AssetSpec) -> SpriteArtifact:
        self.init_db()
        artifact_id = _new_id("sprite")
        artifact_dir = self.sprite_items_dir / artifact_id
        artifact_dir.mkdir(parents=True, exist_ok=False)
        asset_spec_json_path = artifact_dir / "asset-spec.json"
        blueprint_json_path = artifact_dir / "blueprint.json"
        render_png_path = artifact_dir / "render.png"

        _write_json(asset_spec_json_path, asset_spec.model_dump(mode="json"))
        created_at = _iso_now()
        metadata = {
            "artifact_id": artifact_id,
            "created_at": created_at,
            "updated_at": created_at,
            "status": "asset_spec_ready",
            "prompt": prompt,
            "subject": asset_spec.subject,
            "title": f"sprite:{asset_spec.subject}",
            "asset_spec_json_path": str(asset_spec_json_path),
            "blueprint_json_path": str(blueprint_json_path),
            "render_png_path": str(render_png_path),
        }
        _write_json(artifact_dir / "metadata.json", metadata)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sprite_artifacts
                (id, created_at, title, status, prompt, subject, artifact_dir, asset_spec_json_path, blueprint_json_path, render_png_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    metadata["created_at"],
                    metadata["title"],
                    metadata["status"],
                    prompt,
                    asset_spec.subject,
                    str(artifact_dir),
                    str(asset_spec_json_path),
                    str(blueprint_json_path),
                    str(render_png_path),
                ),
            )
            conn.commit()

        logger.info(
            "sprite artifact created",
            extra={"artifact_id": artifact_id, "artifact_dir": str(artifact_dir), "subject": asset_spec.subject},
        )
        return SpriteArtifact(
            artifact_id=artifact_id,
            artifact_dir=artifact_dir,
            asset_spec_json_path=asset_spec_json_path,
            blueprint_json_path=None,
            render_png_path=None,
            status="asset_spec_ready",
            title=metadata["title"],
            prompt=prompt,
            subject=asset_spec.subject,
        )

    def load_artifact(self, artifact_id: str) -> SpriteArtifact:
        self.init_db()
        row = self._fetch_row(artifact_id)
        if row is None:
            raise SpriteArtifactStoreError(f"Unknown sprite artifact: {artifact_id}")
        return SpriteArtifact(
            artifact_id=row["id"],
            artifact_dir=Path(row["artifact_dir"]),
            asset_spec_json_path=Path(row["asset_spec_json_path"]),
            blueprint_json_path=Path(row["blueprint_json_path"]) if row["blueprint_json_path"] else None,
            render_png_path=Path(row["render_png_path"]) if row["render_png_path"] else None,
            status=row["status"],
            title=row["title"],
            prompt=row["prompt"],
            subject=row["subject"],
        )

    def read_asset_spec(self, artifact_id: str) -> AssetSpec:
        artifact = self.load_artifact(artifact_id)
        return AssetSpec.model_validate(json.loads(artifact.asset_spec_json_path.read_text(encoding="utf-8")))

    def read_blueprint(self, artifact_id: str) -> SpriteBlueprint:
        artifact = self.load_artifact(artifact_id)
        if artifact.blueprint_json_path is None or not artifact.blueprint_json_path.exists():
            raise SpriteArtifactStoreError(f"Sprite artifact {artifact_id} does not yet have a blueprint")
        return SpriteBlueprint.model_validate(json.loads(artifact.blueprint_json_path.read_text(encoding="utf-8")))

    def save_blueprint(
        self, artifact_id: str, blueprint: SpriteBlueprint, *, generation: dict[str, object] | None = None
    ) -> SpriteArtifact:
        artifact = self.load_artifact(artifact_id)
        if not artifact.blueprint_json_path:
            raise SpriteArtifactStoreError(f"Sprite artifact {artifact_id} is missing blueprint path")
        _write_json(artifact.blueprint_json_path, blueprint.model_dump(mode="json"))
        self._update_status(artifact_id, status="blueprint_ready", blueprint_generation=generation)
        logger.info(
            "sprite blueprint saved",
            extra={"artifact_id": artifact_id, "blueprint_path": str(artifact.blueprint_json_path)},
        )
        return self.load_artifact(artifact_id)

    def save_render_png(self, artifact_id: str, png_bytes: bytes) -> SpriteArtifact:
        artifact = self.load_artifact(artifact_id)
        render_png_path = artifact.render_png_path or (artifact.artifact_dir / "render.png")
        render_png_path.write_bytes(png_bytes)
        self._update_render_path(artifact_id, render_png_path)
        logger.info(
            "sprite render saved",
            extra={"artifact_id": artifact_id, "render_png_path": str(render_png_path)},
        )
        return self.load_artifact(artifact_id)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _fetch_row(self, artifact_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM sprite_artifacts WHERE id = ?", (artifact_id,)).fetchone()

    def _update_status(
        self,
        artifact_id: str,
        *,
        status: str,
        blueprint_generation: dict[str, object] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE sprite_artifacts SET status = ? WHERE id = ?", (status, artifact_id))
            conn.commit()
        self._write_metadata(artifact_id, status=status, blueprint_generation=blueprint_generation)

    def _update_render_path(self, artifact_id: str, render_png_path: Path) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sprite_artifacts SET render_png_path = ?, status = ? WHERE id = ?",
                (str(render_png_path), "rendered", artifact_id),
            )
            conn.commit()
        self._write_metadata(artifact_id, status="rendered", render_png_path=render_png_path)

    def _write_metadata(
        self,
        artifact_id: str,
        *,
        status: str,
        render_png_path: Path | None = None,
        blueprint_generation: dict[str, object] | None = None,
    ) -> None:
        artifact = self.load_artifact(artifact_id)
        metadata_path = artifact.artifact_dir / "metadata.json"
        existing = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
        metadata = {
            "artifact_id": artifact.artifact_id,
            "created_at": existing.get("created_at", _iso_now()),
            "updated_at": _iso_now(),
            "status": status,
            "prompt": artifact.prompt,
            "subject": artifact.subject,
            "title": artifact.title,
            "asset_spec_json_path": str(artifact.asset_spec_json_path),
            "blueprint_json_path": str(artifact.blueprint_json_path) if artifact.blueprint_json_path else None,
            "render_png_path": str(render_png_path or artifact.render_png_path)
            if (render_png_path or artifact.render_png_path)
            else None,
        }
        saved_generation = blueprint_generation or existing.get("blueprint_generation")
        if saved_generation is not None:
            metadata["blueprint_generation"] = saved_generation
        _write_json(metadata_path, metadata)


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{stamp}_{uuid.uuid4().hex[:8]}"
