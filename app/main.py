from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes.api import router as api_router
from app.routes.web import router as web_router
from app.services.logging_config import configure_logging

configure_logging()

app = FastAPI(
    title="PixelForge",
    version="0.1.0",
    description="Prompt-to-sprite service with API, HTMX UI, JSON logs, and optional LLM calls.",
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(web_router)
app.include_router(api_router)
