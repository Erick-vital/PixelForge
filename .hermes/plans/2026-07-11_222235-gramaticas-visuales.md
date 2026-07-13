# Gramáticas visuales de PixelForge — Plan de implementación

> **Para Hermes:** usar `subagent-driven-development` para ejecutar este plan tarea por tarea, con revisión de cumplimiento y luego revisión de calidad. No crear commits sin autorización explícita de Erick.

**Objetivo:** sustituir la selección superficial por keywords y las recipes rígidas por un sistema tipado de familias, arquetipos, vistas, capacidades y gramáticas visuales que compile `AssetSpec` a `SpriteBlueprint` reproducibles, manteniendo el LLM como fallback controlado.

**Arquitectura:** `AssetSpec` declarará `family`, `archetype` y la vista solicitada. Un registro de gramáticas seleccionará un compilador sólo cuando sus capacidades cubran el spec completo. Cada gramática resolverá `spec -> skeleton/anchors -> partes semánticas -> layers/material roles -> SpriteBlueprint`; el renderer seguirá siendo genérico y compartido con `llm_blueprint`.

**Stack:** Python 3.12, Pydantic, Pillow, NumPy, FastAPI/HTMX, pytest, Ruff, uv.

---

## Contexto y decisiones

### Estado actual

- `known_procedural_recipe()` en `app/services/procedural_sprite.py` clasifica por substrings (`human`, `person`, `dragon`, etc.).
- `app/services/sprite_blueprint.py` resuelve `auto -> procedural | llm_blueprint` y bloquea humanoides `side-view` porque sólo existe skeleton frontal.
- `CharacterSpec` ya contiene anatomía, pose, cara, cabello, ropa, equipo, materiales e iluminación, pero la recipe sólo compila una parte de esos campos.
- `compile_humanoid_character()` ya emite primitives con layers y material roles; `compose_blueprint_layers()` ya compone RGBA por capa.
- El árbol de trabajo está modificado. Antes de ejecutar este plan hay que estabilizar y confirmar la línea base sin mezclar cambios accidentalmente.

### Decisiones

1. **No crear una recipe por subject.** Crear familias (`humanoid`, `quadruped`, `prop`, `dragon`) y arquetipos (`warrior`, `wizard`, `pig`, etc.).
2. **No permitir coordenadas libres en specs.** Los specs contienen enums/valores acotados; los compiladores resuelven geometría.
3. **No convertir automáticamente frontal a lateral.** `HumanoidFrontGrammar` y `HumanoidSideGrammar` tendrán skeletons y capacidades diferentes.
4. **No reemplazar el renderer.** Las gramáticas producen `SpriteBlueprint`; el compositor actual continúa como backend genérico.
5. **Fallback explícito.** Si ninguna gramática cubre el spec completo, `auto` usa `llm_blueprint`; nunca degrada a `generic_prop` silenciosamente.
6. **Compatibilidad de artefactos.** Campos nuevos en `AssetSpec` y metadata comienzan opcionales/default; blueprints históricos siguen siendo renderizables.
7. **Implementación incremental.** Primero clasificación y registro; después enriquecer humanoide frontal; luego lateral; finalmente cuadrúpedos.
8. **La grammar no elimina la creatividad.** El sistema debe separar intención de generación mediante `generation_mode`: `controlled` prioriza una grammar compatible; `exploratory` prioriza un blueprint LLM; `auto` decide según la cobertura de la grammar y la novedad solicitada. La grammar compila estructura segura, pero recibe variantes, slots, paleta, materiales y seed para evitar una plantilla única.

### Modos de generación

```text
controlled
  grammar compatible obligatoria; si no existe, error controlado

exploratory
  LLM blueprint preferido, incluso si existe una grammar

auto
  grammar para familias/arquetipos soportados y pedidos estructurados;
  LLM para novelty explícita, diseño libre o capabilities faltantes
```

`generation_mode` debe ser un campo opcional con default compatible y no debe confundirse con `blueprint_strategy`: el primero expresa intención creativa; el segundo controla qué backend de blueprint se ejecuta.

### No objetivos iniciales

- Animación, rigging temporal o sprite sheets.
- Perspectiva libre o rotación arbitraria.
- Gramática universal para todos los subjects.
- MAP-Elites, candidate search o ranking visual avanzado.
- Migración retroactiva automática de artefactos existentes.

