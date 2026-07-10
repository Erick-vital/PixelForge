# Outline automático, calidad mínima y humanoide chibi — Plan de implementación

> **Para Hermes:** usar `subagent-driven-development` para ejecutar este plan tarea por tarea, con revisión de especificación y de calidad. No hacer commits salvo que Erick lo pida explícitamente.

**Objetivo:** mejorar de forma transversal la legibilidad de todos los sprites nuevos mediante contornos consistentes y validación raster objetiva; después agregar una primera familia procedural humanoide chibi basada en un esqueleto parametrizado.

**Arquitectura:** conservar el pipeline `AssetSpec -> SpriteBlueprint -> PNG`. El renderer seguirá siendo genérico: rasteriza primitives y aplica un postproceso de contorno sin conocer dragones o humanoides. La calidad raster vivirá en un servicio independiente. El conocimiento humanoide se dividirá entre un modelo interno `HumanoidSkeleton` y un compilador que produce `SpriteBlueprint`.

**Stack:** Python 3.11+, Pydantic, Pillow, NumPy, pytest, uv y Ruff.

---

## Recomendación

Sí recomiendo la implementación y también el orden propuesto: **contorno -> métrica/rechazo -> humanoide**. Son tres capas con dependencias correctas:

1. El contorno automático reduce trabajo geométrico repetido tanto en recetas locales como en blueprints nuevos del LLM.
2. El validador permite demostrar si una receta nueva produce un sprite utilizable, en vez de aceptar cualquier PNG no vacío.
3. El humanoide introduce dominio nuevo sólo después de tener renderer y criterios de aceptación mejores.

Sin embargo, recomiendo estos ajustes importantes:

- **No aplicar el contorno incondicionalmente a blueprints históricos.** Los blueprints actuales ya contienen primitives exteriores con `fill="outline"`; activar otro contorno encima produciría bordes dobles. Agregar una configuración explícita y versionable en `SpriteBlueprint`, inicialmente desactivada por defecto para JSON histórico y activada por los generadores nuevos.
- **El pase propuesto crea un contorno de la silueta alfa, no bordes entre todas las piezas internas.** Ojos, separaciones, pliegues y otros detalles oscuros deben seguir siendo primitives normales. Esto es deseable: elimina duplicados de silueta, no el lenguaje de detalle interno.
- **No prometer literalmente “~20 líneas” para el cambio completo.** La operación morfológica sí es pequeña, pero una implementación segura también necesita contrato de blueprint, migración de recetas, actualización del prompt del LLM, compatibilidad y pruebas.
- **Calibrar el validador con ratios, no con números de píxeles absolutos.** PixelForge soporta 32, 64 y 128 px. Como baseline medido hoy en 64x64: dragón `0.3318`, poción `0.1855`, espada `0.1560`, generic prop `0.1829` de ocupación; todos tienen un componente y cero píxeles aislados. Un rango inicial conservador de `0.08..0.70` no rompe estas recetas.
- **Usar conectividad de 8 vecinos.** En pixel art, dos píxeles diagonales suelen percibirse como conectados. La conectividad de 4 vecinos produciría falsos rechazos.
- **Permitir una sola reparación LLM, no un retry ilimitado.** El proyecto ya tiene un único intento de reparación para JSON inválido; los errores de calidad deben entrar en ese mismo presupuesto de un retry.

## Alcance y decisiones cerradas

