from __future__ import annotations

from pydantic import BaseModel


class SettingsResponse(BaseModel):
    data_dir: str
    items_dir: str
    llm_provider: str
    llm_default_model: str
    llm_base_url: str
    env_file: str | None
    app_log_level: str