---

## Arquitectura objetivo

```text
Prompt
  -> LLM / intérprete de intención
  -> AssetSpec estructurado
       generation_mode
       family
       archetype
       game_view
       CharacterSpec / QuadrupedSpec
  -> GrammarRegistry.resolve(spec)
       family + view + capabilities
  -> grammar compiler
       semantic spec
       -> skeleton / anchors
       -> semantic parts
       -> ordered layers + material roles
       -> SpriteBlueprint
  -> compose_blueprint_layers()
  -> outline + palette limiting
  -> quality gates
  -> persisted artifact

Si no existe grammar compatible:
AssetSpec -> LLM Blueprint -> validation -> mismo renderer
```

Estructura prevista, creada sólo a medida que cada módulo tenga comportamiento real:

```text
app/sprite_engine/
  grammar/
    models.py
    registry.py
    classification.py
    humanoid_front.py
    humanoid_side.py
    quadruped_side.py
  character/
    spec.py
    skeleton.py
    side_skeleton.py
    quadruped_spec.py
    quadruped_skeleton.py
```

---

## Fase 0 — Estabilizar la línea base

### Tarea 1: Congelar el comportamiento actual

**Objetivo:** asegurar que las layers/material shading actualmente sin commit forman una base verde antes de introducir gramáticas.

**Archivos:**
- Revisar: `app/schemas/sprite.py`
- Revisar: `app/services/procedural_sprite.py`
- Revisar: `app/sprite_engine/recipes/humanoid.py`
- Revisar: `app/sprite_engine/rendering/rasterizer.py`
- Revisar: `tests/test_layered_compositor.py`

**Pasos:**

1. Ejecutar:
   ```bash
   git status --short
   git diff --check
   uv run ruff format --check .
   uv run ruff check .
   uv run pytest -q
   ```
2. Esperar suite verde y ningún whitespace error.
3. Generar un humanoide frontal de smoke y conservar temporalmente el PNG para comparación visual.
4. No continuar si falla alguna puerta; corregir primero la base.
5. No crear commit automáticamente. Si Erick lo desea, separar este trabajo previo de las gramáticas en un commit independiente.

---

## Fase 1 — Semántica de familia y arquetipo

### Tarea 2: Añadir clasificación explícita al AssetSpec

**Objetivo:** desacoplar `subject` de la familia geométrica.

**Archivos:**
- Modificar: `app/schemas/sprite.py`
- Modificar: `app/services/sprite_interpretation.py`
- Test: `tests/test_sprite.py`
- Test: `tests/test_sprite_blueprint_generation.py`

**Contrato propuesto:**

```python
AssetFamily = Literal["humanoid", "quadruped", "dragon", "prop", "unknown"]
AssetArchetype = Literal[
    "generic",
    "warrior",
    "wizard",
    "blacksmith",
    "pig",
    "wolf",
    "dragon",
    "potion",
    "sword",
]

class AssetSpec(BaseModel):
    family: AssetFamily = "unknown"
    archetype: str = "generic"
```

`archetype` debe mantenerse como string normalizado inicialmente para no necesitar una migración cada vez que aparezca un arquetipo nuevo. La gramática valida cuáles soporta.

**Ciclo TDD:**

1. Añadir tests rojos:
   ```python
   def test_warrior_is_classified_as_humanoid(): ...
   def test_wizard_is_classified_as_humanoid(): ...
   def test_pig_is_classified_as_quadruped(): ...
   def test_legacy_asset_spec_defaults_to_unknown_family(): ...
   ```
2. Ejecutar:
   ```bash
   uv run pytest tests/test_sprite.py tests/test_sprite_blueprint_generation.py -q
   ```
   Esperado: FAIL por campos/comportamiento inexistente.
3. Implementar campos Pydantic y clasificación en interpretación.
4. Volver a ejecutar; esperado: PASS.
5. Verificar que un JSON histórico sin `family` sigue validando.

### Tarea 3: Crear un clasificador de dominio separado

**Objetivo:** sacar la clasificación semántica de `procedural_sprite.py` y evitar que el registry dependa de substrings dispersos.

**Archivos:**
- Crear: `app/sprite_engine/grammar/classification.py`
- Crear: `app/sprite_engine/grammar/__init__.py`
- Modificar: `app/services/sprite_interpretation.py`
- Test: `tests/test_sprite_classification.py`

