from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_settings_env(monkeypatch, tmp_path):
    """Keep tests hermetic: ignore repo .env and use temp runtime paths."""
    monkeypatch.setenv("APP_ENV_FILE", "")
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("APP_ITEMS_DIR", str(tmp_path / "items"))
    monkeypatch.delenv("APP_LLM_API_KEY", raising=False)
    monkeypatch.delenv("APP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("APP_ANTHROPIC_API_KEY", raising=False)
