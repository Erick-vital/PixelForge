from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes.admin import router as admin_router
from app.routes.api import router as api_router
from app.routes.web import router as web_router
from app.services.logging_config import configure_logging
from app.services.trace_context import log_context

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="PixelForge",
    version="0.1.0",
    description="Prompt-to-sprite service with API, HTMX UI, JSON logs, and optional LLM calls.",
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.middleware("http")
async def add_request_trace(request, call_next):
    request_id = request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex}"
    operation_id = f"op_{uuid.uuid4().hex}"
    started_at = time.perf_counter()
    with log_context(
        request_id=request_id,
        operation_id=operation_id,
        route=request.url.path,
        method=request.method,
    ):
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "http request failed",
                extra={"operation": "http", "outcome": "failed", "duration_ms": _elapsed_ms(started_at)},
            )
            raise
        logger.info(
            "http request completed",
            extra={
                "operation": "http",
                "outcome": "completed",
                "status_code": response.status_code,
                "duration_ms": _elapsed_ms(started_at),
            },
        )
    response.headers["X-Request-Id"] = request_id
    return response


def _elapsed_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(web_router)
app.include_router(api_router)
app.include_router(admin_router)
