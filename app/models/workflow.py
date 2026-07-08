from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkflowInput:
    title: str
    input_text: str
    use_llm: bool = False
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None


@dataclass(frozen=True)
class WorkflowOutput:
    summary: str
    generated_text: str
    provider: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class SavedRun:
    run_id: str
    run_dir: Path
    input_json_path: Path
    output_json_path: Path
    report_markdown_path: Path


@dataclass(frozen=True)
class WorkflowResult:
    status: str
    title: str
    summary: str
    generated_text: str
    saved_run: SavedRun
    provider: str | None = None
    model: str | None = None

    def to_response_dict(self) -> dict:
        return {
            "status": self.status,
            "title": self.title,
            "summary": self.summary,
            "generated_text": self.generated_text,
            "provider": self.provider,
            "model": self.model,
            "paths": {
                "run_dir": str(self.saved_run.run_dir),
                "input_json": str(self.saved_run.input_json_path),
                "output_json": str(self.saved_run.output_json_path),
                "report_markdown": str(self.saved_run.report_markdown_path),
            },
        }
