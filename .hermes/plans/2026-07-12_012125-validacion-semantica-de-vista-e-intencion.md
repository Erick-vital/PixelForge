# Validación semántica de vista e intención de generación — Plan de implementación

> **Para Hermes:** usar `subagent-driven-development` para ejecutar este plan tarea por tarea, con revisión de cumplimiento y luego revisión de calidad. No crear commits sin autorización explícita de Erick.

**Goal:** impedir que un blueprint LLM válido estructuralmente se persista como éxito cuando contradice la vista, la pose o la intención explícita del usuario; permitir seleccionar desde el primer request si se desea una grammar controlada, LLM exploratorio o una plantilla concreta.

**Architecture:** separar tres decisiones que hoy se mezclan: (1) la intención declarada por el cliente, (2) el `AssetSpec` interpretado, y (3) el backend que compila el blueprint. Añadir una validación semántica compartida para blueprints procedurales y LLM; esta validación produce diagnósticos estructurados de vista/perfil, simetría y capas. Un fallo LLM consume el único repair existente; un fallo procedural es un error de código y no se reintenta.

**Tech Stack:** Python 3.12, Pydantic, Pillow, NumPy, FastAPI, HTMX, pytest, Ruff, uv.

---

## Investigación realizada

El artifact `sprite_20260712_070828_6f4cbc38` no adquirió `side-view` desde una variable hardcodeada en la ruta local. La ruta sin LLM calcula `game_view` en `app/services/sprite_interpretation.py:_detect_view()` y, si el prompt no contiene `side`, `plataforma` o `platform`, devuelve `icon/front`.

El artifact se creó por la ruta LLM. `ASSET_SPEC_SYSTEM_PROMPT` permite las tres vistas y exige que el LLM emita `game_view`, pero no ordena un default para peticiones sin vista. El modelo devolvió `side-view` por inferencia propia. Además, el mismo prompt de interpretación describe `character.pose.stance: front_neutral`, por lo que permitió la contradicción `game_view=side-view` + `stance=front_neutral`. `AssetSpec.resolve_side_pose_default()` sólo corrige a `side_neutral` si el LLM omitió completamente `pose`; no corrige una pose frontal declarada.

Por eso el pipeline seleccionó fallback LLM para un `warrior side-view` no cubierto por la ejecución que generó ese artifact y el blueprint LLM resultante fue geométricamente frontal. La calidad raster sólo verificó conectividad/ocupación; no evaluó coherencia con la vista. Los artifacts ya persistidos son inmutables y no deben cambiar con esta implementación.

## Decisiones de diseño

1. **El request debe poder declarar intención antes de interpretar el prompt.** Añadir controles opcionales al request inicial, no sólo a `/api/blueprint`:
   - `view: AllowedView | None` — una vista explícita prevalece sobre el LLM/local interpreter.
   - `generation_mode: GenerationMode = "auto"` — intención creativa (`controlled`, `exploratory`, `auto`).
   - `blueprint_strategy: BlueprintStrategy = "auto"` — backend solicitado para el flujo completo.
   - `template_id: str | None` — identificador de plantilla/grammar preconfigurada; inicialmente sólo valores de un registro pequeño y estable.

2. **No usar `template` como sinónimo ambiguo de cualquier recipe.** Un `template_id` es una intención de producto seleccionable (por ejemplo `warrior_front`, `warrior_side`, `pig_side`), no el `recipe` persistido ni coordenadas libres. El registro resuelve un template a constraints tipados de `AssetSpec` y a una grammar compatible.

3. **Cuando no hay vista explícita, aplicar una política estable y visible.** Para el incremento inicial: humanoid y prop usan `icon/front`; quadruped/pig puede conservar `side-view` sólo si el template lo fija. El LLM no elige la vista por defecto. Persistir `view_source: explicit | template | default | llm_inferred` para auditar la decisión. Como primera versión, `llm_inferred` debe quedar deshabilitado salvo que un flag posterior lo habilite deliberadamente.

4. **La semántica se valida contra señales geométricas deterministas, no mediante visión por IA.** Para side-view humanoid se exige asimetría horizontal suficiente, una única cadena dominante de cara/perfil hacia la dirección, y solapamiento/offset de extremidades. Para front-view se exige simetría dentro de tolerancia. Estas reglas se aplican a primitives y, cuando haga falta, a la máscara raster alpha. No intentar reconocer todos los objetos del mundo.

5. **Un rechazo no se persiste como artifact renderizado.** El artifact puede conservar status/error y diagnósticos seguros, pero no se guarda `blueprint.json` ni `render.png` como éxito hasta superar schema, semántica y calidad raster.

