from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, StringConstraints
from typing_extensions import Annotated

from app.models.workflow import WorkflowInput


class WorkflowRunRequest(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = "Untitled workflow"
    input_text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    use_llm: bool = False
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None

    def to_workflow_input(self) -> WorkflowInput:
        return WorkflowInput(
            title=self.title,
            input_text=self.input_text,
            use_llm=self.use_llm,
            provider=self.provider,
            model=self.model,
            base_url=self.base_url,
        )


class WorkflowRunResponse(BaseModel):
    status: str
    title: str
    summary: str
    generated_text: str
    provider: str | None = None
    model: str | None = None
    paths: dict[str, str]


class SettingsResponse(BaseModel):
    data_dir: str
    items_dir: str
    llm_provider: str
    llm_default_model: str
    llm_base_url: str
    env_file: str | None
    app_log_level: str


class ErrorResponse(BaseModel):
    detail: str | list[dict[str, Any]]
