# FastAPI HTMX Service Template

Reusable local-first template for server services. It preserves the architecture pattern from `job-market-intelligence` without domain-specific code.

## Included

- FastAPI JSON API
- Jinja2 pages + HTMX partial responses
- Visible inline progress/success/error feedback with `hx-on::before-request` and `hx-on::after-request`
- Thin routes, Pydantic schemas, internal dataclasses, service layer
- JSON logs to stdout via `APP_LOG_LEVEL`
- Central settings in `app/services/settings.py` using `APP_*` env vars and optional `.env`
- Shared LLM manager for OpenAI-compatible and Anthropic providers
- SQLite + filesystem artifact store
- Tests for API, web pages, HTMX partials, artifact persistence, and LLM provider wiring

## Run

```bash
cd /home/erickesc/repos/fastapi-htmx-service-template
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8025
```

Open:

```text
http://127.0.0.1:8025
```

Health:

```bash
curl http://127.0.0.1:8025/health
```

Tests:

```bash
uv run pytest -q
```

## API example

```bash
curl -X POST http://127.0.0.1:8025/api/workflow/run \
  -H 'Content-Type: application/json' \
  -d '{"title":"Example","input_text":"hello template","use_llm":false}'
```

Generated runtime artifacts are saved under `items/runs/` and indexed in `data/app.sqlite`.

## Template conventions

- `app/routes/`: HTTP parsing, dependency injection, response shaping
- `app/schemas/`: Pydantic request/response contracts
- `app/models/`: internal dataclasses and DTOs
- `app/services/`: domain logic, persistence, settings, logging, LLM provider clients
- `app/templates/pages/`: full pages
- `app/templates/partials/`: HTMX fragments
- `app/static/styles.css`: all styling

## Environment variables

See `.env.example`. Important variables:

- `APP_ENV_FILE`: override `.env` path; empty string disables `.env`
- `APP_DATA_DIR`: SQLite/index directory
- `APP_ITEMS_DIR`: generated artifact directory
- `APP_LOG_LEVEL`: JSON log level
- `APP_LLM_PROVIDER`: `openai_compatible` or `anthropic`
- `APP_LLM_MODEL`
- `APP_LLM_BASE_URL`
- `APP_LLM_API_KEY`, `APP_OPENAI_API_KEY`, `APP_ANTHROPIC_API_KEY`