**API propuesta:**

```python
@dataclass(frozen=True)
class AssetClassification:
    family: str
    archetype: str


def classify_subject(subject: str) -> AssetClassification:
    ...
```

La primera versión puede tener un vocabulario pequeño y centralizado para normalización local, pero el resultado queda persistido en `AssetSpec`; no debe volver a inferirse en cada etapa.

**Tests mínimos:**

```text
warrior, knight, wizard, blacksmith -> humanoid
human, person, chibi                -> humanoid/generic
pig, boar, wolf, dog                -> quadruped
dragon                              -> dragon
potion, sword                       -> prop
unknown subject                     -> unknown
```

**Verificación:**

```bash
uv run pytest tests/test_sprite_classification.py -q
```

### Tarea 3A: Implementar el camino híbrido LLM → spec → grammar

**Objetivo:** conservar la creatividad conceptual del LLM sin permitirle escribir coordenadas cuando una grammar compatible puede compilar el pedido.

**Archivos:**
- Modificar: `app/schemas/sprite.py`
- Modificar: `app/services/sprite_interpretation.py`
- Modificar: `app/services/sprite_blueprint.py`
- Modificar: `app/schemas/__init__.py` si exporta contratos públicos
- Test: `tests/test_sprite.py`
- Test: `tests/test_sprite_blueprint_generation.py`
- Test: `tests/test_api_and_web.py`

**Contrato propuesto:**

```python
GenerationMode = Literal["auto", "controlled", "exploratory"]

class AssetSpec(BaseModel):
    generation_mode: GenerationMode = "auto"
```

El intérprete LLM puede proponer semántica acotada como:

```json
{
  "generation_mode": "auto",
  "family": "humanoid",
  "archetype": "warrior",
  "character": {
    "anatomy": {"build": "broad"},
    "clothing": {"upper": "armor"},
    "equipment": {"hand": "blacksmith_hammer"},
    "materials": {"upper": "metal"}
  }
}
```

No puede producir anchors, coordenadas, skeletons ni primitives en esta etapa. La grammar recibe el `AssetSpec` validado y resuelve la geometría.

**Precedencia con `BlueprintStrategy`:**

```text
strategy=procedural
  -> exige grammar compatible; si no existe, error controlado

strategy=llm_blueprint
  -> genera blueprint con LLM, sin consultar generation_mode

strategy=auto + generation_mode=controlled
  -> exige grammar compatible; si no existe, error controlado

strategy=auto + generation_mode=exploratory
  -> usa LLM blueprint aunque exista grammar

strategy=auto + generation_mode=auto
  -> grammar compatible si existe; LLM fallback si no existe
```

La primera implementación no debe intentar detectar “novedad artística” mediante heurísticas ambiguas. `exploratory` es una intención explícita del usuario o del request; `auto` se decide únicamente por capabilities reproducibles.

**Ciclo TDD:**

1. Añadir tests rojos para los cinco casos de precedencia.
2. Añadir un test que capture el `AssetSpec` recibido por una grammar fake y compruebe que conserva build, armor, equipment, material, palette y seed propuestos por el intérprete.
3. Añadir un test que verifique que la salida de interpretación no acepta `primitives`, `points`, `bbox` ni anchors libres.
4. Ejecutar:
   ```bash
   uv run pytest tests/test_sprite.py tests/test_sprite_blueprint_generation.py tests/test_api_and_web.py -q
   ```
   Esperado: FAIL antes de implementar el contrato y routing.
5. Implementar el campo, validación y precedencia mínima.
6. Repetir el comando; esperado: PASS.

**Criterio de aceptación:**

```text
Prompt
→ interpretación LLM semántica
→ AssetSpec validado
→ CharacterSpec tipado
→ grammar compatible
→ SpriteBlueprint reproducible
```

El LLM conserva libertad para proponer composición semántica; la grammar conserva control geométrico. `exploratory` mantiene disponible la generación directa de blueprint LLM.

---

## Fase 2 — Capacidades y registro de gramáticas

### Tarea 4: Definir el contrato de una gramática visual

**Objetivo:** modelar compiladores por familia sin acoplarlos al servicio web.

**Archivos:**
- Crear: `app/sprite_engine/grammar/models.py`
- Test: `tests/test_grammar_registry.py`

**Modelos propuestos:**

