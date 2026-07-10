# PixelForge

PixelForge is a prompt-to-sprite service built with FastAPI + HTMX.

The product focus is:

1. Receive a natural-language prompt
2. Convert it into a canonical Asset Spec
3. Persist that spec as a sprite artifact item
4. Build a procedural blueprint from the artifact
5. Render a first-pass procedural PNG from the artifact
6. Optionally process an input sprite into a transparent PNG
7. Offer a simple browser front with a text box and button for the main prompt flow

## What the repo does now

- FastAPI JSON API
- Canonical Sprite Asset Spec with structured guidance sections
- Separate interpretation and processing services
- Procedural sprite rendering in Python with Pillow + NumPy
- 2D sprite post-processing with Pillow
- Jinja2 pages + HTMX partials for the sprite UI
- Visible inline progress/success/error feedback with `hx-on::before-request` and `hx-on::after-request`
- JSON logs to stdout via `APP_LOG_LEVEL`
- Central settings in `app/services/settings.py` using `APP_*` env vars and optional `.env`
- SQLite + filesystem artifact store for persisted runs and reports
- Hermetic tests

## Sprite front

The browser front lives at:

- `/sprite`

It has:
- a text box for the prompt
- a button to generate the result
- inline loading/success/error feedback
- an HTMX results panel that shows:
  - the sprite artifact ID
  - Asset Spec JSON
  - Blueprint JSON
- a procedural PNG render button with inline preview

## Sprite API

### `POST /api/asset-spec`

Turns a user prompt into a structured Asset Spec and persists it as a sprite artifact.

Example:

```bash
curl -X POST http://127.0.0.1:8025/api/asset-spec \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Quiero un dragón pequeño estilo pixel art, 64x64, para un RPG top-down"
  }'
```

Response includes:
- `artifact_id`
- `artifact_dir`
- `status`
- `subject`
- `asset_spec`

### `POST /api/blueprint`

Builds and stores a procedural blueprint from an existing sprite artifact.

Example:

```bash
curl -X POST http://127.0.0.1:8025/api/blueprint \
  -H "Content-Type: application/json" \
  -d '{
    "artifact_id": "sprite_20260709_190000_abcd1234",
    "seed": 123
  }'
```

### `POST /api/render-sprite`

Renders a first-pass procedural PNG directly from an existing sprite artifact. This path does not call an image model.

Example:

```bash
curl -X POST http://127.0.0.1:8025/api/render-sprite \
  -H "Content-Type: application/json" \
  -d '{
    "artifact_id": "sprite_20260709_190000_abcd1234",
    "seed": 123
  }' \
  --output baby-dragon.png
```

The first render recipes support:

- `baby dragon`
- `potion`
- `sword`

### `POST /api/render-blueprint`

Renders the stored blueprint for a sprite artifact into a PNG.

Example:

```bash
curl -X POST http://127.0.0.1:8025/api/render-blueprint \
  -H "Content-Type: application/json" \
  -d '{
    "artifact_id": "sprite_20260709_190000_abcd1234",
    "seed": 123
  }' \
  --output blueprint-dragon.png
```

### `POST /api/process-sprite`

Accepts a PNG upload plus `asset_spec_json` and returns a processed transparent PNG.

Example:

```bash
curl -X POST http://127.0.0.1:8025/api/process-sprite \
  -F 'asset_spec_json={"size":{"width":64,"height":64},"technical_constraints":{"transparent_background":true,"pixel_art":true}}' \
  -F 'image=@/path/to/input.png;type=image/png' \
  --output processed.png
```

## Sprite contract and pipeline

The canonical Asset Spec currently carries:

- `asset_type`
- `subject`
- `game_view`
- `style`
- `size`
- `palette`
- `shape`
- `technical_constraints`
- `prompt_guidance`
- `processing_profile`

Interpretation and processing are now separated in code:

- `app/services/sprite_interpretation.py` handles prompt interpretation
- `app/services/sprite_artifact_store.py` persists sprite artifact items on disk and in SQLite
- `app/services/procedural_sprite.py` handles blueprint creation and model-free procedural PNG rendering
- `app/services/sprite_processing.py` handles image processing with Pillow
- `app/services/sprite.py` is the orchestration layer used by the API and UI

## Run

```bash
cd /home/erickesc/repos/PixelForge
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8025
```

Open:

- `http://127.0.0.1:8025/` for the PixelForge home
- `http://127.0.0.1:8025/sprite` for the Sprite front

Health:

```bash
curl http://127.0.0.1:8025/health
```

Tests:

```bash
uv run pytest -q
```

## Template conventions

- `app/routes/`: HTTP parsing, dependency injection, response shaping
- `app/schemas/`: Pydantic request/response contracts
- `app/models/`: internal dataclasses and DTOs
- `app/services/`: domain logic, persistence, settings, logging, integrations
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

## Notes

- The MVP supports `enemy`, `prop`, and `icon` assets.
- Supported sizes: `32x32`, `64x64`, `128x128`.
- Supported views: `side-view`, `top-down 3/4`, `icon/front`.
- Output is PNG with transparency.
- The existing run/artifact subsystem remains available internally for persisted runs.
