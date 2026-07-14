# Visual Critique Cycle Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add one bounded visual critique-and-revision pass after an LLM blueprint is rendered, so PixelForge can detect visual defects that schema and semantic geometry checks cannot reliably assess.

**Architecture:** Keep the existing contract `AssetSpec -> SpriteBlueprint -> generic renderer -> PNG`. The new critic is a separate service that receives a provisional PNG, canonical Asset Spec, and safe blueprint summary; it returns structured issue codes only. A failed visual critique triggers at most one targeted LLM blueprint revision, then the normal schema, structural, semantic, and rendering gates run again. This plan does not train or deploy a proprietary model.

**Tech Stack:** FastAPI, Pydantic, existing `LlmGenerationService`, Pillow PNG bytes, pytest, Ruff, uv.

---

## Preconditions and scope

- Complete semantic part tags and family validators first. The critic must receive those tags and deterministic issue codes as context.
- Preserve the generic renderer: it must never acquire wizard, wolf, belt, or weapon-specific code.
- Never send API keys, raw provider headers, or full user prompts to a critic.
- Keep the pass bounded: one critique and, only if needed, one revision. Do not create loops.
- Make the capability opt-in initially through an explicit `visual_critique` generation option; do not alter the default latency/cost profile without measurement.

## Task 1: Define critic contracts

**Objective:** Create explicit, safe structured inputs and outputs for visual evaluation.

**Files:**
- Modify: `app/schemas/sprite.py`
- Create: `app/services/sprite_visual_critique.py`
- Test: `tests/test_sprite_visual_critique.py`

**Step 1: Write failing tests**

Test that a `VisualCritique` model accepts only:

```python
{
  "passed": False,
  "issues": ["belt_color_too_bright", "held_item_not_attached"],
  "summary": "short bounded explanation"
}
```

Test that unknown issue codes, duplicate codes, raw candidate text, or arbitrary extra keys are rejected.

**Step 2: Run tests red**

```bash
uv run pytest -q tests/test_sprite_visual_critique.py
```

**Step 3: Implement minimal Pydantic contracts**

Create a fixed issue-code enum covering initial categories: silhouette clarity, prompt mismatch, held-item attachment, belt contrast, limb attachment, quadruped anatomy, and layer-order/grounding. Cap issue count and summary length.

**Step 4: Run tests green**

```bash
uv run pytest -q tests/test_sprite_visual_critique.py
```

## Task 2: Build a provider-independent critique service

**Objective:** Request structured critique of a provisional render without persisting rejected content.

**Files:**
- Create: `app/services/sprite_visual_critique.py`
- Modify: `app/services/llm_generation.py` only if an image-capable request abstraction is required
- Test: `tests/test_sprite_visual_critique.py`

**Step 1: Write failing tests**

Use a fake provider and assert that the service receives:

- a data URL or bounded PNG bytes for the provisional render;
- canonical `AssetSpec.model_dump(mode="json")` without the raw prompt;
- a safe semantic-part summary rather than unbounded blueprint prose;
- a strict JSON-only system prompt.

Test provider failure maps to a controlled `VisualCritiqueError` and does not change artifact status.

**Step 2: Implement the service**

Add `critique_sprite_render(...) -> VisualCritique`. Select a configured vision-capable provider/model explicitly; return a controlled unavailable result when none is configured. Log only provider/model, artifact ID, pass/fail, and issue codes.

**Step 3: Verify**

```bash
uv run pytest -q tests/test_sprite_visual_critique.py
```

## Task 3: Add a single revision pass to blueprint generation

**Objective:** Turn actionable critique issues into one bounded targeted revision.

**Files:**
- Modify: `app/services/sprite_blueprint.py`
- Modify: `app/services/sprite.py`
- Test: `tests/test_sprite_blueprint_generation.py`
- Test: `tests/test_sprite_visual_critique.py`

**Step 1: Write failing integration tests**

Assert this sequence:

```text
initial valid blueprint
-> provisional render
-> critique fails with issue codes
-> one revision LLM call containing the canonical spec, safe issue codes, and initial blueprint as untrusted data
-> full validation + final render
```

Assert that a passing critique causes no revision and that a failing revised candidate returns a controlled domain error without a third call.

**Step 2: Implement a separate revision budget**

The initial malformed-JSON repair and visual revision must be explicitly budgeted and observable. Prefer a single combined revision call if either validation or critique fails, so total model revisions remain bounded.

**Step 3: Persist lineage**

Record requested critique mode, provider/model, critique issue codes, whether a revision occurred, and final pass status in `blueprint_generation`. Do not persist rejected image or raw model output as successful artifact data.

**Step 4: Verify**

```bash
uv run pytest -q tests/test_sprite_blueprint_generation.py tests/test_sprite_visual_critique.py
```

## Task 4: Add user-visible quality mode

**Objective:** Let users opt into visual critique with explicit latency/cost feedback.

**Files:**
- Modify: `app/schemas/sprite.py`
- Modify: `app/routes/web.py`
- Modify: `app/templates/pages/sprite.html`
- Modify: `app/templates/partials/sprite_result.html`
- Test: `tests/test_api_and_web.py`

**Step 1: Write failing route/template tests**

Assert that the form exposes `standard` and `quality_review` modes, defaults to `standard`, shows visible progress during critique, and reports whether a critique/revision was used.

**Step 2: Implement thin route wiring**

Keep mode parsing in the route and orchestration in services. Do not expose raw critique prompts or responses to the page.

**Step 3: Verify**

```bash
uv run pytest -q tests/test_api_and_web.py
```

## Task 5: Build evaluation before enabling by default

**Objective:** Prove the critique improves user-preferred quality rather than only adding cost and latency.

**Files:**
- Create: `tests/fixtures/visual-review/`
- Create: `scripts/evaluate_visual_critique.py`
- Create: `docs/visual-critique-evaluation.md`

**Step 1: Curate a holdout set**

Store prompt/spec plus candidate pairs and human preference labels. Include wizard equipment, belts, books, wolf anatomy, different views, and non-humanoid props. Keep it separate from any later training set.

**Step 2: Define product metrics**

Measure:

- human pairwise preference agreement;
- top-1 winner selection rate among candidates;
- critique issue precision for each issue code;
- valid-render rate after revision;
- latency and provider cost per final artifact.

Do not use generic language-model academic benchmarks as a substitute for PixelForge visual quality.

**Step 3: Compare modes**

Run standard generation versus `quality_review` on the frozen holdout set. Enable the feature by default only if it improves the agreed human preference metric without unacceptable latency/cost.

## Task 6: Prepare preference data for a future local ranker

**Objective:** Collect reusable data without training a model yet.

**Files:**
- Create: `docs/preference-data-contract.md`
- Modify: artifact metadata schema/store only after agreeing retention policy

**Data record:**

```json
{
  "prompt_hash": "...",
  "asset_spec": {},
  "candidate_artifact_ids": ["...", "..."],
  "chosen_artifact_id": "...",
  "criteria": ["silhouette_clarity", "equipment_attachment"],
  "reviewer_notes": "optional bounded note",
  "created_at": "..."
}
```

Use pairwise human choices rather than an uncalibrated single scalar. Keep user-visible consent and retention policy explicit before collecting feedback at scale.

## Final verification

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Run a controlled real smoke test with one wizard and one wolf in `quality_review` mode, verify the metadata lineage, and compare the final PNGs manually against the baseline artifacts.
