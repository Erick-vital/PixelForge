# Arquitectura de PixelForge

## Propósito

PixelForge genera sprites PNG pixel-art de forma procedural y reproducible. El flujo principal transforma una petición de usuario en datos estructurados antes de rasterizar:

```text
Prompt
  -> Asset Spec
  -> Sprite Blueprint
  -> rasterizador genérico + outline pass
  -> validación de calidad
  -> PNG + artefacto persistido
```

El renderer no contiene conocimiento de subjects específicos. Los subjects y sus geometrías viven en la generación de blueprints; el renderer solamente conoce primitives.

## Capas del proyecto

| Capa | Directorio | Responsabilidad |
| --- | --- | --- |
| HTTP | `app/routes/` | Parsear solicitudes, inyectar servicios, traducir errores y devolver JSON, HTML o PNG. |
| Contratos | `app/schemas/` | Modelos Pydantic públicos: Asset Spec, requests, Sprite Blueprint y primitives. |
| Modelos internos | `app/models/` | Dataclasses y DTOs internos, por ejemplo calidad raster y esqueleto humanoide. |
| Servicios | `app/services/` | Interpretación, generación, render, validación, persistencia, LLM, configuración y procesamiento. |
| UI | `app/templates/`, `app/static/` | Páginas Jinja2, fragments HTMX y estilos. |
| Pruebas | `tests/` | Pruebas herméticas de servicios, renderer, API y UI. |

`SpriteService` (`app/services/sprite.py`) es la capa de orquestación. Las rutas API y web no deberían reimplementar lógica de generación, calidad o persistencia.

## Pipeline de sprites

### 1. Asset Spec

`POST /api/asset-spec` recibe un prompt y usa `app/services/sprite_interpretation.py` para crear el `AssetSpec` canónico. El spec reúne subject, tipo, view, tamaño, palette, shape, restricciones técnicas y processing profile.

El artefacto se crea inmediatamente mediante `SpriteArtifactStore`:

- `asset-spec.json`
- `blueprint.json` cuando esté disponible
- `render.png` cuando se renderice
- `metadata.json`
- una fila en SQLite

La configuración de rutas y base de datos viene de `app/services/settings.py` mediante variables `APP_*`.

### 2. Generación de blueprint

`POST /api/blueprint` recibe un `artifact_id`, una estrategia y un seed.

`app/services/sprite_blueprint.py` resuelve la estrategia:

- `auto`: receta procedural si el subject es conocido; LLM en caso contrario.
- `procedural`: usa una receta local, incluido el fallback `generic_prop`.
- `llm_blueprint`: solicita JSON estricto al proveedor configurado.

El LLM devuelve datos, nunca código de renderer. Antes de persistir, un blueprint LLM pasa por:

1. extracción de JSON;
2. validación Pydantic de `SpriteBlueprint`;
3. validación semántica: palette, fills, coordenadas `0..63`, primitive budget y geometría;
4. raster temporal y validación de calidad;
5. a lo sumo una solicitud de reparación si cualquier paso falla.

No existe fallback silencioso desde un LLM inválido a un sprite genérico.

### 3. Blueprints y primitives

Los blueprints se definen en una cuadrícula base de 64x64 y usan sólo estas operaciones:

- `ellipse`
- `rectangle`
- `polygon`
- `line`
- `point`

El renderer escala las primitives a 32, 64 o 128px. Un `SpriteBlueprint` también incluye un `SpriteOutlineSpec` persistible:

```json
{
  "enabled": true,
  "color_key": "outline",
  "width": 1
}
```

El default es `enabled=false` para preservar el aspecto de blueprints históricos. Las recetas nuevas habilitan explícitamente el outline.

### 4. Renderer y outline pass

`app/services/procedural_sprite.py` contiene el rasterizador genérico. Su orden de trabajo es:

1. crear canvas RGBA transparente;
2. escalar y rasterizar primitives de atrás hacia adelante;
3. si `outline.enabled`, convertir alpha en máscara, dilatarla con vecindad de 8 vecinos y pintar `dilate(alpha) AND NOT alpha` detrás del contenido;
4. limitar la paleta;
5. serializar como PNG y construir el reporte técnico.

