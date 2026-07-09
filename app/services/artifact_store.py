from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app.models.workflow import SavedRun, WorkflowInput, WorkflowOutput

logger = logging.getLogger(__name__)


class ArtifactStore:
    def __init__(self, *, data_dir: Path, items_dir: Path) -> None:
        self.data_dir = data_dir
        self.items_dir = items_dir
        self.db_path = data_dir / "app.sqlite"

    def init_db(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.items_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_chars INTEGER NOT NULL,
                    provider TEXT,
                    model TEXT,
                    run_dir TEXT NOT NULL,
                    input_json_path TEXT NOT NULL,
                    output_json_path TEXT NOT NULL,
                    report_markdown_path TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def save_run(self, *, workflow_input: WorkflowInput, workflow_output: WorkflowOutput) -> SavedRun:
        self.init_db()
        run_id = _new_id("run")
        run_dir = self.items_dir / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        input_json_path = run_dir / "input.json"
        output_json_path = run_dir / "output.json"
        report_markdown_path = run_dir / "report.md"

        _write_json(input_json_path, asdict(workflow_input))
        _write_json(output_json_path, asdict(workflow_output))
        report_markdown_path.write_text(_report_markdown(workflow_input, workflow_output), encoding="utf-8")

        now = _iso_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO workflow_runs
                (id, created_at, title, status, input_chars, provider, model, run_dir, input_json_path, output_json_path, report_markdown_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    now,
                    workflow_input.title,
                    "completed",
                    len(workflow_input.input_text),
                    workflow_output.provider,
                    workflow_output.model,
                    str(run_dir),
                    str(input_json_path),
                    str(output_json_path),
                    str(report_markdown_path),
                ),
            )
            conn.commit()
        logger.info(
            "workflow run saved",
            extra={"run_id": run_id, "run_dir": str(run_dir), "input_chars": len(workflow_input.input_text)},
        )
        return SavedRun(
            run_id=run_id,
            run_dir=run_dir,
            input_json_path=input_json_path,
            output_json_path=output_json_path,
            report_markdown_path=report_markdown_path,
        )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _report_markdown(workflow_input: WorkflowInput, workflow_output: WorkflowOutput) -> str:
    provider_line = f"- Provider: {workflow_output.provider or 'none'}\n- Model: {workflow_output.model or 'none'}"
    return f"# {workflow_input.title}\n\n- Status: completed\n- Input characters: {len(workflow_input.input_text)}\n{provider_line}\n\n## Summary\n\n{workflow_output.summary}\n\n## Generated text\n\n{workflow_output.generated_text}\n"


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{stamp}_{uuid.uuid4().hex[:8]}"
