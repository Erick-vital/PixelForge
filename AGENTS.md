# AGENTS.md

This repository is a reusable FastAPI + HTMX service template.

## Goal

Keep the architecture generic and reusable for future internal services.
Avoid adding domain-specific behavior unless the repo is explicitly being specialized.

## Development rules

- Keep routes thin.
  - `app/routes/` should only parse requests, call services, and return JSON or templates.
- Put business logic in `app/services/`.
- Keep request/response contracts in `app/schemas/`.
- Keep internal dataclasses and DTOs in `app/models/`.
- Use Jinja2 server-side templates.
- Use HTMX for progressive enhancement and partial HTML responses.
- Full pages live in `app/templates/pages/`.
- Partial fragments live in `app/templates/partials/`.
- Keep styling in `app/static/styles.css`.
- Preserve the `#results` HTMX swap pattern for interactive pages.
- Preserve visible inline feedback with `hx-on::before-request` and `hx-on::after-request`.
- Keep logging structured and JSON-formatted.
- Never log secrets or full API keys.
- Use `APP_*` environment variables and `app/services/settings.py` for config.
- Use `app/services/llm_generation.py` for provider-specific LLM calls.
- Use `app/services/artifact_store.py` for persisted outputs and run artifacts.
- Tests should stay hermetic.
  - `tests/conftest.py` disables repo `.env` by setting `APP_ENV_FILE=""`.

## Verification

Before finishing changes:

- Run `uv run ruff check .` and `uv run ruff format --check .` (use `--fix` / drop `--check` to apply)
- Run `uv run pytest -q`
- If you touch runtime behavior, verify the app starts with `uv run uvicorn app.main:app`
- Prefer adding or updating tests when behavior changes

## Design guidance

When adding a new service, follow the same pattern:

- `routes/` for HTTP
- `schemas/` for input/output contracts
- `models/` for internal data structures
- `services/` for logic, persistence, logging, and integrations
- `templates/` for UI only when the service needs a human-facing view

If a change would introduce a new domain, keep it isolated so the template stays reusable.