## Flujo objetivo

```text
POST /api/asset-spec
  request intent: view/template/generation_mode/strategy
  -> normalización de constraints explícitos
  -> intérprete LLM o local sólo para campos no fijados
  -> reconciliación: template > request explícito > default estable > interpretación
  -> AssetSpec + DecisionTrace
  -> persistir asset-spec y trace

POST /api/blueprint (o flujo UI integrado)
  -> resolver grammar/LLM según strategy + generation_mode + template
  -> blueprint candidato
  -> schema validation
  -> semantic intent validation (view/pose/template/family/archetype)
  -> render temporal
  -> raster quality validation
  -> LLM: un repair con diagnósticos seguros si falla schema/semantic/raster
  -> persistir blueprint/render sólo tras éxito
```

---

### Task 1: Introducir contratos de intención y trazabilidad de vista

**Objective:** hacer explícito qué pidió el cliente, qué se eligió y de dónde procede la vista final.

**Files:**
- Modify: `app/schemas/sprite.py`
- Modify: `app/services/sprite_interpretation.py`
- Test: `tests/test_sprite.py`
- Test: create `tests/test_sprite_intent.py`

**Step 1: Write failing tests**

```python
def test_explicit_request_view_overrides_llm_view() -> None:
    request = AssetSpecRequest(prompt="draw a warrior", view="icon/front")
    spec, trace = await create_asset_spec_from_request_with_trace(request, fake_llm_returning_side_view)
    assert spec.game_view == "icon/front"
    assert trace.view_source == "explicit"


def test_unspecified_humanoid_view_uses_stable_front_default() -> None:
    spec, trace = await create_asset_spec_from_request_with_trace(
        AssetSpecRequest(prompt="draw a warrior"), fake_llm_returning_side_view
    )
    assert spec.game_view == "icon/front"
    assert trace.view_source == "default"
```

Also cover template precedence, invalid `template_id`, and a side template setting `side-view` + `side_neutral`.

**Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_sprite_intent.py -q
```

Expected: FAIL because request fields and trace model do not exist.

**Step 3: Add minimal contracts**

In `app/schemas/sprite.py`, add:

```python
ViewSource = Literal["explicit", "template", "default", "llm_inferred"]

class AssetSpecRequest(BaseModel):
    prompt: ...
    use_llm: bool = True
    view: AllowedView | None = None
    generation_mode: GenerationMode = "auto"
    blueprint_strategy: BlueprintStrategy = "auto"
    template_id: str | None = None
    ...

class AssetSpecDecisionTrace(BaseModel):
    view_source: ViewSource
    template_id: str | None = None
    requested_view: AllowedView | None = None
```

Use a return DTO/internal result from interpretation rather than changing existing `AssetSpec` return values indiscriminately.

**Step 4: Verify GREEN**

Run the focused test command. Expected: PASS.

---

### Task 2: Add a typed template registry that resolves constraints, not geometry

**Objective:** support user-selectable templates without treating template identifiers as raw recipes or free coordinates.

**Files:**
- Create: `app/sprite_engine/grammar/templates.py`
- Modify: `app/sprite_engine/grammar/__init__.py`
- Modify: `app/services/sprite_interpretation.py`
- Test: `tests/test_sprite_intent.py`

**Step 1: Write failing tests**

```python
def test_warrior_side_template_sets_required_constraints() -> None:
    result = resolve_template("warrior_side")
    assert result.constraints == {
        "family": "humanoid",
        "archetype": "warrior",
        "game_view": "side-view",
        "character.pose.stance": "side_neutral",
    }


def test_unknown_template_is_a_controlled_request_error() -> None:
    with pytest.raises(TemplateResolutionError, match="unknown template"):
        resolve_template("warrior_3d")