El outline es el borde externo de la silueta. No sustituye detalles internos como ojos, divisiones o líneas decorativas: éstos permanecen como primitives con `fill="outline"` cuando corresponde.

## Recetas procedurales

`known_procedural_recipe()` centraliza la selección de recipes para evitar discrepancias entre `auto` y el builder local.

| Subject/token | Recipe | Generador |
| --- | --- | --- |
| `dragon` | `baby_dragon` | `procedural_sprite.py` |
| `potion` | `potion` | `procedural_sprite.py` |
| `sword` | `sword` | `procedural_sprite.py` |
| `human`, `humanoid`, `person`, `chibi` | `humanoid_chibi` | `humanoid_sprite.py` |
| cualquier otro (sólo estrategia procedural) | `generic_prop` | `procedural_sprite.py` |

### Humanoide chibi

`HumanoidSkeleton` (`app/models/humanoid.py`) contiene anchors e invariantes del cuerpo base: eje `x=32`, ground line, alto de cabeza, torso, cadera y piernas. `compile_humanoid_base()` convierte ese modelo en un blueprint frontal de cabeza, torso y piernas simétricas. No agrega brazos, equipo, animación ni overlays.

Esta separación protege el límite arquitectónico: el compilador conoce el dominio humanoide; `render_blueprint()` no.

## Calidad raster

`app/services/sprite_quality.py` analiza el canal alpha del PNG final. La política inicial para un sprite unitario exige:

- exactamente un componente opaco, usando conectividad de 8 vecinos;
- occupancy ratio entre `0.08` y `0.70`;
- cero componentes de un solo píxel.

El servicio devuelve `SpriteQualityReport` con métricas y issues estables:

- `component_count`
- `occupancy_too_low`
- `occupancy_too_high`
- `isolated_pixels`

`SpriteService.render_sprite()` y `render_blueprint()` validan calidad antes de guardar `render.png`. Un fallo se traduce a `SpriteError`, por lo que las rutas devuelven un error controlado y el artefacto no se marca como renderizado exitosamente.

Los endpoints de render incluyen además headers compactos:

- `X-PixelForge-Quality-Passed`
- `X-PixelForge-Quality-Components`
- `X-PixelForge-Quality-Occupancy`
- `X-PixelForge-Quality-Isolated-Pixels`

## Persistencia y lineaje

`SpriteArtifactStore` persiste los archivos del artefacto y mantiene SQLite como índice. `metadata.json` conserva timestamps, status, rutas y la procedencia del blueprint (estrategia, provider/model cuando aplica y seed).

Al renderizar, PixelForge prefiere siempre `blueprint.json` persistido. Sólo construye directamente desde el Asset Spec cuando el artefacto todavía no tiene blueprint. Esto evita que un render posterior sustituya un blueprint LLM válido por una receta local diferente.

## Interfaces

### JSON API

- `POST /api/asset-spec`: crear y persistir un Asset Spec.
- `POST /api/blueprint`: crear y persistir un blueprint.
- `POST /api/render-sprite`: renderizar blueprint persistido o receta local inicial.
- `POST /api/render-blueprint`: renderizar el blueprint persistido.
- `POST /api/process-sprite`: procesar un PNG externo según un Asset Spec.
- `GET /api/settings`: exponer configuración no secreta.

### Web

- `GET /sprite`: página Jinja2 del flujo principal.
- `POST /ui/sprite/spec`: HTMX para Asset Spec + blueprint.
- `POST /ui/sprite/render` y `/ui/sprite/render-blueprint`: fragments de preview PNG.

La UI preserva el patrón de swap `#results` y feedback visible de progreso, éxito y error.

## Verificación de cambios

Para cambios Python en PixelForge:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Para cambios de comportamiento runtime, iniciar `uvicorn`, validar el endpoint afectado y detener el proceso después del smoke test.
