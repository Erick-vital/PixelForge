from __future__ import annotations

import logging
from dataclasses import dataclass

from app.models.workflow import WorkflowInput, WorkflowOutput, WorkflowResult
from app.services.artifact_store import ArtifactStore
from app.services.llm_generation import LlmGenerationService
from app.services.settings import WorkflowSettings, get_workflow_settings

logger = logging.getLogger(__name__)


@dataclass
class WorkflowService:
    settings: WorkflowSettings
    llm_service: LlmGenerationService | None = None

    async def run(self, workflow_input: WorkflowInput) -> WorkflowResult:
        logger.info(
            "workflow service run started",
            extra={"title": workflow_input.title, "input_chars": len(workflow_input.input_text), "use_llm": workflow_input.use_llm},
        )
        if workflow_input.use_llm:
            llm = self.llm_service or LlmGenerationService()
            llm_result = await llm.generate_text(
                system_prompt="You are a concise automation service. Return a useful result for the provided input.",
                prompt=workflow_input.input_text,
                provider=workflow_input.provider,
                model=workflow_input.model,
                base_url=workflow_input.base_url,
            )
            output = WorkflowOutput(
                summary=f"Generated text with {llm_result.provider}/{llm_result.model}.",
                generated_text=llm_result.text,
                provider=llm_result.provider,
                model=llm_result.model,
            )
        else:
            output = WorkflowOutput(
                summary=f"Processed {len(workflow_input.input_text)} characters without LLM.",
                generated_text=workflow_input.input_text.upper(),
            )
        saved = ArtifactStore(data_dir=self.settings.data_dir, items_dir=self.settings.items_dir).save_run(
            workflow_input=workflow_input, workflow_output=output
        )
        logger.info("workflow service run completed", extra={"title": workflow_input.title, "run_id": saved.run_id})
        return WorkflowResult(
            status="completed",
            title=workflow_input.title,
            summary=output.summary,
            generated_text=output.generated_text,
            saved_run=saved,
            provider=output.provider,
            model=output.model,
        )


def build_workflow_service_from_env() -> WorkflowService:
    return WorkflowService(settings=get_workflow_settings())