- El outline se define en coordenadas base de 64px. `width=1` equivale a 1px en 64x64, se mantiene en al menos 1px para 32x32 y escala a 2px para 128x128.
- La dilatación usa vecindad 8 (kernel cuadrado) implementada con NumPy/Pillow; no se agrega SciPy.
- El contorno se compone detrás del raster original: `dilate(alpha) AND NOT alpha`, color `palette[color_key]`.
- El control de outline se modela en el blueprint, no en `AssetSpec`, porque es una decisión concreta de render y debe persistir con el artefacto.
- El validador analiza el alpha del PNG renderizado y devuelve un reporte estructurado; no inspecciona nombres de recipes o subjects.
- Reglas iniciales: exactamente 1 componente opaco, ocupación entre 8% y 70%, y 0 píxeles opacos aislados.
- Un componente es un grupo de píxeles alpha > 0 conectado por 8 vecinos.
- Un píxel aislado es un componente de tamaño 1. Se reportan tanto `connected_components` como `isolated_pixel_count` aunque estén relacionados, porque generan diagnósticos distintos.
- El humanoide inicial es frontal, simétrico alrededor de `x=32`, con cabeza + torso + dos piernas, pies apoyados en una ground line. Sin brazos, equipo, animación ni overlays en esta fase.
- La simetría se genera con una función espejo; no se escriben manualmente coordenadas independientes para izquierda y derecha.
- No se amplían todavía `AllowedAssetType` ni la UI. Un humanoide puede entrar como `enemy` y ser seleccionado por el subject.

## Contratos propuestos

### Configuración de outline persistida

En `app/schemas/sprite.py`:

```python
class SpriteOutlineSpec(BaseModel):
    enabled: bool = False
    color_key: str = "outline"
    width: int = Field(default=1, ge=1, le=4)


class SpriteBlueprint(BaseModel):
    recipe: str
    subject: str
    palette: dict[str, str]
    primitives: list[SpritePrimitive]
    outline: SpriteOutlineSpec = Field(default_factory=SpriteOutlineSpec)
    notes: list[str] = Field(default_factory=list)
```

El default `False` mantiene el aspecto de blueprints ya persistidos. Todas las recetas migradas y los blueprints LLM nuevos emitirán explícitamente `"outline": {"enabled": true, ...}`.

### Reporte de calidad

Modelo interno sugerido en `app/models/sprite_quality.py`:

```python
@dataclass(frozen=True)
class SpriteQualityIssue:
    code: str
    message: str


@dataclass(frozen=True)
class SpriteQualityReport:
    passed: bool
    connected_components: int
    occupancy_ratio: float
    isolated_pixel_count: int
    issues: tuple[SpriteQualityIssue, ...]
```

`app/services/sprite_quality.py` expondrá:

```python
def evaluate_sprite_quality(image: Image.Image) -> SpriteQualityReport: ...

def require_sprite_quality(image: Image.Image) -> SpriteQualityReport: ...
```

`require_sprite_quality` lanzará `SpriteQualityError` con el reporte completo para que el retry LLM y los errores HTTP reciban diagnósticos concretos.

### Esqueleto humanoide

Modelo interno sugerido en `app/models/humanoid.py`:

```python
@dataclass(frozen=True)
class HumanoidSkeleton:
    center_x: int = 32
    ground_y: int = 58
    head_top_y: int = 6
    head_bottom_y: int = 31
    shoulder_y: int = 31
    waist_y: int = 43
    hip_y: int = 45
    leg_bottom_y: int = 58
    head_half_width: int = 13
    torso_half_width: int = 9
    hip_half_width: int = 7
    leg_half_width: int = 3
    leg_gap: int = 2
```

El compilador deberá validar invariantes: coordenadas dentro de `0..63`, `head_top_y < ... < ground_y`, eje en `x=32`, ancho positivo y altura total aproximadamente dos veces la altura de cabeza (tolerancia explícita en tests).

---

## Fase 0: Caracterización y fixtures de regresión

### Tarea 1: Capturar las invariantes actuales del renderer

**Objetivo:** tener pruebas que distingan silueta, detalle interno, escalado y compatibilidad histórica antes de cambiar píxeles.

**Archivos:**
- Modificar: `tests/test_procedural_sprite.py`

**Pasos:**

