from __future__ import annotations

import json

from app.models.workflow import WorkflowInput, WorkflowOutput
from app.services.artifact_store import ArtifactStore


def test_artifact_store_writes_json_markdown_and_sqlite_index(tmp_path):
    store = ArtifactStore(data_dir=tmp_path / "data", items_dir=tmp_path / "items")
    saved = store.save_run(
        workflow_input=WorkflowInput(title="Store Test", input_text="abc", use_llm=False),
        workflow_output=WorkflowOutput(summary="Processed 3 characters without LLM.", generated_text="ABC"),
    )

    assert saved.run_id.startswith("run_")
    assert saved.run_dir.exists()
    assert saved.input_json_path.exists()
    assert saved.output_json_path.exists()
    assert saved.report_markdown_path.exists()
    assert (tmp_path / "data" / "app.sqlite").exists()

    output = json.loads(saved.output_json_path.read_text(encoding="utf-8"))
    assert output["summary"] == "Processed 3 characters without LLM."
    assert "# Store Test" in saved.report_markdown_path.read_text(encoding="utf-8")
