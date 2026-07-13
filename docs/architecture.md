# Arquitectura de PixelForge

## Flujo

```text
Prompt -> intérprete semántico -> AssetSpec
  -> selección de estrategia
     -> creativo/auto: LLM -> SpriteBlueprint JSON validado
     -> controlado: GrammarRegistry -> grammar -> skeleton -> partes/layers/materiales -> SpriteBlueprint
  -> compositor/rasterizador genérico -> outline/paleta/calidad -> artifact
```

El camino creativo es LLM-first incluso cuando existe una gramática compatible. El modo `controlled` y la estrategia explícita `procedural` conservan el compilador determinista. El renderer consume únicamente `SpriteBlueprint`: no importa gramáticas, no llama modelos y no conoce subjects.

## Contratos y conceptos

- **family**: familia geométrica (`humanoid`, `quadruped`, `dragon`, `prop`, `unknown`).
- **archetype**: variante semántica extensible, persistida como string (por ejemplo `warrior`).
- **template**: intención de producto tipada (`warrior_front`, `warrior_side`, `wizard_front`, `pig_side`) que fija familia, arquetipo, vista y, cuando aplica, pose; nunca contiene geometría.
- **blueprint strategy**: backend solicitado (`auto`, `procedural`, `llm_blueprint`); no es una template ni una recipe.
- **grammar**: compilador determinista de un spec tipado a blueprint; no llama al LLM.
- **skeleton**: anchors e invariantes geométricas de una familia/vista.
- **recipe**: identificador persistido de la construcción concreta (`humanoid_side/warrior`). Las recipes históricas de dragon/potion/sword continúan disponibles para compatibilidad de `auto`.
- **renderer**: compositor genérico de primitives, layers, materiales, iluminación y outline.

`AssetSpec.family`, `archetype` y `generation_mode` tienen defaults compatibles. `SpriteBlueprint.layer_order`, `material_roles` y `lighting_direction` también tienen defaults, por lo que JSON históricos siguen validando.

## Intención de request y procedencia de vista

`POST /api/asset-spec` y el formulario HTMX aceptan opcionalmente `view`, `template_id`, `generation_mode` y `blueprint_strategy`. La precedencia de vista es: template > `view` explícito > default determinista > interpretación. Para humanoid, prop y unknown el default inicial es `icon/front`; el LLM no decide esa vista por defecto. La respuesta incluye `decision_trace` seguro (`requested_view`, `view_source`, `template_id`) y el mismo objeto se conserva en `metadata.json` del artifact.

| Template | Family/archetype | Vista | Pose |
| --- | --- | --- | --- |
| `warrior_front` | humanoid / warrior | `icon/front` | `front_neutral` |
| `warrior_side` | humanoid / warrior | `side-view` | `side_neutral` |
| `wizard_front` | humanoid / wizard | `icon/front` | `front_neutral` |
| `pig_side` | quadruped / pig | `side-view` | — |

## Selección

`blueprint_strategy` selecciona backend; `generation_mode` expresa intención:

| Estrategia/modo | Resultado |
| --- | --- |
| `procedural` | exige grammar compatible; si no existe, error explícito |
| `llm_blueprint` | LLM, sin consultar el modo |
| `auto` + `controlled` | grammar obligatoria |
| `auto` + `exploratory` | LLM; es el default de creación |
| `auto` + `auto` | LLM creativo; conserva el reason de capability cuando no existe grammar |

El clasificador central de `grammar/classification.py` se usa durante interpretación y su resultado queda persistido; el registry no reclasifica por substrings.

## Capabilities implementadas

| Grammar | Family | Views | Archetypes | Skeleton |
| --- | --- | --- | --- | --- |
| `humanoid_front` | humanoid | `icon/front` | generic, blacksmith, warrior, wizard | `HumanoidSkeleton` |
| `humanoid_side` | humanoid | `side-view` | generic, warrior | `HumanoidSideSkeleton` |
| `quadruped_side` | quadruped | `side-view` | pig | `QuadrupedSkeleton` |