1. Agregar un helper de test que abra `ProceduralSpriteResult.png_bytes` como RGBA.
2. Agregar un blueprint mínimo sin configuración `outline` y comprobar que conserva el comportamiento legacy: no aparece color de outline fuera de su primitive.
3. Agregar un blueprint con una forma base y un detalle oscuro interno para demostrar que ambos sobreviven al futuro postproceso.
4. Ejecutar sólo estas pruebas y confirmar que pasan antes de modificar producción:
   - `uv run pytest -q tests/test_procedural_sprite.py`
5. No usar snapshots binarios frágiles; comprobar coordenadas/píxeles representativos, bbox y conteos.

**Aceptación:** hay una prueba explícita de compatibilidad para un `SpriteBlueprint` sin el nuevo campo.

---

## Fase 1: Pase de contorno automático

### Tarea 2: Agregar el contrato explícito de outline

**Objetivo:** hacer que el postproceso sea persistible, validable y compatible con artifacts existentes.

**Archivos:**
- Modificar: `app/schemas/sprite.py`
- Modificar: `tests/test_sprite_blueprint_generation.py`

**Pasos TDD:**

1. Escribir tests de `SpriteBlueprint.model_validate` para:
   - JSON histórico sin `outline` => `enabled is False`;
   - configuración válida => `enabled=True`, `width=1`;
   - width `0` o `>4` => error Pydantic.
2. Ejecutar las pruebas y comprobar el fallo por ausencia de `SpriteOutlineSpec`.
3. Implementar `SpriteOutlineSpec` y añadirlo a `SpriteBlueprint`.
4. Ejecutar las pruebas y confirmar que pasan.

### Tarea 3: Implementar la operación morfológica aislada

**Objetivo:** producir un anillo de contorno consistente sin conocimiento del subject.

**Archivos:**
- Modificar: `app/services/procedural_sprite.py`
- Modificar: `tests/test_procedural_sprite.py`

**Diseño:**

1. Extraer una función privada `_apply_outline_pass(image, *, color, width) -> Image.Image`.
2. Obtener `alpha = np.asarray(image.getchannel("A")) > 0`.
3. Dilatar por cada pixel de radio mediante padding/ventanas desplazadas de 8 vecinos; no hacer wrap en bordes.
4. Calcular `outline_mask = dilated & ~alpha`.
5. Crear una capa RGBA transparente, pintar sólo `outline_mask`, y hacer `Image.alpha_composite(outline_layer, image)`.
6. Aplicar outline después de rasterizar primitives y antes de `_limit_palette`.
7. Resolver `color_key` mediante la paleta; si está habilitado y no existe, lanzar `ProceduralSpriteError`.
8. Escalar el ancho con `max(1, round(base_width * min(scale_x, scale_y)))`.

**Pruebas:**

- Una primitive base cuadrada gana exactamente un anillo de 1px.
- El interior conserva sus colores byte por byte.
- Un punto cercano a un borde no produce wrap al borde opuesto.
- `enabled=False` no cambia el raster legacy.
- A 128x128 un outline base de 1 usa radio 2; a 32x32 usa radio 1.
- El resultado sigue siendo RGBA/transparente y determinista.

**Comando:** `uv run pytest -q tests/test_procedural_sprite.py`

### Tarea 4: Migrar recetas procedurales para eliminar siluetas duplicadas

**Objetivo:** reducir primitives manuales de outline sin perder detalles internos.

**Archivos:**
- Modificar: `app/services/procedural_sprite.py`
- Modificar: `tests/test_procedural_sprite.py`

**Pasos:**

1. Migrar `_blueprint_for_baby_dragon`:
   - quitar las elipses/polígonos/rectángulos de outline cuya única función es envolver una forma base más pequeña;
   - conservar ojos, líneas de cola y detalles oscuros que sí son contenido interno;
   - activar `SpriteOutlineSpec(enabled=True, color_key="outline", width=1)`.