```python
@dataclass(frozen=True)
class GrammarCapabilities:
    family: str
    views: frozenset[str]
    archetypes: frozenset[str]
    poses: frozenset[str]


class VisualGrammar(Protocol):
    name: str
    capabilities: GrammarCapabilities

    def supports(self, asset_spec: AssetSpec) -> bool: ...
    def compile(self, asset_spec: AssetSpec, *, seed: int) -> SpriteBlueprint: ...
```

**Reglas:**

- `supports()` debe evaluar spec completo, no sólo subject.
- `compile()` no puede llamar a LLM.
- El renderer no puede importar gramáticas.
- Un spec no soportado debe producir una decisión `unsupported`, no una imagen falsa.

### Tarea 5: Implementar GrammarRegistry

**Objetivo:** elegir una gramática por capabilities y devolver trazabilidad de la decisión.

**Archivos:**
- Crear: `app/sprite_engine/grammar/registry.py`
- Modificar: `app/sprite_engine/grammar/__init__.py`
- Test: `tests/test_grammar_registry.py`

**API propuesta:**

```python
@dataclass(frozen=True)
class GrammarResolution:
    grammar_name: str | None
    supported: bool
    reason: str


class GrammarRegistry:
    def resolve(self, asset_spec: AssetSpec) -> GrammarResolution: ...
    def compile(self, asset_spec: AssetSpec, *, seed: int) -> SpriteBlueprint: ...
```

**Tests rojos esenciales:**

```text
humanoid + icon/front -> humanoid_front
humanoid + side-view  -> unsupported hasta Fase 5
quadruped + side-view -> unsupported hasta Fase 6
unknown               -> unsupported
```

**Verificación:**

```bash
uv run pytest tests/test_grammar_registry.py -q
```

### Tarea 6: Conectar `auto` al registry

**Objetivo:** reemplazar `known_procedural_recipe(subject)` como decisión primaria.

**Archivos:**
- Modificar: `app/services/sprite_blueprint.py`
- Modificar: `app/services/procedural_sprite.py`
- Test: `tests/test_sprite_blueprint_generation.py`

**Comportamiento objetivo:**

```text
auto + grammar compatible     -> procedural grammar
auto + grammar no compatible  -> llm_blueprint
procedural + no compatible    -> error controlado, no generic_prop
llm_blueprint                 -> LLM explícito
```

**Tests:**

- `warrior` clasificado humanoide frontal selecciona procedural aunque no contenga `person`.
- `wizard` frontal selecciona procedural.
- `warrior person` lateral sigue yendo a LLM mientras no exista grammar lateral.
- `pig` lateral va a LLM mientras no exista grammar cuadrúpeda.
- `strategy=procedural` con familia desconocida produce `BlueprintGenerationError`.

**Verificación:**

```bash
uv run pytest tests/test_sprite_blueprint_generation.py -q
```

---

## Fase 3 — HumanoidFrontGrammar real

### Tarea 7: Convertir la recipe humanoide actual en gramática frontal

**Objetivo:** reutilizar `HumanoidSkeleton` sin duplicar geometría.

**Archivos:**
- Crear: `app/sprite_engine/grammar/humanoid_front.py`
- Modificar: `app/sprite_engine/recipes/humanoid.py`
- Modificar: `app/sprite_engine/grammar/registry.py`
- Test: `tests/test_humanoid_front_grammar.py`

**Enfoque:**

- `HumanoidFrontGrammar` adapta `AssetSpec` a `HumanoidTraits`.
- Reutiliza `build_humanoid_skeleton()`.
- Reutiliza o absorbe `compile_humanoid_character()`.
- Declara capabilities frontales y arquetipos iniciales: `generic`, `blacksmith`, `warrior`, `wizard`.
- No implementar aún vista lateral.

**Acceptance tests:**

```text
same spec + seed -> blueprint idéntico
warrior frontal  -> recipe humanoid_front/warrior
wizard frontal   -> recipe humanoid_front/wizard
all anchors       -> canvas bounds y ground line válidos
```

### Tarea 8: Implementar slots frontales por arquetipo

**Objetivo:** hacer que `CharacterSpec` cambie geometría y silueta, no sólo metadata.

**Archivos:**
- Modificar: `app/sprite_engine/character/spec.py`
- Modificar: `app/sprite_engine/grammar/humanoid_front.py`
- Posible crear sólo si reduce complejidad real: `app/sprite_engine/grammar/humanoid_parts.py`
- Test: `tests/test_humanoid_front_grammar.py`