```

**Step 2: Verify RED**

```bash
uv run pytest tests/test_sprite_intent.py -q
```

Expected: FAIL because no template registry exists.

**Step 3: Implement minimal registry**

Use a frozen `SpriteTemplate` dataclass containing `template_id`, `family`, `archetype`, `view`, `generation_mode` defaults, and an optional bounded `CharacterSpec` patch. Initial values only:

```text
warrior_front -> humanoid/warrior/icon-front/front_neutral
warrior_side  -> humanoid/warrior/side-view/side_neutral
wizard_front  -> humanoid/wizard/icon-front/front_neutral
pig_side      -> quadruped/pig/side-view
```

Apply template constraints after interpretation and before `AssetSpec` validation/reconciliation. Do not put geometry, primitive lists, or renderer logic in this registry.

**Step 4: Verify GREEN**

```bash
uv run pytest tests/test_sprite_intent.py -q
```

---

### Task 3: Reconcile view and pose before grammar selection

**Objective:** prevent contradictory `side-view + front_neutral` specs from reaching the blueprint stage.

**Files:**
- Modify: `app/schemas/sprite.py`
- Modify: `app/services/sprite_interpretation.py`
- Test: `tests/test_sprite_intent.py`
- Test: `tests/test_visual_grammars.py`

**Step 1: Write failing tests**

```python
@pytest.mark.parametrize(
    ("view", "stance"),
    [("side-view", "front_neutral"), ("icon/front", "side_neutral")],
)
def test_incompatible_explicit_view_and_pose_is_rejected(view: str, stance: str) -> None:
    with pytest.raises(ValidationError, match="pose contradicts game_view"):
        AssetSpec(game_view=view, character={"pose": {"stance": stance}})
```

Add a separate test that a view supplied only by a template/default normalizes the omitted pose to its compatible value.

**Step 2: Verify RED**

```bash
uv run pytest tests/test_sprite_intent.py tests/test_visual_grammars.py -q
```

**Step 3: Implement validation**

Replace the current narrow `resolve_side_pose_default()` behavior with a reconciliation validator that:

- assigns `front_neutral` for defaulted `icon/front` humanoids;
- assigns `side_neutral` for defaulted/template `side-view` humanoids;
- rejects an explicitly supplied incompatible pair;
- does not mutate a spec silently when both fields were explicit.

The reconciliation layer must know field provenance from the request/template/LLM result; do not infer explicitness solely from Pydantic defaults.

**Step 4: Verify GREEN**

Run the focused command. Expected: PASS.

---

### Task 4: Define structured semantic diagnostics for LLM and procedural blueprints

**Objective:** make semantic failures inspectable, repairable, and safe to persist in error metadata.

**Files:**
- Modify: `app/sprite_engine/quality/semantic.py`
- Test: create `tests/test_semantic_view_quality.py`

**Step 1: Write failing tests**

```python
def test_side_view_rejects_front_symmetric_humanoid_blueprint() -> None:
    result = evaluate_semantic_quality(side_warrior_spec, front_symmetric_blueprint)
    assert result.passed is False
    assert "side_view_symmetry_too_high" in result.issue_codes


def test_side_view_accepts_profile_with_directional_face_and_limb_offset() -> None:
    result = evaluate_semantic_quality(side_warrior_spec, valid_side_profile_blueprint)
    assert result.passed is True


def test_front_view_rejects_strongly_asymmetric_profile_blueprint() -> None:
    result = evaluate_semantic_quality(front_warrior_spec, valid_side_profile_blueprint)
    assert "front_view_symmetry_too_low" in result.issue_codes
```

Use a handcrafted approximation of the problematic artifact blueprint as the first failing fixture; do not mutate its stored artifact files.

**Step 2: Verify RED**

```bash
uv run pytest tests/test_semantic_view_quality.py -q
```

**Step 3: Implement a report-oriented API**

Replace direct-only checks with a report:

```python
@dataclass(frozen=True)
class SemanticQualityReport:
    passed: bool
    issue_codes: tuple[str, ...]
    metrics: dict[str, float | int | str]


def evaluate_semantic_quality(
    spec: AssetSpec,
    blueprint: SpriteBlueprint,
    *,
    grammar_name: str | None,
) -> SemanticQualityReport: ...


def require_semantic_quality(...):
    report = evaluate_semantic_quality(...)
    if not report.passed:
        raise SemanticQualityError(report)