2. Aplicar la misma regla a potion, sword y generic prop.
3. No forzar una reducción literal del 50% en todos los subjects; medir y fijar expectativas por recipe.
4. Tests estructurales:
   - todas las recipes nuevas tienen outline habilitado;
   - el dragón usa menos primitives que las 24 actuales;
   - ninguna recipe contiene pares triviales de misma operación/bbox concéntricos usados sólo como borde;
   - render determinista y válido en 32/64/128.
5. Ejecutar: `uv run pytest -q tests/test_procedural_sprite.py`.

### Tarea 5: Actualizar el contrato LLM para que no duplique contornos

**Objetivo:** lograr que los blueprints nuevos del LLM usen el pase automático, manteniendo details oscuros cuando sean semánticos.

**Archivos:**
- Modificar: `app/services/sprite_blueprint.py`
- Modificar: `tests/test_sprite_blueprint_generation.py`

**Pasos:**

1. Actualizar `LLM_BLUEPRINT_SYSTEM_PROMPT`:
   - incluir la clave top-level `outline`;
   - exigir `enabled=true`, `color_key="outline"`, `width=1`;
   - explicar que no debe crear una primitive grande de outline debajo de cada forma;
   - permitir `fill="outline"` sólo para detalles internos deliberados (ojos, separaciones, etc.).
2. En `validate_sprite_blueprint`, exigir que `color_key` exista en palette cuando outline esté habilitado.
3. Actualizar fixtures LLM válidos en tests para incluir outline explícito.
4. Añadir test de rechazo cuando `color_key` no exista.
5. Añadir test que confirme que JSON histórico parseado fuera del generador sigue con outline desactivado.
6. Ejecutar: `uv run pytest -q tests/test_sprite_blueprint_generation.py`.

**Aceptación de Fase 1:** recipes locales y blueprints LLM nuevos usan contorno automático; artifacts históricos siguen renderizando sin doble borde.

---

## Fase 2: Validador mínimo de calidad

### Tarea 6: Implementar métricas raster puras

**Objetivo:** medir componentes, ocupación y ruido sin acoplarse al renderer o al LLM.

**Archivos:**
- Crear: `app/models/sprite_quality.py`
- Crear: `app/services/sprite_quality.py`
- Crear: `tests/test_sprite_quality.py`

**Algoritmo:**

1. Convertir el alpha a máscara booleana `alpha > 0`.
2. `occupancy_ratio = foreground_pixels / (width * height)`.
3. Recorrer la máscara con flood-fill/BFS de 8 vecinos y registrar tamaño de cada componente.
4. `connected_components = len(component_sizes)`.
5. `isolated_pixel_count = count(size == 1)`.
6. Emitir issues estables con codes:
   - `component_count` si el total no es 1;
   - `occupancy_too_low` si `< 0.08`;
   - `occupancy_too_high` si `> 0.70`;
   - `isolated_pixels` si `> 0`.
7. Una imagen vacía falla con `component_count`, `occupancy_too_low`; no necesita un cuarto check.

**Pruebas unitarias herméticas:**

- silueta compacta válida => passed;
- dos bloques separados => `component_count`;
- ocupación de 1% => `occupancy_too_low`;
- ocupación de 90% => `occupancy_too_high`;
- cuerpo válido más un pixel suelto => `isolated_pixels` y dos componentes;
- contacto diagonal => un solo componente;
- resultados equivalentes por ratio en 32, 64 y 128.

**Comando:** `uv run pytest -q tests/test_sprite_quality.py`

### Tarea 7: Integrar calidad al reporte y rechazo antes de persistir

**Objetivo:** impedir que `render.png` se marque como exitoso si el raster está obviamente roto.

**Archivos:**
- Modificar: `app/services/sprite.py`
- Modificar: `app/services/procedural_sprite.py` sólo para extender `_build_report`, si hace falta
- Modificar: `app/routes/api.py`
- Modificar: `tests/test_procedural_sprite.py`
- Modificar: `tests/test_api_and_web.py`

**Pasos:**

