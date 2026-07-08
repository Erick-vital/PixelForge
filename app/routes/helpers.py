from __future__ import annotations

import logging

from app.models.workflow import WorkflowResult
from app.schemas.workflow import WorkflowRunRequest
from app.services.llm_generation import LlmGenerationProviderError
from app.services.settings import MissingLlmApiKeyError
from app.services.workflow_service import WorkflowService

logger = logging.getLogger(__name__)


class WorkflowHttpError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


async def run_workflow_for_request(service: WorkflowService, payload: WorkflowRunRequest, *, source: str) -> WorkflowResult:
    logger.info(
        f"workflow {source} run requested",
        extra={
            "title": payload.title,
            "input_chars": len(payload.input_text),
            "use_llm": payload.use_llm,
            "provider": payload.provider,
            "model_supplied": bool(payload.model),
            "base_url_supplied": bool(payload.base_url),
        },
    )
    try:
        result = await service.run(payload.to_workflow_input())
    except MissingLlmApiKeyError as exc:
        logger.warning(f"workflow {source} run missing api key", extra={"error": str(exc)})
        raise WorkflowHttpError(status_code=400, detail=str(exc)) from exc
    except LlmGenerationProviderError as exc:
        logger.warning(f"workflow {source} run provider error", extra={"status_code": exc.status_code, "error": str(exc)})
        raise WorkflowHttpError(status_code=502, detail=str(exc)) from exc
    logger.info(f"workflow {source} run completed", extra={"title": result.title, "run_dir": str(result.saved_run.run_dir)})
    return result
