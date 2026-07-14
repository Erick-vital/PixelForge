from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.models.sprite_artifact import SpriteArtifact
from app.schemas.sprite import AssetSpec, AssetSpecDecisionTrace, SpriteBlueprint
from app.services.trace_context import get_trace_context, trace_details

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

    def create_asset_spec_artifact(
        self, *, prompt: str, asset_spec: AssetSpec, decision_trace: AssetSpecDecisionTrace | None = None
    ) -> SpriteArtifact:
        self.init_db()
        artifact_id = _new_id("sprite")
        artifact_dir = self.sprite_items_dir / artifact_id
        artifact_dir.mkdir(parents=True, exist_ok=False)
        asset_spec_json_path = artifact_dir / "asset-spec.json"
        blueprint_json_path = artifact_dir / "blueprint.json"
        render_png_path = artifact_dir / "render.png"

        _write_json(asset_spec_json_path, asset_spec.model_dump(mode="json"))
        created_at = _iso_now()
        metadata: dict[str, Any] = {
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
        if decision_trace is not None:
            metadata["decision_trace"] = decision_trace.model_dump(mode="json")
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
        self.append_trace_event(
            artifact_id,
            event_type="artifact.created",
            stage="asset_spec",
            outcome="completed",
            status_after="asset_spec_ready",
            details={"subject": asset_spec.subject},
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
        try:
            payload = json.loads(artifact.asset_spec_json_path.read_text(encoding="utf-8"))
            return AssetSpec.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise SpriteArtifactStoreError(f"Sprite artifact {artifact_id} contains an invalid Asset Spec") from exc

    def read_blueprint(self, artifact_id: str) -> SpriteBlueprint:
        artifact = self.load_artifact(artifact_id)
        if artifact.blueprint_json_path is None or not artifact.blueprint_json_path.exists():
            raise SpriteArtifactStoreError(f"Sprite artifact {artifact_id} does not yet have a blueprint")
        return SpriteBlueprint.model_validate(json.loads(artifact.blueprint_json_path.read_text(encoding="utf-8")))

    def read_metadata(self, artifact_id: str) -> dict[str, object]:
        artifact = self.load_artifact(artifact_id)
        path = artifact.artifact_dir / "metadata.json"
        if not path.exists():
            raise SpriteArtifactStoreError(f"Sprite artifact {artifact_id} has no metadata")
        return json.loads(path.read_text(encoding="utf-8"))

    def save_blueprint(
        self, artifact_id: str, blueprint: SpriteBlueprint, *, generation: dict[str, object] | None = None
    ) -> SpriteArtifact:
        artifact = self.load_artifact(artifact_id)
        if not artifact.blueprint_json_path:
            raise SpriteArtifactStoreError(f"Sprite artifact {artifact_id} is missing blueprint path")
        _write_json(artifact.blueprint_json_path, blueprint.model_dump(mode="json"))
        self._update_status(
            artifact_id,
            status="blueprint_ready",
            blueprint_generation=generation,
            clear_generation_error=True,
        )
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

    def mark_blueprint_failed(
        self,
        artifact_id: str,
        *,
        generation_error: dict[str, object],
        trace_event_details: dict[str, object] | None = None,
    ) -> SpriteArtifact:
        """Persist bounded diagnostics without writing a rejected blueprint or render."""
        self._update_status(artifact_id, status="blueprint_failed", generation_error=generation_error)
        self.append_trace_event(
            artifact_id,
            event_type="blueprint.generation.failed",
            stage="blueprint",
            outcome="failed",
            status_after="blueprint_failed",
            details=trace_details(issue_codes=generation_error.get("issue_codes"), **(trace_event_details or {})),
        )
        return self.load_artifact(artifact_id)

    def append_trace_event(
        self,
        artifact_id: str,
        *,
        event_type: str,
        stage: str,
        outcome: str,
        status_before: str | None = None,
        status_after: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        """Append a compact, safe domain event to an artifact-local timeline."""
        artifact = self.load_artifact(artifact_id)
        context = get_trace_context()
        event: dict[str, object] = {
            "event_schema_version": 1,
            "occurred_at": _trace_iso_now(),
            "artifact_id": artifact_id,
            "event_type": event_type,
            "stage": stage,
            "outcome": outcome,
            "details": details or {},
        }
        for key in ("request_id", "operation_id"):
            if key in context:
                event[key] = context[key]
        if status_before is not None:
            event["status_before"] = status_before
        if status_after is not None:
            event["status_after"] = status_after
        trace_path = artifact.artifact_dir / "trace.jsonl"
        with trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        logger.info(
            "sprite artifact trace event recorded",
            extra={
                "artifact_id": artifact_id,
                "event_type": event_type,
                "stage": stage,
                "outcome": outcome,
            },
        )

    def read_trace_events(self, artifact_id: str) -> list[dict[str, object]]:
        artifact = self.load_artifact(artifact_id)
        trace_path = artifact.artifact_dir / "trace.jsonl"
        if not trace_path.exists():
            return []
        try:
            return [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line]
        except json.JSONDecodeError as exc:
            raise SpriteArtifactStoreError(f"Sprite artifact {artifact_id} contains an invalid trace") from exc

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
        generation_error: dict[str, object] | None = None,
        clear_generation_error: bool = False,
    ) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE sprite_artifacts SET status = ? WHERE id = ?", (status, artifact_id))
            conn.commit()
        self._write_metadata(
            artifact_id,
            status=status,
            blueprint_generation=blueprint_generation,
            generation_error=generation_error,
            clear_generation_error=clear_generation_error,
        )

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
        generation_error: dict[str, object] | None = None,
        clear_generation_error: bool = False,
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
        saved_error = None if clear_generation_error else generation_error or existing.get("generation_error")
        if saved_error is not None:
            metadata["generation_error"] = saved_error
        decision_trace = existing.get("decision_trace")
        if decision_trace is not None:
            metadata["decision_trace"] = decision_trace
        _write_json(metadata_path, metadata)


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _trace_iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{stamp}_{uuid.uuid4().hex[:8]}"