1. En `SpriteService.render_sprite` y `render_blueprint`, abrir el PNG RGBA y llamar `require_sprite_quality` **antes** de `save_render_png`.
2. Añadir al report un bloque serializable:

```json
{
  "quality": {
    "passed": true,
    "connected_components": 1,
    "occupancy_ratio": 0.18,
    "isolated_pixel_count": 0,
    "issues": []
  }
}
```

3. En fallo, convertir `SpriteQualityError` a `SpriteError` incluyendo codes y valores, sin guardar/actualizar el render como `rendered`.
4. Mantener rutas delgadas: sólo traducir `SpriteError` a HTTP 400.
5. Exponer headers compactos:
   - `X-PixelForge-Quality-Passed`;
   - `X-PixelForge-Quality-Components`;
   - `X-PixelForge-Quality-Occupancy`;
   - `X-PixelForge-Quality-Isolated-Pixels`.
6. Añadir prueba de servicio con blueprint de dos piezas: HTTP 400 y ausencia de `render.png` exitoso.
7. Añadir prueba de las cuatro recipes actuales y seeds representativos para evitar thresholds demasiado agresivos.

**Nota:** el validator permanece independiente; la decisión de rechazar y persistir pertenece a `SpriteService`.

### Tarea 8: Usar diagnósticos de calidad en la única reparación LLM

**Objetivo:** regenerar una vez un blueprint rasterizable pero visualmente inválido, sin loops.

**Archivos:**
- Modificar: `app/services/sprite_blueprint.py`
- Modificar: `tests/test_sprite_blueprint_generation.py`

**Pasos:**

1. Extraer un único flujo `_validate_candidate` que haga:
   - parse/Pydantic;
   - validación semántica del blueprint;
   - render temporal al tamaño de `AssetSpec`;
   - `evaluate_sprite_quality`.
2. Si falla parsing, semántica o calidad en el primer candidato LLM, consumir el único repair existente.
3. Para calidad, incluir en el prompt de reparación sólo diagnósticos estructurados seguros, por ejemplo:

```text
component_count: expected 1, observed 2
occupancy_too_low: expected >= 0.08, observed 0.03
```

4. No incluir PNG, contenido binario, secretos ni logs completos del prompt.
5. Si el segundo candidato falla, lanzar `BlueprintGenerationError` con los codes de calidad.
6. La ruta procedural no hace retry: si una recipe local falla, es un bug de código y debe fallar sus tests.
7. Tests con `SequencedBlueprintLlm`:
   - primer blueprint de dos piezas, segundo conectado => dos llamadas y éxito;
   - ambos inválidos => exactamente dos llamadas y error controlado;
   - candidato válido => una llamada.

**Aceptación de Fase 2:** ningún raster roto se persiste como exitoso y el LLM tiene como máximo una oportunidad de corregirse con feedback objetivo.

---

## Fase 3: HumanoidSkeleton y compilador chibi

### Tarea 9: Crear y validar `HumanoidSkeleton`

**Objetivo:** representar anchors y proporciones sin primitives ni lógica de renderer.

**Archivos:**
- Crear: `app/models/humanoid.py`
- Crear: `tests/test_humanoid_sprite.py`

**Pasos TDD:**

1. Escribir tests para defaults:
   - `center_x == 32`;
   - `ground_y == 58`;
   - orden vertical correcto;
   - margen transparente mínimo de 5px;
   - altura de cabeza / altura total cercana a 0.5, con tolerancia documentada.
2. Añadir `mirror_x(x) -> int` y probar `mirror_x(center_x-d) == center_x+d`.
3. Añadir `validate()` o validación en `__post_init__` para anchors fuera del canvas, orden invertido y anchos no positivos.
4. Mantener el modelo sin Pillow, Pydantic, LLM o primitives.
5. Ejecutar: `uv run pytest -q tests/test_humanoid_sprite.py`.