**Slots iniciales:**

```text
headwear: none | helmet | wizard_hat
upper: tunic | leather_apron | armor | robe
lower: trousers | work_pants | armored_legs | robe_lower
footwear: boots | heavy_boots
main_hand: none | hammer | sword | staff
off_hand: none | shield | book
```

**Reglas mínimas:**

- `helmet` se ancla a cabeza y deja visor/ojos legibles.
- `wizard_hat` extiende `head_top_y` sin salir del canvas.
- `armor` ensancha hombros y declara metal.
- `robe` cambia la silueta inferior y puede ocluir piernas.
- `heavy_boots` incrementa volumen manteniendo `ground_y`.
- equipo se divide entre `back_equipment` y `front_equipment`.

**Tests estructurales:**

```text
warrior y wizard tienen bboxes/siluetas distintas
armor produce material metal
robe altera lower silhouette
heavy boots permanecen en ground line
shield queda detrás del brazo; sword delante
```

### Tarea 9: Hacer efectivos materiales e iluminación del CharacterSpec

**Objetivo:** evitar campos declarativos sin efecto.

**Archivos:**
- Modificar: `app/schemas/sprite.py`
- Modificar: `app/sprite_engine/grammar/humanoid_front.py`
- Modificar: `app/sprite_engine/rendering/rasterizer.py`
- Test: `tests/test_layered_compositor.py`
- Test: `tests/test_humanoid_front_grammar.py`

**Comportamiento:**

- `materials.upper` determina cloth/leather/metal para la pieza superior.
- `materials.equipment` se deriva por pieza cuando exista mango+cabeza.
- `lighting.direction=top_left|top_right` cambia máscaras de borde.
- `SpriteBlueprint` persiste la dirección de iluminación o un contrato de render equivalente, con default compatible.

**Tests:**

```text
top_left y top_right desplazan highlights en direcciones opuestas
metal tiene mayor rango de contraste que cloth
material_roles sólo referencia fills existentes
```

---

## Fase 4 — Validación semántica y benchmark frontal

### Tarea 10: Añadir validación de gramática

**Objetivo:** detectar blueprints proceduralmente válidos pero contradictorios con el spec.

**Archivos:**
- Crear: `app/sprite_engine/quality/semantic.py`
- Modificar: `app/services/sprite_blueprint.py`
- Test: `tests/test_semantic_quality.py`

**Checks iniciales:**

```text
family coincide con grammar
view coincide con capabilities
archetype requerido produce sus partes distintivas
layers obligatorias no están vacías
material roles válidos
front humanoid conserva simetría cuando aplica
```

No intentar todavía visión por IA. Usar verificaciones estructurales reproducibles.

### Tarea 11: Crear fixtures y contact sheet reproducible

**Objetivo:** comparar visualmente cambios sin depender de recuerdos de artifacts aislados.

**Archivos:**
- Crear: `tests/fixtures/grammar_specs/warrior_front.json`
- Crear: `tests/fixtures/grammar_specs/wizard_front.json`
- Crear: `tests/fixtures/grammar_specs/blacksmith_front.json`
- Crear: `scripts/render_grammar_contact_sheet.py`
- Test: `tests/test_grammar_benchmarks.py`

**Salida esperada:**

```text
/tmp/pixelforge-grammar-front-contact-sheet.png
```

El script no debe escribir artifacts de producto; sólo fixtures reproducibles y salida temporal.

**Verificación manual:**

- Guerrero, mago y herrero tienen siluetas distinguibles a 1×.
- Ninguna parte sale del canvas.
- Equipo y ropa respetan oclusión.
- Paletas y materiales son legibles.

---

## Fase 5 — HumanoidSideGrammar

### Tarea 12: Definir un skeleton lateral independiente

**Objetivo:** representar perfil lateral real sin deformar el skeleton frontal.

**Archivos:**
- Crear: `app/sprite_engine/character/side_skeleton.py`
- Test: `tests/test_humanoid_side_skeleton.py`

**Anchors mínimos:**

```text
body_axis_x
face_direction: left | right
head_center
nose_anchor
shoulder_front/back
hand_front/back
hip
knee_front/back
foot_front/back
ground_y
back_equipment_anchor
```