```

Initial deterministic checks:

- `view_pose_conflict` — should normally be blocked before this phase.
- `side_view_symmetry_too_high` — compare alpha-mask overlap with its horizontal mirror in the object bounding box; a near-perfect mirror is invalid for a side humanoid.
- `side_view_missing_directional_feature` — require a directionally biased head/front-equipment primitive or a declared profile feature in a bounded semantic contract.
- `side_view_missing_limb_depth` — require front/back limb geometry or a measurable x-offset/overlap between limbs for humanoids.
- `front_view_symmetry_too_low` — apply only to grammars/templates declaring symmetric front presentation.
- Existing family/view/layer/material/archetype checks.

Keep thresholds constants in `semantic.py`, document why each exists, and test the threshold boundaries. Do not introduce computer vision models.

**Step 4: Verify GREEN**

```bash
uv run pytest tests/test_semantic_view_quality.py tests/test_visual_grammars.py -q
```

---

### Task 5: Run the semantic gate for every blueprint origin before persistence

**Objective:** ensure LLM blueprints receive the same intent validation as procedural blueprints.

**Files:**
- Modify: `app/services/sprite_blueprint.py`
- Modify: `app/services/sprite.py`
- Modify: `app/services/sprite_artifact_store.py`
- Test: `tests/test_sprite_blueprint_generation.py`
- Test: create `tests/test_sprite_semantic_repair.py`

**Step 1: Write failing tests**

```python
async def test_llm_front_like_candidate_for_side_spec_triggers_one_semantic_repair() -> None:
    llm = FakeLlm([front_symmetric_json, valid_side_profile_json])
    generated = await generate_sprite_blueprint(side_warrior_spec, llm_service=llm)
    assert len(llm.calls) == 2
    assert generated.blueprint.recipe == "llm_blueprint"


async def test_llm_semantic_repair_failure_returns_controlled_error_and_no_success_artifact() -> None:
    llm = FakeLlm([front_symmetric_json, front_symmetric_json])
    with pytest.raises(BlueprintGenerationError, match="side_view_symmetry_too_high"):
        await service.create_sprite_blueprint(...)
    assert artifact.status == "blueprint_failed"
    assert not artifact.blueprint_json_path.exists()
    assert not artifact.render_png_path.exists()
```

**Step 2: Verify RED**

```bash
uv run pytest tests/test_sprite_semantic_repair.py tests/test_sprite_blueprint_generation.py -q
```

**Step 3: Implement one shared validation pipeline**

Refactor `_parse_and_validate_sprite_blueprint()` into a candidate validation function that returns the semantic report after:

```text
JSON parse -> Pydantic -> primitive/schema validation -> semantic validation -> temporary render -> raster quality
```

For LLM output, pass only safe structured semantic diagnostics to `_blueprint_repair_prompt()`:

```json
{
  "semantic_issue_codes": ["side_view_symmetry_too_high"],
  "metrics": {"mirror_overlap": 0.94},
  "required_view": "side-view",
  "direction": "right"
}
```

Do not include raw prompts, secrets, headers, or unrelated artifact data. Retain the existing hard maximum of one repair call across parse, schema, semantic, and raster errors combined.

For procedural grammar output, execute the same gate but do not invoke a repair. Raise a controlled `BlueprintGenerationError` with the report, because this is a deterministic compiler regression.

Persist safe `semantic_quality` diagnostics in metadata on success and `generation_error` diagnostics on failure. Keep existing historical metadata parseable by using optional/default fields.

**Step 4: Verify GREEN**

Run the focused tests. Expected: PASS.

---

### Task 6: Make initial request policy available in API and HTMX without breaking existing clients

**Objective:** expose view/template/mode/strategy in the first request and show the resolved decision visibly.

**Files:**
- Modify: `app/routes/api.py`
- Modify: `app/routes/web.py`
- Modify: `app/templates/pages/sprite.html`
- Modify: `app/templates/partials/sprite_result.html`
- Test: `tests/test_api_and_web.py`

**Step 1: Write failing API and UI tests**

```python
def test_asset_spec_accepts_explicit_warrior_side_template() -> None:
    response = client.post("/api/asset-spec", json={
        "prompt": "draw a warrior",
        "view": "side-view",
        "template_id": "warrior_side",
        "generation_mode": "controlled",
        "blueprint_strategy": "auto",
        "use_llm": False,
    })
    assert response.json()["asset_spec"]["game_view"] == "side-view"
    assert response.json()["decision_trace"]["view_source"] == "template"


def test_ui_shows_requested_and_resolved_generation_decisions() -> None:
    response = client.post("/ui/sprite/spec", data={...})
    assert "View source: template" in response.text
    assert "Resolved strategy: procedural" in response.text
    assert "Grammar: humanoid_side" in response.text