### Tarea 10: Compilar el cuerpo base a `SpriteBlueprint`

**Objetivo:** generar cabeza + torso + piernas simétricas como datos, sin agregar funciones de dibujo humanoide al renderer.

**Archivos:**
- Crear: `app/services/humanoid_sprite.py`
- Modificar: `tests/test_humanoid_sprite.py`

**Interfaz:**

```python
def compile_humanoid_base(
    subject: str,
    palette: dict[str, str],
    skeleton: HumanoidSkeleton,
) -> SpriteBlueprint: ...
```

**Geometría mínima:**

- cabeza: una ellipse base centrada en `center_x`, entre `head_top_y` y `head_bottom_y`;
- torso: polygon/base que solape 1–2px con la cabeza/cuello y llegue a la cadera;
- pierna izquierda: polygon o rectangle que solape la cadera y llegue a ground line;
- pierna derecha: espejo exacto de la izquierda;
- zapatos/pies opcionales sólo si son parte de la misma primitive de pierna o solapan; no agregar brazos ni accesorios;
- highlights/shadows sólo si no rompen simetría estructural;
- `outline.enabled=True` y sin primitives exteriores duplicadas.

**Pruebas:**

1. El blueprint sólo usa operations soportadas.
2. Las dos piernas son espejo exacto respecto a x=32.
3. El bbox total toca `ground_y` y conserva margen superior/lateral.
4. No hay primitives para brazos u overlays.
5. El raster pasa `evaluate_sprite_quality`: un componente, ocupación válida, cero aislados.
6. Determinismo: mismo skeleton + palette => mismo blueprint/PNG.

### Tarea 11: Registrar la familia procedural humanoide sin duplicar selección

**Objetivo:** integrar humanoides a `auto` y al renderer procedural usando una sola fuente de verdad para recipes conocidas.

**Archivos:**
- Modificar: `app/services/procedural_sprite.py`
- Modificar: `app/services/sprite_blueprint.py`
- Modificar: `tests/test_procedural_sprite.py`
- Modificar: `tests/test_sprite_blueprint_generation.py`
- Modificar: `tests/test_humanoid_sprite.py`

**Pasos:**

1. Reemplazar la duplicación actual entre `_recipe_for` y `_has_known_procedural_recipe` por una función compartida, por ejemplo:

```python
def known_procedural_recipe(subject: str) -> str | None: ...
```

2. Reconocer inicialmente tokens acotados y verificables: `human`, `humanoid`, `person`, `chibi`. Evitar términos ambiguos como `knight`, `wizard` o `zombie` hasta agregar overlays/variaciones.
3. En `build_sprite_blueprint`, recipe `humanoid_chibi` llama `compile_humanoid_base`.
4. En estrategia `auto`, la misma función decide que esos subjects son procedurales.
5. Añadir palette humanoide base explícita sin inferir etnia a partir del prompt. Usar colores de prueba neutrales/fantásticos o respetar palette canónica cuando ya exista una traducción soportada.
6. Tests:
   - `human chibi` => recipe `humanoid_chibi`;
   - `auto` no llama al LLM;
   - un término no soportado sigue resolviendo a LLM en `auto`;
   - 32/64/128 y varios seeds pasan calidad;
   - la ground line escala correctamente.

### Tarea 12: Prueba integral del pipeline y artifacts

**Objetivo:** demostrar el flujo real `AssetSpec -> Blueprint -> outline -> quality -> PNG`.

**Archivos:**
- Modificar: `tests/test_api_and_web.py`
- Modificar: `tests/test_procedural_sprite.py`
- Modificar: `README.md` sólo si ya documenta recipes/capacidades de generación

**Escenario integral:**

