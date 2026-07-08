from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_pages_render_with_active_menu():
    client = TestClient(app)

    home = client.get("/")
    assert home.status_code == 200
    assert "Reusable FastAPI + HTMX service template" in home.text
    assert 'href="/workflow"' in home.text
    assert 'href="/settings"' in home.text
    assert 'href="/llm"' in home.text

    workflow = client.get("/workflow")
    assert workflow.status_code == 200
    assert 'hx-post="/ui/workflow/run"' in workflow.text
    assert 'hx-target="#results"' in workflow.text
    assert 'hx-on::before-request' in workflow.text
    assert 'hx-on::after-request' in workflow.text
    assert '<a href="/workflow" class="active" aria-current="page">' in workflow.text


def test_workflow_api_runs_and_persists_artifacts():
    response = TestClient(app).post(
        "/api/workflow/run",
        json={"title": "Template Smoke Test", "input_text": "hello from api", "use_llm": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["title"] == "Template Smoke Test"
    assert body["summary"] == "Processed 14 characters without LLM."
    assert Path(body["paths"]["run_dir"]).exists()
    assert Path(body["paths"]["input_json"]).exists()
    assert Path(body["paths"]["output_json"]).exists()
    assert Path(body["paths"]["report_markdown"]).exists()


def test_workflow_htmx_form_returns_partial_with_result():
    response = TestClient(app).post(
        "/ui/workflow/run",
        data={"title": "HTMX Run", "input_text": "hello from htmx", "use_llm": "false"},
    )

    assert response.status_code == 200
    assert "Workflow completed" in response.text
    assert "HTMX Run" in response.text
    assert "Processed 15 characters without LLM." in response.text
    assert "Saved to:" in response.text


def test_workflow_api_requires_input_text():
    response = TestClient(app).post(
        "/api/workflow/run",
        json={"title": "Missing", "input_text": "", "use_llm": False},
    )

    assert response.status_code == 422