```

**Step 2: Verify RED**

```bash
uv run pytest tests/test_api_and_web.py -q
```

**Step 3: Implement request plumbing**

- Extend API response schemas to return `decision_trace` without removing current fields.
- Accept optional HTMX form controls: view selector (`auto/default`, front, side, top-down), generation mode, and template selector.
- Preserve visible `hx-on::before-request` progress and explicit success/error fragments.
- In result UI, display: requested view, resolved view, source, template, requested/resolved strategy, grammar/LLM, and semantic-quality report summary.
- Do not force a user to select a template; `auto/default` remains the default.

**Step 4: Verify GREEN**

```bash
uv run pytest tests/test_api_and_web.py -q
```

---

### Task 7: Add regression fixtures, documentation, and full verification

**Objective:** prevent recurrence of the `sprite_20260712_070828_6f4cbc38` class of failure and document exact behavior.

**Files:**
- Create: `tests/fixtures/semantic_quality/warrior_side_front_like_llm.json`
- Create: `tests/fixtures/semantic_quality/warrior_side_valid_profile.json`
- Modify: `docs/architecture.md`
- Modify: `README.md`
- Test: `tests/test_semantic_view_quality.py`
- Test: `tests/test_sprite_semantic_repair.py`

**Step 1: Write failing regression test**

Use a sanitized/hand-authored derivative of the artifact blueprint, not the persisted artifact itself:

```python
def test_regression_side_warrior_front_like_llm_blueprint_is_rejected() -> None:
    blueprint = load_fixture("warrior_side_front_like_llm.json")
    report = evaluate_semantic_quality(side_warrior_spec, blueprint, grammar_name=None)
    assert report.issue_codes == ("side_view_symmetry_too_high", "side_view_missing_directional_feature")
```

**Step 2: Verify RED**

```bash
uv run pytest tests/test_semantic_view_quality.py::test_regression_side_warrior_front_like_llm_blueprint_is_rejected -q
```

**Step 3: Document actual policy**

Update architecture docs with:

- precedence: template > explicit request view > deterministic default > optional inferred value;
- difference between template, grammar, recipe, and blueprint strategy;
- semantic validation stages and issue codes;
- one-repair policy;
- historical artifact immutability and deliberate regeneration workflow;
- initial capability/template table.

**Step 4: Verify GREEN and run full gates**

```bash
uv run ruff format .
uv run ruff check .
uv run pytest -q
git diff --check
uv run python scripts/render_grammar_contact_sheet.py
```

Expected: all tests pass, no Ruff/diff errors, and contact sheet remains a valid RGBA PNG.

Run runtime smoke:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8014
curl --fail http://127.0.0.1:8014/api/settings
```

Stop the temporary server intentionally after HTTP 200.

## Acceptance criteria

- A prompt without a view no longer lets the LLM silently choose `side-view`; a stable policy resolves the view and records its source.
- Explicit request view and typed template constraints are visible in the first API request, artifact metadata, and UI result.
- An explicit `side-view` + explicit `front_neutral` conflict returns a controlled validation error before blueprint generation.
- A structurally valid but front-symmetric LLM blueprint for a side-view humanoid fails semantic validation, receives only one repair attempt, and is not persisted as a rendered success if repair fails.
- A valid profile blueprint with appropriate directional features and limb-depth geometry succeeds.
- The same semantic gate runs for grammar and LLM blueprints; only LLM may use the one repair call.
- Existing clients that send only `prompt` and `use_llm` remain valid and receive a deterministic default view.
- Historic artifacts remain unchanged and renderable; remediation is an explicit regenerate/new-artifact action.

## Flow improvements

1. **Interpretation:** converts an implicit, model-chosen view into a user- or policy-owned decision.
2. **Spec integrity:** catches view/pose contradictions before grammar selection.
3. **Routing:** prevents accidental fallback caused by an arbitrary inferred view and lets `controlled` requests fail early and explain why.
4. **LLM blueprint generation:** upgrades validation from “valid JSON and valid pixels” to “the geometry satisfies the requested presentation.”
5. **Repair:** gives the model concise issue codes/metrics instead of an opaque “invalid blueprint” response.
6. **Persistence:** prevents misleading `rendered` artifacts and records safe semantic evidence for successful/failed attempts.
7. **UI/API:** lets the caller select a template or view up front and see exactly why grammar versus LLM was used.
8. **Operations/debugging:** makes artifact diagnosis reproducible through view provenance, template ID, strategy lineage, and semantic report.

## Risks and mitigations

- **False rejection of stylized side sprites:** start with conservative thresholds and fixture-driven boundary tests; report metrics to tune thresholds.
- **Overfitting to humanoids:** scope the initial profile rules to `humanoid` and declare unsupported semantic checks as skipped for props/dragons; add quadruped rules in a separate increment.
- **Template proliferation:** keep the registry small, declarative, and capability-backed; do not add a class per cosmetic combination.
- **API complexity:** all new request controls are optional and retain current defaults.
- **Unexpected inference regressions:** persist `view_source` and test no-view requests through both local and fake LLM interpretation.