**Invariantes:**

- Perfil cabe dentro de 64×64.
- Un pie o ambos apoyan en `ground_y` según pose.
- Cabeza comunica dirección mediante nariz/frente.
- Brazo/pierna traseros pueden ocluirse parcialmente.
- `mirror_direction()` produce left/right sin cambiar anatomía.

### Tarea 13: Compilar humanoides laterales

**Objetivo:** cubrir los casos de `generic person side-view` y `warrior person side-view` que hoy van a LLM.

**Archivos:**
- Crear: `app/sprite_engine/grammar/humanoid_side.py`
- Modificar: `app/sprite_engine/grammar/registry.py`
- Test: `tests/test_humanoid_side_grammar.py`

**Primera cobertura:**

```text
archetypes: generic, warrior
views: side-view
poses: side_neutral
parts: head/profile, torso, front/back limbs, boots, armor, hammer/sword/shield
```

**Regresiones basadas en artifacts:**

- Crear specs equivalentes a `sprite_20260712_032109_555eadf5` y `sprite_20260712_035834_a8bb8895` como fixtures nuevos, sin modificar artifacts históricos.
- Comprobar que `auto` ahora resuelve a `humanoid_side`.
- Comprobar que el blueprint reporta layers y material roles, no sólo `base`.

**Visual acceptance:** perfil inequívoco, sin apariencia frontal accidental.

---

## Fase 6 — QuadrupedSideGrammar

### Tarea 14: Modelar cuadrúpedos laterales

**Objetivo:** generalizar cerdo/lobo/perro sin hardcodear coordenadas por subject.

**Archivos:**
- Crear: `app/sprite_engine/character/quadruped_spec.py`
- Crear: `app/sprite_engine/character/quadruped_skeleton.py`
- Test: `tests/test_quadruped_skeleton.py`

**Contrato propuesto:**

```text
body_length: short | average | long
body_depth: slim | average | heavy
leg_length: short | average | long
head_shape: round | wedge
snout_length: short | average | long
ear_shape: floppy | triangular | upright
tail_shape: curly | straight | bushy
```

**Invariantes:** cuatro anchors de patas, cabeza conectada al cuerpo, ground line, dirección izquierda/derecha y bounds.

### Tarea 15: Implementar pig como primer arquetipo cuadrúpedo

**Objetivo:** promover la gramática visual observada en el artifact de cerdo a un compilador controlado.

**Archivos:**
- Crear: `app/sprite_engine/grammar/quadruped_side.py`
- Modificar: `app/sprite_engine/grammar/registry.py`
- Test: `tests/test_quadruped_side_grammar.py`

**Pig grammar:**

```text
round/heavy body
short legs
round head
short snout
triangular ears
curly tail
pink skin material
```

**Tests:**

- `pig + side-view` resuelve a procedural.
- Cuatro patas se anclan al cuerpo y suelo.
- Hocico está delante de la cabeza.
- Cola está detrás del cuerpo.
- Silueta distinta de humanoide.

Después de estabilizar pig, añadir wolf/dog en tareas separadas; no incluirlos en este incremento.

---

## Fase 7 — LLM fallback enriquecido y lineaje

### Tarea 16: Pedir layers/material roles a los LLM blueprints

**Objetivo:** permitir que el fallback use el compositor semántico sin convertir el renderer en subject-aware.

**Archivos:**
- Modificar: `app/services/sprite_blueprint.py`
- Modificar: `app/schemas/sprite.py`
- Test: `tests/test_sprite_blueprint_generation.py`

**Contrato LLM extendido:**

```text
layer_order
material_roles
primitive.layer
lighting direction opcional
```

**Validación:**

- Cada layer usada aparece en `layer_order`.
- Cada material role referencia un fill existente.
- Sólo materiales soportados.
- Blueprints históricos sin campos nuevos conservan defaults.

### Tarea 17: Persistir trazabilidad de selección

**Objetivo:** responder desde metadata si se usó grammar, skeleton o LLM sin inferencia manual.

**Archivos:**
- Modificar: `app/models/sprite_artifact.py`
- Modificar: `app/services/sprite_artifact_store.py`
- Modificar: `app/services/sprite.py`
- Test: `tests/test_artifact_store.py`
- Test: `tests/test_sprite.py`

**Metadata propuesta:**