1. Crear un asset spec local para `human chibi`.
2. Crear blueprint con `strategy=auto`.
3. Comprobar recipe `humanoid_chibi`, outline habilitado y primitives sin bordes duplicados.
4. Renderizar vía `/api/render-blueprint`.
5. Comprobar PNG 64x64 RGBA, quality headers, un componente y cero aislados.
6. Comprobar que `blueprint.json`, `render.png` y metadata corresponden al mismo artifact.
7. Comprobar que un blueprint roto devuelve error visible y no queda con status `rendered`.

---

## Verificación final

Ejecutar en este orden desde `/home/erickesc/repos/PixelForge`:

```bash
uv run pytest -q tests/test_procedural_sprite.py
uv run pytest -q tests/test_sprite_quality.py
uv run pytest -q tests/test_humanoid_sprite.py
uv run pytest -q tests/test_sprite_blueprint_generation.py
uv run pytest -q tests/test_api_and_web.py
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Como se toca comportamiento runtime, iniciar la app:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Y en otra terminal verificar al menos `/api/settings` y un flujo real de asset/blueprint/render. Detener uvicorn al terminar.

## Métricas de éxito

- 100% de recipes procedurales nuevas usan outline automático explícito.
- El dragón usa menos de las 24 primitives actuales sin perder ojos/detalles internos.
- Todos los sprites procedurales soportados pasan calidad para los tamaños 32, 64 y 128 en los seeds cubiertos.
- Un sprite de dos piezas separadas falla antes de persistirse como render exitoso.
- Un pixel aislado falla con code estable.
- El LLM hace 1 llamada si el candidato es bueno y como máximo 2 si necesita reparación.
- El humanoide base tiene cabeza aproximadamente 50% de la altura total, simetría exacta en x=32, pies en ground line y un solo componente.
- Blueprints históricos sin campo `outline` mantienen comportamiento legacy.

## Riesgos y mitigaciones

1. **Contorno conecta piezas cercanas y oculta un fallo de componentes.**
   - Mitigación inicial: tests con separaciones mayores al radio de outline. Mejora posterior posible: evaluar conectividad sobre la máscara previa al outline, si aparecen falsos positivos reales.

2. **La quantización altera el color exacto del outline.**
   - Mitigación: aplicar outline antes de `_limit_palette`; probar presencia topológica del anillo y no depender siempre de RGB exacto cuando `max_colors` sea bajo.

3. **Artifacts históricos cambian visualmente.**
   - Mitigación: `outline.enabled=False` por defecto; sólo generators nuevos lo activan explícitamente.

4. **El validador rechaza assets legítimos de varias piezas (monedas, partículas, constelaciones).**
   - Mitigación: la fase mínima es estricta para sprites unitarios. No agregar excepciones prematuras; más adelante introducir perfiles de calidad por familia si surge un caso real.

5. **El outline global no separa cabeza/torso o piernas internamente.**
   - Mitigación: conservar líneas/detalles `fill="outline"` deliberados; el pase automático sólo resuelve la silueta externa.

6. **El compiler humanoide se vuelve un renderer específico disfrazado.**
   - Mitigación: `humanoid_sprite.py` sólo devuelve `SpriteBlueprint`; `procedural_sprite.py` sigue siendo el único rasterizador genérico.

7. **Selección procedural inconsistente entre build y estrategia auto.**
   - Mitigación: una única función `known_procedural_recipe` compartida.

## Fuera de alcance

- Brazos, manos, armas, ropa, cabello, expresiones y overlays.
- Animación o spritesheets.
- Poses no frontales.
- IK o sistema de bones general.
- Excepciones de calidad por tipo de asset.
- Nuevas opciones de UI para editar skeleton/outline.
- Migración masiva de artifacts históricos ya guardados.
- Retries procedurales automáticos.

## Secuencia de entrega sugerida

1. PR/cambio A: contrato + outline + migración de recipes/LLM.
2. PR/cambio B: quality model/service + integración + retry LLM.
3. PR/cambio C: skeleton + compiler + recipe humanoide + pruebas integrales.

Cada bloque debe quedar verde de forma independiente antes de iniciar el siguiente.