No están implementados wizard lateral, wolf/dog procedural, dragon como grammar nueva, top-down 3/4, animación ni perspectiva libre. Esos pedidos usan fallback LLM en `auto`.

## Compilación y render

Las gramáticas viven en `app/sprite_engine/grammar/`; skeletons/specs acotados en `character/`. Humanoide frontal reutiliza `build_humanoid_skeleton()` y la compilación histórica de partes. Los skeletons lateral y cuadrúpedo son independientes. El cerdo usa cuatro patas conectadas y apoyadas, hocico delantero y cola trasera.

Los blueprints declaran orden de capas, roles de material y `lighting_direction`. `rendering/rasterizer.py` compone canvases RGBA por capa y aplica ramps de cloth/leather/wood/metal/skin/hair; `top_left` y `top_right` invierten bordes iluminados. La validación semántica comprueba recipe/grammar, layers, fills de materiales y partes estructurales mínimas antes de persistir.

## Validación semántica y reparación LLM

Antes de persistir un blueprint, se valida el schema, contratos de grammar/layers/materiales, semántica determinista y calidad raster. Para humanoides, la semántica mide la silueta raster y las primitives: un lateral rechaza `side_view_symmetry_too_high`, `side_view_missing_directional_feature` o `side_view_missing_limb_depth`; un frontal LLM puede rechazar `front_view_symmetry_too_low`. Las grammars además reportan conflictos de familia/vista, recipe, layers, materiales y requisitos de arquetipo.

Una grammar que falla es un error de código y no se reintenta. Un blueprint LLM que falla schema, semántica o raster recibe exactamente un repair con el Asset Spec canónico, diagnósticos acotados y el candidato original marcado explícitamente como datos no confiables. El candidato rechazado no se persiste como artifact exitoso. Si el repair también falla, el artifact queda `blueprint_failed` con `generation_error` y no se escribe `blueprint.json` ni `render.png` como éxito. Los reports semánticos aprobados se guardan en `metadata.json.blueprint_generation.semantic_quality` y se muestran en la UI.

Los artifacts históricos no se modifican: la corrección de un resultado antiguo requiere crear/regenerar un artifact nuevo de forma deliberada.

## Fallback LLM y lineaje

El contrato LLM permite `primitive.layer`, `layer_order`, `material_roles` y `lighting_direction`; se validan layers, fills, materiales, coordenadas, primitive budget y calidad raster. No hay fallback silencioso a `generic_prop`.

`metadata.json.blueprint_generation` registra:

```json
{
  "requested_strategy": "auto",
  "resolved_strategy": "procedural",
  "strategy": "procedural",
  "grammar": "humanoid_side",
  "grammar_version": 1,
  "family": "humanoid",
  "archetype": "warrior",
  "skeleton": "HumanoidSideSkeleton",
  "fallback_reason": null,
  "seed": 0
}
```

`strategy` se conserva como alias histórico. En LLM, grammar/skeleton son `null` y `fallback_reason` explica la capability faltante. No se guardan respuestas crudas ni secretos.

## Añadir una grammar

1. Añadir spec/skeleton tipados con invariantes y tests.
2. Implementar `name`, `capabilities`, `skeleton_name`, `supports(spec completo)` y `compile()`.
3. Registrar el compilador en `GrammarRegistry`.
4. Probar reproducibilidad, bounds, layers/materiales, routing y fallback.
5. Añadir fixture/contact sheet si afecta una referencia visual.

No se modifica el renderer para añadir una familia.

## Persistencia e interfaces

`SpriteService` orquesta y `SpriteArtifactStore` guarda `asset-spec.json`, `blueprint.json`, `render.png`, `metadata.json` e índice SQLite. Las rutas FastAPI permanecen delgadas. La UI HTMX muestra strategy, family, archetype, grammar y razón.

El benchmark frontal se genera sin artifacts de producto:

```bash
uv run python scripts/render_grammar_contact_sheet.py
# /tmp/pixelforge-grammar-front-contact-sheet.png
```

## Verificación

```bash
uv run ruff format .
uv run ruff check .
uv run pytest -q
git diff --check
```