```json
{
  "blueprint_generation": {
    "requested_strategy": "auto",
    "resolved_strategy": "procedural",
    "grammar": "humanoid_side",
    "grammar_version": 1,
    "family": "humanoid",
    "archetype": "warrior",
    "skeleton": "HumanoidSideSkeleton",
    "seed": 0
  }
}
```

Para LLM:

```json
{
  "resolved_strategy": "llm_blueprint",
  "grammar": null,
  "skeleton": null,
  "fallback_reason": "no grammar supports humanoid side-view wizard"
}
```

No guardar prompts completos adicionales, respuestas crudas ni secretos.

---

## Fase 8 — Integración, UI y documentación

### Tarea 18: Exponer la decisión sin saturar la UI

**Objetivo:** hacer visible por qué se usó grammar o LLM.

**Archivos:**
- Modificar: `app/templates/partials/sprite_result.html`
- Modificar: `app/templates/partials/sprite_preview.html`
- Modificar: `app/routes/web.py` sólo si falta contexto para templates
- Test: `tests/test_api_and_web.py`

**Mostrar:**

```text
Strategy: procedural | llm_blueprint
Family: humanoid
Archetype: warrior
Grammar: humanoid_side (o "LLM fallback")
Reason: capability match / unsupported view
```

Mantener feedback visible durante ejecución y confirmación explícita al finalizar.

### Tarea 19: Actualizar documentación

**Objetivo:** reflejar la arquitectura real, no la futura.

**Archivos:**
- Modificar: `docs/architecture.md`
- Modificar: `README.md`
- Crear opcional: `docs/visual-grammars.md`

**Documentar:**

- Diferencia entre family, archetype, grammar, recipe, skeleton y renderer.
- Tabla de capabilities.
- Flujo `auto` y fallback.
- Contrato de metadata.
- Limitaciones reales por vista/arquetipo.
- Cómo añadir una nueva gramática sin tocar el renderer.

---

## Validación final

### Tarea 20: Quality gates y smoke tests

**Comandos obligatorios:**

```bash
uv run ruff format .
uv run ruff check .
uv run pytest -q
git diff --check
```

**Smoke procedural:**

```text
warrior front  -> humanoid_front
wizard front   -> humanoid_front
warrior side   -> humanoid_side (después de Fase 5)
pig side       -> quadruped_side (después de Fase 6)
unknown asset  -> llm_blueprint en auto
```

**Smoke runtime:**

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8014
curl --fail http://127.0.0.1:8014/api/settings
```

Detener el servidor temporal intencionalmente después de verificar HTTP 200.

**Verificación de artifacts nuevos:**

- `metadata.json` explica requested/resolved strategy y grammar.
- `blueprint.json` tiene recipe, layers, material roles y primitives reproducibles.
- `render.png` es RGBA, legible a 1× y pasa quality gates.
- Artefactos históricos permanecen intactos.

---

## Riesgos y mitigaciones

1. **Explosión de variantes.** No crear clases por combinación; usar slots y piezas reutilizables.
2. **Grammar demasiado genérica.** Mantener compiladores por familia/vista y capabilities estrictas.
3. **Campos de spec sin efecto.** Añadir tests que comparen estructura/bbox/layers para cada campo soportado.
4. **Regresiones de persistencia.** Campos nuevos con defaults y fixtures de JSON histórico.
5. **Confundir `icon/front`.** En esta implementación conservar el valor por compatibilidad; planear después una migración separada a `view="front"` + `presentation="icon"`.
6. **Side-view que parece frontal.** Acceptance visual + anchors de perfil + test estructural de oclusión.
7. **LLM reportado como procedural.** Metadata separa requested/resolved strategy, grammar y fallback reason.
8. **Renderer subject-aware.** Prohibir imports desde `grammar/` hacia `rendering/`; sólo consume blueprint.
9. **Árbol de trabajo ya modificado.** Estabilizar Fase 0 y no mezclar commits sin autorización.

---

## Orden recomendado de entregas

```text
Entrega 1: clasificación + capabilities + registry
Entrega 2: HumanoidFrontGrammar rica
Entrega 3: HumanoidSideGrammar
Entrega 4: QuadrupedSideGrammar/pig
Entrega 5: LLM layers + metadata + UI/docs
```

Cada entrega debe terminar con suite completa, smoke render y revisión visual antes de iniciar la siguiente.
