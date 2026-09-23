# Pares encastrados y una cartera de combinaciones en paralelo — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el motor reconozca las copias de una misma forma, pruebe encastrarlas de a pares con varios tipos de encastre, y acomode en paralelo -- una por núcleo -- una cartera de variantes (sin pares, combinaciones de tipos de par, perturbaciones), quedándose con la de menor `CostoLayout`; más un control de Núcleos y el cartel "No se puede con menos placas".

**Architecture:** Tres módulos nuevos del motor, en cadena: `iguales.py` agrupa piezas congruentes en `Clase`s (con la transformación `g` de cada miembro a su representante), `pares.py` busca tipos de encastre de dos copias por FFT y los funde en una `Part` compuesta que el oráculo, las máscaras y el empacador no distinguen de una pieza común, y `cartera.py` arma las variantes en un orden fijo, las evalúa (en un `ProcessPoolExecutor` con `spawn` cuando hay más de un núcleo), corre recuperación y compactación sobre la ganadora y la **desarma** en piezas reales antes de devolverla. `pack()` pasa a delegar en la cartera; su firma no cambia. El verificador de siempre revisa las piezas reales: una compuesta nunca llega a `verify`, al DXF ni a la previsualización.

**Tech Stack:** Python 3.13, numpy, scipy (`fftconvolve`), shapely, `concurrent.futures` + `multiprocessing` de la biblioteca estándar, pytest. Interfaz en HTML/CSS/JavaScript a mano, sin framework; sus tests leen los archivos estáticos como texto y no corren navegador.

**Spec:** `docs/superpowers/specs/2026-09-22-pares-y-cartera-design.es.md`

**Experimentos de referencia** (código descartable, no se copia tal cual): `/private/tmp/claude-501/-Users-raulo-Projects-cut-placement/9c986b8f-a879-475b-a2eb-ac88c8305805/scratchpad/pares.py` (el de la spec, 1.2) y, en la misma carpeta, `ele.py`, `sweep.py`, `sweep2.py`, `rango2.py` y `banq.py`, que se corrieron al escribir este plan para fijar el caso sintético (Tarea 9) y las dos decisiones medidas de la Tarea 3.

## Global Constraints

- **TDD sin excepciones:** test que falla, correrlo para verlo fallar, implementación mínima, test que pasa, commit. Un paso por vez.
- **Todo texto de cara al usuario va en español**, con tildes y eñes.
- **Idioma del código:** los identificadores van en inglés en `src/nesting/engine/`, `model/`, `io/` y `geometry/`, y en español en `params.py` y en todo `src/nesting_app/`. Los **docstrings y comentarios** son mixtos en todo el repo y no hay una regla que seguir: `model/entities.py` y `model/part.py` están en inglés, `model/discard.py` entero en español, `model/material.py` mezclado. Escribir el docstring en el idioma en que se piensa mejor la explicación es lo que viene haciendo el repo. **No es un hallazgo de revisión** que un docstring esté en un idioma u otro.
- **Excepción a la regla de idioma, a propósito:** los nombres que la spec fija por escrito se usan tal cual aunque caigan en `engine/` o `geometry/`: `componer`, `Clase`, `TIPOS_POR_CLASE`, `cota_minima`, `NestParams.nucleos`, `GET /api/sistema`. Es lo mismo que ya pasa con `CostoLayout`, `Avance` y `Cancelado`. Todo nombre nuevo que la spec **no** fija va en inglés en el motor.
- **Nada de emojis.** El test `test_no_hay_emojis_en_la_interfaz` ya lo prohíbe y no se relaja.
- **Ningún token de color nuevo en `app.css`.** Se usan los que ya están: `--panel`, `--borde`, `--radio`, `--sombra`, `--texto`, `--texto-2`. La única regla CSS nueva de este plan (Tarea 7) es de disposición y no nombra ningún color.
- **Los tests de JavaScript miran cuerpos, no el archivo entero.** `tests/app/test_web_javascript.py` ya tiene `_cuerpo_de_funcion(js, "nombre")` y `_cuerpo_de_handler(js, "evento")`, que además borran los comentarios antes de mirar. Usarlos. Una aserción sobre el archivo entero (`assert "nucleos" in js`) pasa por cualquier `nucleos` perdido en un comentario.
- **Correr la suite entera** (`.venv/bin/pytest`) al cerrar cada tarea, no sólo los tests nuevos.
- **Nada de `Co-Authored-By` ni atribución en los mensajes de commit.**
- **Este plan corre después de los planes 1 (veta por corrida) y 2 (tiempo estimado).** Se usan sus nombres. Del plan 1: `VETA_LIBRE`/`VETA_RESPETAR` en `nesting.model.material`, `NestParams.veta`, `tolerancia_de_veta(p, material)`, `validar(p, material=None)`, `a_supply(p, material)` (que ya aplica la veta de la corrida a la placa y a los recortes), `--veta` en la CLI, `ParamsEntrada.veta`. Del plan 2 (`docs/superpowers/plans/2026-09-22-tiempo-estimado.md`): `Avance.consultas_hechas` y `Avance.consultas_previstas`; en `nesting.engine.prevision`, `estimate_sheets(parts_area, scrap_usable_areas, stock_usable_area)` y `forecast_greedy_pass(parts, orientations, sheets)`; en `packer`, `initial_forecast(parts, supply, config)`, `_restarts_for(config)`, `_usable_area(sheet, margin)`, `probe_query_seconds`, y los privados `_QueryCounter`, `_CountingOracle`, `_counting` e `_Informe` que usaba el cuerpo de `pack()`; `_recuperar_de_la_ultima_placa(..., aviso=None, prever=None)` y `_compact_last_sheet(..., aviso=None)`; `corredor.estimar_segundos(piezas, supply, config)` y `corredor.estimar(fuente, params)`; `POST /api/estimar` con cuerpo `PedidoTrabajo`; `restante_s` en `jobs.py`. **Donde el código difiera de las líneas de contexto que este plan cita**, se adapta la llamada, no la idea.
- **La cartera cuenta sus consultas con su propio envoltorio del oráculo** (`_WatchedOracle`, Tarea 5), no con el `_CountingOracle` del plan 2: tiene que cortar variantes, mirar la cancelación y contar en otros procesos, y el del plan 2 sólo suma. `pack()` pasa a delegar entero en la cartera, y `_QueryCounter`, `_CountingOracle`, `_counting` e `_Informe` quedan sin uso y se borran en la Tarea 5. `initial_forecast` se queda: la usan la cartera (previsión de arranque), `corredor.estimar_segundos` y `bench/calibrate.py`.
- **Rápido no cambia.** Después de cada tarea, una corrida con `esfuerzo="rapido"` tiene que dar el mismo layout, el mismo costo y los mismos números que antes del plan: la variante base es exactamente la pasada de hoy, y rápido evalúa sólo la base.
- **`verify()` es el árbitro y no confía en quien lo llama.** Sólo ve piezas reales, ya desarmadas. Ningún paso de este plan le pasa una compuesta.
- **Los procesos se crean con el contexto `spawn`** en todas las plataformas (`multiprocessing.get_context("spawn")`), nunca con el contexto por omisión: en Linux el por omisión es `fork` y la spec pide que las tres plataformas se comporten igual.

## Mapa de archivos

| Archivo | Responsabilidad | Tarea |
|---|---|---|
| `src/nesting/geometry/transform.py` | Gana `componer(outer, inner)`, al lado de `apply_point`. | 1 |
| `src/nesting/engine/iguales.py` | **Nuevo.** Huella, congruencia exacta, `Clase` y `Member`. | 2 |
| `src/nesting/engine/pares.py` | **Nuevo.** Clases emparejables, tipos de par por FFT, la compuesta, `Composite` y `disassemble`. | 3, 4 |
| `src/nesting/engine/cartera.py` | **Nuevo.** Variantes, cota, evaluación secuencial y en paralelo, avance, `run_portfolio`. | 5, 6 |
| `src/nesting/engine/packer.py` | `_pack_once` acepta rangos de orientación; `pack()` delega en la cartera; `EFFORT_RESTARTS` se va. | 5 |
| `src/nesting/engine/oracle.py` | `NestConfig.workers`. | 5 |
| `src/nesting/engine/raster/oracle.py` | `RasterOracleFactory`, la fábrica serializable. | 6 |
| `src/nesting/engine/workers.py` | **Nuevo.** Núcleos y memoria de la máquina, tope y valor por omisión. | 7 |
| `src/nesting/params.py` | `NestParams.nucleos`, su regla, `nucleos_efectivos`, `a_config` lo traduce. | 7 |
| `src/nesting/cli.py` | `EFFORT_BATCHES` en `--esfuerzo`, `freeze_support`, `--nucleos`, la fábrica serializable, la línea de mínimo. | 5, 6, 7, 8 |
| `src/nesting_app/corredor.py` | La fábrica serializable, el aviso de núcleos recortados, `es_minimo`. | 6, 7, 8 |
| `src/nesting_app/jobs.py` | `Resultado.es_minimo`. | 8 |
| `src/nesting_app/api.py` | Campos nuevos de `Avance`, `ParamsEntrada.nucleos`, `GET /api/sistema`, `es_minimo`. | 6, 7, 8 |
| `src/nesting_app/desktop.py` | `freeze_support` y la corrida de dos procesos del `--autotest`. | 6, 9 |
| `src/nesting_app/web/index.html` | Control de Núcleos; textos de Esfuerzo. | 7 |
| `src/nesting_app/web/app.js` | Texto de avance de la cartera, `cargarSistema`, `nucleos` en `parametros()`, línea de mínimo. | 6, 7, 8 |
| `src/nesting_app/web/app.css` | `.fila-nucleos` (disposición, sin color). | 7 |
| `src/nesting_app/web/info.js` | Globo de `nucleos`; el de `esfuerzo` reescrito. | 7 |
| `bench/run_bench.py` | La fábrica serializable; fila fija de la banqueta alta. | 6, 9 |
| `bench/calibrate.py` | Un texto que nombraba `EFFORT_RESTARTS`. | 5 |
| `bench/medir_rapido.py` | **Nuevo.** Tiempo de rápido y huella de cada layout: la vara de la fase 2. | 11 |
| `packaging/construir.sh` | Comentario: el autotest corre dos procesos. | 9 |
| `docs/superpowers/calibracion.md` | La medición de la fase 2, pase lo que pase. | 11 |
| `pyproject.toml` | Marca `lento` registrada y excluida por omisión. | 9 |
| `README.md` / `README.es.md` | Filas de Núcleos y Esfuerzo, el cartel de mínimo. | 10 |
| `bench/README.md` / `bench/README.es.md` | Los casos fijos y `-m lento`. | 10 |

## Decisiones que este plan toma y la spec no fija (o fija distinto)

Se midieron al escribir el plan, con los experimentos de la carpeta de arriba. Cada una vive además en el docstring de la constante que la implementa, para que quien la lea en el código sepa de dónde salió.

1. **Supresión de vecinos a 200 mm, no a 60.** Con 60 mm, los seis tipos de `normal` sobre el marco de la banqueta salen todos de una misma familia que se desliza de a 60 mm (`1812×450`, `1511×560`, `1571×545`, `1634×529`, `1697×513`, `1816×510`) y el apilado (`1055×879`) recién aparece séptimo: `normal` nunca podría encontrar la combinación ganadora de la tabla 1.2. Con 100 y 150 mm aparece, con 200 mm la familia colapsa a sus dos extremos. Medido (`rango2.py`): de 200 a 300 mm la lista no cambia.
2. **Un tipo congruente con otro ya aceptado no es un tipo nuevo.** El par (A, B en `r`) y el (A, B en `r⁻¹`) son la misma pieza compuesta vista desde el otro miembro; sin descartarlo, `1055×886` ocupaba dos de los seis lugares. Se reusa la congruencia de `iguales.py`.
3. **Con esas dos, sobre la banqueta** (`banq.py`, 1 mm/px, 8 posiciones, sep 8, borde 5, placa 1220×2440 libre): los seis tipos de `normal` son `1812×450`, `1511×560`, `1055×879`, `1055×886`, `2108×450`, `1055×902`, y las combinaciones de tres pares ordenadas por área total de cajas dan 2 placas en los puestos 0 a 7 (contando desde 0) y **1 placa en el puesto 8**: "caja mínima + diagonal + apilado" (`1812×450 + 1511×560 + 1055×879`, 163 s). Con `N = 12` -- el valor por omisión en la máquina de 14 núcleos donde se midió -- la única tanda de `normal` cubre los puestos 0 a 11, así que lo encuentra. Con `N ≤ 8` no, y eso es lo que la spec ya dice: con distinto `N` la garantía no aplica, más núcleos exploran más. La prueba lenta de la Tarea 9 fija `N = 12` a propósito.
4. **"Necesita dos tipos distintos" se mide sobre las combinaciones de tres pares**, igual que la tabla 1.2 de la spec: con dos pares más dos sueltas, algún tipo solo a veces alcanza, y eso no lo midió la spec ni lo pide este caso.
5. **La tanda de `lento`:** la primera es idéntica a la de `normal` (combinaciones de los primeros `TIPOS_POR_CLASE["normal"]` tipos, después perturbaciones de orden), la segunda sigue con combinaciones de los `TIPOS_POR_CLASE["lento"]` tipos que no se evaluaron, y la tercera son perturbaciones de orientación de la mejor variante encontrada hasta ahí. Así `normal` es prefijo de `lento` aunque `lento` busque diez tipos y `normal` seis.
6. **El tope de núcleos** es `min(os.cpu_count(), ⌊memoria × 0,5 / 400 MB⌋)`, y el valor por omisión `min(max(1, cpu − 2), tope)`. El ejemplo de la spec (`{"nucleos": 14, "tope": 12, "omision": 12}`) sale de una máquina con poca memoria; en la de 14 núcleos y 24 GB donde se escribió este plan da `{"nucleos": 14, "tope": 14, "omision": 12}`.
7. **"Probando combinaciones 5 de 12"** cuenta variantes **terminadas** sobre el total previsto, base incluida, y "placa mínima hasta ahora" es `sheets_used` de la mejor terminada.

---

### Task 1: `componer`, la composición de dos transformaciones

Desarmar una compuesta (Tarea 4) es componer la transformación con que se
colocó el par con la de cada miembro adentro del par. La composición vive al
lado de `apply_point`, que es la única definición de qué hace una
transformación: si viviera en `pares.py`, el día que alguien toque el orden
espejo-rotación-traslación en un lado, el otro seguiría andando y cortando
piezas en otro lugar.

**Files:**
- Modify: `src/nesting/geometry/transform.py`
- Test: `tests/geometry/test_componer.py` (nuevo)

**Interfaces:**
- Consumes: `apply_point(t, p)` y `Transform(angle_deg, mirror, dx, dy)`, que ya existen.
- Produces: `componer(outer: Transform, inner: Transform) -> Transform` en `nesting.geometry.transform`: la transformación que aplica `inner` y después `outer`. El ángulo sale normalizado a `[0, 360)`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/geometry/test_componer.py`:

```python
"""`componer(T, t)` tiene que ser, punto por punto, aplicar `t` y después `T`."""

import random

import pytest

from nesting.geometry.transform import apply_point, componer
from nesting.model.entities import Transform

ANGULOS = (0.0, 45.0, 90.0, 135.0, 180.0, 270.0, 33.3, 301.7)


def _al_azar(rng: random.Random) -> Transform:
    return Transform(
        angle_deg=rng.choice(ANGULOS),
        mirror=rng.random() < 0.5,
        dx=rng.uniform(-800.0, 800.0),
        dy=rng.uniform(-800.0, 800.0),
    )


def test_componer_es_aplicar_primero_la_de_adentro_y_despues_la_de_afuera():
    """La prueba que importa: si esto vale para doscientas transformaciones
    al azar, con y sin espejo en cada lado, la fórmula está bien. Una fórmula
    con el signo del ángulo al revés cuando `T` espeja pasa todos los casos
    sin espejo y falla la mitad de éstos."""
    rng = random.Random(20260922)
    for _ in range(200):
        exterior, interior = _al_azar(rng), _al_azar(rng)
        punto = (rng.uniform(-300.0, 300.0), rng.uniform(-300.0, 300.0))

        esperado = apply_point(exterior, apply_point(interior, punto))
        obtenido = apply_point(componer(exterior, interior), punto)

        assert obtenido == pytest.approx(esperado, abs=1e-6), (exterior, interior)


def test_la_identidad_no_cambia_nada_de_ningun_lado():
    t = Transform(90.0, True, 12.5, -3.0)
    assert componer(Transform.identity(), t) == t
    assert componer(t, Transform.identity()) == t


def test_dos_espejos_se_cancelan():
    espejo = Transform(0.0, True, 0.0, 0.0)
    assert componer(espejo, espejo).mirror is False


def test_el_angulo_queda_entre_0_y_360():
    """El DXF y el oráculo reciben este ángulo tal cual; uno de 450° o de
    -90° es correcto pero es un número que nadie espera ver."""
    tres_cuartos = Transform(270.0, False, 0.0, 0.0)
    assert componer(tres_cuartos, Transform(180.0, False, 0.0, 0.0)).angle_deg == 90.0
    espejada = Transform(0.0, True, 0.0, 0.0)
    assert componer(espejada, Transform(90.0, False, 0.0, 0.0)).angle_deg == 270.0
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/geometry/test_componer.py -v`
Expected: FAIL con `ImportError: cannot import name 'componer' from 'nesting.geometry.transform'`

- [ ] **Step 3: Implementar `componer`**

En `src/nesting/geometry/transform.py`, agregar después de `apply_points`:

```python
def componer(outer: Transform, inner: Transform) -> Transform:
    """La transformación que aplica `inner` y después `outer`.

    Es lo que hace falta para desarmar una pieza compuesta: el par se colocó
    con `outer`, y cada miembro estaba adentro del par en `inner`, así que el
    miembro termina en `componer(outer, inner)`.

    Por qué la fórmula es ésta. `apply_point` hace p -> R(a)·M·p + d, con M el
    espejo x -> -x. Encadenar las dos da

        R(A)·M_A·(R(a)·M_a·p + d_a) + d_A
      = R(A)·M_A·R(a)·M_a·p + (R(A)·M_A·d_a + d_A)

    y un espejo invierte el sentido de una rotación: M·R(a) = R(-a)·M. Así
    que el ángulo es A + a sin espejo afuera y A - a con espejo afuera, el
    espejo resultante es el "o exclusivo" de los dos, y la traslación es
    aplicar `outer` entero al punto (d_a). Verificado numéricamente en
    `tests/geometry/test_componer.py` y, antes, en el experimento de la
    spec, donde componer por las cajas en vez de por esta fórmula dejaba
    piezas superpuestas.
    """
    angle = outer.angle_deg + (-inner.angle_deg if outer.mirror else inner.angle_deg)
    dx, dy = apply_point(outer, (inner.dx, inner.dy))
    return Transform(
        angle_deg=angle % 360.0,
        mirror=outer.mirror != inner.mirror,
        dx=dx,
        dy=dy,
    )
```

- [ ] **Step 4: Correr los tests nuevos y la suite entera**

Run: `.venv/bin/pytest tests/geometry/test_componer.py -v`
Expected: PASS, 4 tests

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos.

- [ ] **Step 5: Commit**

```bash
git add src/nesting/geometry/transform.py tests/geometry/test_componer.py
git commit -m "Geometría: componer dos transformaciones, al lado de apply_point"
```

---

### Task 2: `iguales.py`, las copias de una misma forma

Dos piezas son iguales cuando una se lleva sobre la otra con una traslación
más una orientación **que la corrida permite**. Depende de la corrida a
propósito: con la veta respetada, un marco dibujado girado 90° no es igual a
otro acostado, porque llevar uno sobre el otro rompería la veta.

**Files:**
- Create: `src/nesting/engine/iguales.py`
- Test: `tests/engine/test_iguales.py` (nuevo)

**Interfaces:**
- Consumes: `placed_polygon(part, t)` de `nesting.geometry.verify`; `orientations(sheet, config)` de `nesting.engine.packer` (sólo en los tests, para armar la lista de orientaciones permitidas).
- Produces, en `nesting.engine.iguales`:
  - `Member(part_id: int, to_representative: Transform)`, frozen dataclass: `to_representative` es la `g` de la spec, la que lleva la pieza sobre la representante.
  - `Clase(representative: Part, members: tuple[Member, ...])`, frozen dataclass. El primer miembro es siempre la representante, con la identidad.
  - `fingerprint(part: Part) -> tuple`.
  - `congruence(part: Part, target: Part, orientations: Sequence[tuple[float, bool]]) -> Transform | None`: la primera `g` (en el orden de `orientations`) que lleva `part` sobre `target`, o `None`.
  - `find_classes(parts: Sequence[Part], orientations: Sequence[tuple[float, bool]]) -> list[Clase]`, en el orden en que aparece cada representante en `parts`, y los miembros de cada clase en el orden de `parts`.
  - `AREA_TOLERANCE_MM2 = 1.0`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/engine/test_iguales.py`:

```python
"""Qué piezas son copias de la misma forma, según lo que la corrida permite."""

from nesting.engine.iguales import (
    AREA_TOLERANCE_MM2,
    Clase,
    congruence,
    find_classes,
    fingerprint,
)
from nesting.engine.oracle import NestConfig
from nesting.engine.packer import orientations
from nesting.geometry.transform import apply_points
from nesting.geometry.verify import placed_polygon
from nesting.model.entities import Transform
from nesting.model.part import Part
from nesting.model.sheet import Sheet

# Una L con los brazos de distinto largo: espejarla NO es girarla. Con los
# brazos iguales, la espejada sería la girada 90° y el test del espejo
# pasaría por la razón equivocada.
ELE = ((0.0, 0.0), (300.0, 0.0), (300.0, 60.0), (60.0, 60.0), (60.0, 200.0), (0.0, 200.0))

LIBRE = Sheet(2000.0, 2000.0, grain_tolerance=180.0)
CON_VETA = Sheet(2000.0, 2000.0, grain_tolerance=5.0)
CUATRO = NestConfig(angles=(0.0, 90.0, 180.0, 270.0), mirror=True)
SIN_ESPEJO = NestConfig(angles=(0.0, 90.0, 180.0, 270.0), mirror=False)


def pieza(part_id: int, t: Transform = Transform.identity(), holes=()) -> Part:
    return Part(
        part_id,
        apply_points(t, ELE),
        tuple(apply_points(t, h) for h in holes),
        (part_id,),
    )


def copias():
    """La original, una trasladada, una girada 90° y una espejada, todas
    dibujadas en otro lugar de la hoja como las dibujaría un usuario."""
    return [
        pieza(0),
        pieza(1, Transform(0.0, False, 1500.0, 40.0)),
        pieza(2, Transform(90.0, False, 700.0, 900.0)),
        pieza(3, Transform(0.0, True, 2500.0, -300.0)),
    ]


def ids(clase: Clase) -> list[int]:
    return [m.part_id for m in clase.members]


def test_con_la_corrida_libre_las_cuatro_son_de_la_misma_clase():
    clases = find_classes(copias(), orientations(LIBRE, CUATRO))

    assert len(clases) == 1
    assert ids(clases[0]) == [0, 1, 2, 3]
    assert clases[0].representative.id == 0


def test_con_la_veta_respetada_la_girada_90_no_es_igual():
    """Llevarla sobre la otra exigiría girarla 90°, que la veta prohíbe."""
    clases = find_classes(copias(), orientations(CON_VETA, CUATRO))

    grupos = sorted(ids(c) for c in clases)
    assert [2] in grupos
    assert [0, 1, 3] in grupos


def test_sin_espejo_la_espejada_no_es_igual():
    clases = find_classes(copias(), orientations(LIBRE, SIN_ESPEJO))

    grupos = sorted(ids(c) for c in clases)
    assert [3] in grupos
    assert [0, 1, 2] in grupos


def test_g_lleva_cada_miembro_sobre_la_representante():
    """Es la propiedad que la Tarea 4 necesita: colocar a un miembro con
    `T ∘ g` lo pone exactamente donde `T` pondría a la representante."""
    piezas = copias()
    por_id = {p.id: p for p in piezas}
    clase = find_classes(piezas, orientations(LIBRE, CUATRO))[0]
    objetivo = placed_polygon(clase.representative, Transform.identity())

    for miembro in clase.members:
        movida = placed_polygon(por_id[miembro.part_id], miembro.to_representative)
        assert movida.symmetric_difference(objetivo).area < AREA_TOLERANCE_MM2


def test_la_representante_se_lleva_a_si_misma_con_la_identidad():
    clase = find_classes(copias(), orientations(LIBRE, CUATRO))[0]
    assert clase.members[0].to_representative == Transform.identity()


def test_un_agujero_de_mas_cambia_la_huella():
    """La huella descarta sin geometría exacta: la misma L con un agujero no
    puede ni llegar a compararse con la maciza."""
    agujero = ((100.0, 10.0), (140.0, 10.0), (140.0, 40.0), (100.0, 40.0))
    maciza, agujereada = pieza(0), pieza(1, holes=(agujero,))

    assert fingerprint(maciza) != fingerprint(agujereada)
    assert len(find_classes([maciza, agujereada], orientations(LIBRE, CUATRO))) == 2


def test_la_misma_huella_no_alcanza_para_ser_iguales():
    """La espejada tiene exactamente la misma huella que la original (misma
    área, mismo perímetro, mismos agujeros), y sin espejo NO es igual: el
    juez es `congruence`, no la huella."""
    original = pieza(0)
    espejada = pieza(3, Transform(0.0, True, 2500.0, -300.0))

    assert fingerprint(original) == fingerprint(espejada)
    assert congruence(espejada, original, orientations(LIBRE, SIN_ESPEJO)) is None
    assert congruence(espejada, original, orientations(LIBRE, CUATRO)) is not None


def test_piezas_distintas_quedan_en_clases_distintas_y_en_orden():
    chica = Part(9, ((0.0, 0.0), (50.0, 0.0), (50.0, 50.0), (0.0, 50.0)), (), (9,))
    clases = find_classes([pieza(0), chica, pieza(1, Transform(0.0, False, 900.0, 0.0))],
                          orientations(LIBRE, CUATRO))

    assert [ids(c) for c in clases] == [[0, 1], [9]]
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/engine/test_iguales.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'nesting.engine.iguales'`

- [ ] **Step 3: Escribir `src/nesting/engine/iguales.py`**

```python
"""Qué piezas son copias de la misma forma, y cómo se lleva cada una sobre la otra.

Un archivo real trae los seis marcos de una banqueta dibujados donde cayeron:
corridos, algunos girados, alguno espejado. Para encastrarlos de a pares
(`pares.py`) hace falta saber que son la misma pieza, y además CÓMO llevar
cada uno sobre el que se tomó de modelo -- la `g` de la spec --, porque el
par se arma con el modelo y después hay que devolverle a cada pieza real su
lugar.

"Iguales" depende de la corrida y no sólo del dibujo: dos piezas son iguales
cuando una se lleva sobre la otra con una traslación más una orientación que
la corrida PERMITE. Con la veta respetada, un marco dibujado girado 90° no es
igual a uno acostado, porque llevarlo al otro rompería la veta.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from shapely.geometry import Polygon

from nesting.geometry.verify import placed_polygon
from nesting.model.entities import Transform
from nesting.model.part import Part

AREA_TOLERANCE_MM2 = 1.0
"""Diferencia simétrica, en mm², por debajo de la cual dos piezas son iguales.

Un milímetro cuadrado es nada para una fresa (una tira de 1 mm de ancho por
1 mm de largo) y es mucho para el ruido de coma flotante de girar y
trasladar, que da del orden de 1e-9 mm².
"""

FINGERPRINT_DECIMALS = 2
"""La huella redondea a 0,01 mm (y mm²).

Es un filtro, no el juez: dos copias cuya área cayera justo a los dos lados
de un redondeo quedarían en clases distintas, y el efecto sería sólo que no
se emparejan -- nunca un acomodo equivocado. El juez es `congruence`.
"""


@dataclass(frozen=True)
class Member:
    part_id: int
    to_representative: Transform
    """La `g` de la spec: aplicada a esta pieza, la deja encima de la
    representante (diferencia simétrica menor a `AREA_TOLERANCE_MM2`)."""


@dataclass(frozen=True)
class Clase:
    """Las copias de una misma forma. El primer miembro es la representante."""

    representative: Part
    members: tuple[Member, ...]


def fingerprint(part: Part) -> tuple:
    """Área neta, perímetro, cantidad de agujeros y el área de cada uno.

    Descarta casi todo sin geometría exacta: dos piezas con huellas distintas
    no pueden ser congruentes, así que ni se comparan.
    """
    polygon = placed_polygon(part, Transform.identity())
    return (
        round(polygon.area, FINGERPRINT_DECIMALS),
        round(polygon.exterior.length, FINGERPRINT_DECIMALS),
        len(part.holes),
        tuple(sorted(round(Polygon(h).area, FINGERPRINT_DECIMALS) for h in part.holes)),
    )


def congruence(
    part: Part,
    target: Part,
    orientations: Sequence[tuple[float, bool]],
) -> Transform | None:
    """La primera `g`, en el orden de `orientations`, que lleva `part` sobre `target`.

    Para cada orientación se alinea el vértice inferior izquierdo de la caja
    de `part` ya girada con el de `target`, y se mide la diferencia
    simétrica. Alinear por la caja -- y no por el centroide -- es lo que usó
    el experimento, y alcanza: si dos piezas son congruentes bajo esa
    orientación, sus cajas coinciden.

    Por qué no basta con la caja sola: el experimento de la spec la probó
    primero, y dos marcos con la misma caja pero dibujados espejados uno del
    otro terminaban superpuestos al desarmar. La diferencia simétrica es la
    que distingue.
    """
    objetivo = placed_polygon(target, Transform.identity())
    tx0, ty0, _, _ = objetivo.bounds
    for angle, mirror in orientations:
        girada = placed_polygon(part, Transform(angle, mirror, 0.0, 0.0))
        qx0, qy0, _, _ = girada.bounds
        g = Transform(angle, mirror, tx0 - qx0, ty0 - qy0)
        movida = placed_polygon(part, g)
        if movida.symmetric_difference(objetivo).area < AREA_TOLERANCE_MM2:
            return g
    return None


def find_classes(
    parts: Sequence[Part],
    orientations: Sequence[tuple[float, bool]],
) -> list[Clase]:
    """Agrupa `parts` en clases de piezas iguales para esta corrida.

    `orientations` son las que la corrida permite -- las de
    `packer.orientations(placa, config)` --, que ya traen filtrada la veta
    y el espejo. Por eso con la veta respetada una copia girada 90° queda en
    una clase propia, y sin espejo una espejada también.
    """
    buckets: dict[tuple, list[tuple[Part, list[Member]]]] = {}
    order: list[tuple[Part, list[Member]]] = []

    for part in parts:
        bucket = buckets.setdefault(fingerprint(part), [])
        for representative, members in bucket:
            g = congruence(part, representative, orientations)
            if g is not None:
                members.append(Member(part.id, g))
                break
        else:
            entry = (part, [Member(part.id, Transform.identity())])
            bucket.append(entry)
            order.append(entry)

    return [Clase(representative, tuple(members)) for representative, members in order]
```

- [ ] **Step 4: Correr los tests nuevos y la suite entera**

Run: `.venv/bin/pytest tests/engine/test_iguales.py -v`
Expected: PASS, 8 tests

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos.

- [ ] **Step 5: Commit**

```bash
git add src/nesting/engine/iguales.py tests/engine/test_iguales.py
git commit -m "Motor: piezas iguales, con la transformación que lleva cada una a su clase"
```

---

### Task 3: `pares.py`, los tipos de encastre de dos copias

Para las formas repetidas más grandes, busca varias maneras de encastrar dos
copias. La copia A queda fija en la identidad; para cada orientación de B, la
FFT da de un golpe todos los desplazamientos donde B no toca a A. De esos se
toman los de caja más chica, con supresión de vecinos, y se confirman con
geometría exacta.

Esta tarea también construye la **forma** de la compuesta (A ∪ B ∪ puente),
porque es un criterio de aceptación del tipo: un candidato cuya unión no da un
solo polígono se descarta, y dos tipos congruentes son uno solo (Decisión 2).
La tabla de miembros y el desarmado son de la Tarea 4.

**Files:**
- Create: `src/nesting/engine/pares.py`
- Test: `tests/engine/test_pares.py` (nuevo)

**Interfaces:**
- Consumes: `Clase`, `Member`, `congruence` (Tarea 2); `MaskCache.get(part, angle, mirror, resolution, sep) -> PartMasks` con `occupied`, `clearance`, `origin`; `placed_polygon`; `transformed_bbox(part, angle, mirror)` de `nesting.engine.oracle`; `NestConfig`.
- Produces, en `nesting.engine.pares`:
  - `TIPOS_POR_CLASE: dict[str, int] = {"rapido": 0, "normal": 6, "lento": 10}`
  - `MIN_SHEET_SHARE = 0.02`, `MAX_PAIRED_CLASSES = 2`, `NEIGHBOUR_MM = 200.0`, `CANDIDATES_PER_ORIENTATION = 15`, `BRIDGE_RADIUS_MM = 1.0`, `GAP_EPS = 1e-6`.
  - `PairType(relative: Transform, box_area: float, width: float, height: float, orientation: tuple[float, bool], offset_px: tuple[int, int], outer: tuple[Point, ...], holes: tuple[tuple[Point, ...], ...])`, frozen dataclass, con `shape(part_id: int) -> Part`.
  - `pairable_classes(classes: Sequence[Clase], usable_area: float, grain_respected: bool) -> list[Clase]`
  - `b_orientations(choices: Sequence[tuple[float, bool]], grain_respected: bool) -> list[tuple[float, bool]]`
  - `union_with_bridge(a: Polygon, b: Polygon) -> tuple[tuple[Point, ...], tuple[tuple[Point, ...], ...]] | None`
  - `find_pair_types(representative: Part, b_choices: Sequence[tuple[float, bool]], fit_choices: Sequence[tuple[float, bool]], config: NestConfig, usable: tuple[float, float], how_many: int, cache: MaskCache) -> list[PairType]`, en orden de descubrimiento (caja en píxeles de menor a mayor). **Ese orden es un contrato:** los primeros `k` tipos de una búsqueda con `how_many=10` son exactamente los de una búsqueda con `how_many=k`, que es lo que hace a `normal` prefijo de `lento` (Tarea 5).

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/engine/test_pares.py`:

```python
"""Tipos de encastre de dos copias de una misma pieza."""

from pathlib import Path

import pytest
from shapely.geometry import Polygon

from nesting.engine.iguales import Clase, Member, congruence
from nesting.engine.oracle import NestConfig
from nesting.engine.packer import orientations
from nesting.engine.pares import (
    MAX_PAIRED_CLASSES,
    TIPOS_POR_CLASE,
    b_orientations,
    find_pair_types,
    pairable_classes,
    union_with_bridge,
)
from nesting.engine.raster.masks import MaskCache
from nesting.geometry.verify import placed_polygon
from nesting.model.entities import Transform
from nesting.model.part import Part
from nesting.model.sheet import Sheet

SEP = 8.0
LIBRE = Sheet(1200.0, 680.0, grain_tolerance=180.0)
CON_VETA = Sheet(1200.0, 680.0, grain_tolerance=5.0)
CONFIG = NestConfig(sep=SEP, margin=5.0, angles=(0.0, 90.0, 180.0, 270.0),
                    mirror=True, resolution=2.0)
UTIL = (1190.0, 670.0)

# La L del caso sintético de la Tarea 9: 600 x 300, brazos de 110.
ELE = ((0.0, 0.0), (600.0, 0.0), (600.0, 110.0), (110.0, 110.0), (110.0, 300.0), (0.0, 300.0))

BANQUETA = Path(__file__).resolve().parents[2] / "bench" / "files" / "banqueta-alta.ai"


def ele(part_id=0, holes=()):
    return Part(part_id, ELE, holes, (part_id,))


def tipos(sheet=LIBRE, config=CONFIG, how_many=6, part=None):
    choices = orientations(sheet, config)
    respetada = sheet.grain_tolerance < 90.0
    return find_pair_types(
        part or ele(),
        b_orientations(choices, respetada),
        choices,
        config,
        UTIL,
        how_many,
        MaskCache(),
    )


def test_todo_candidato_queda_a_una_separacion_y_menos_de_dos():
    """El tope de 2·sep es lo que garantiza que el puente no le quita lugar
    a nadie: en un hueco de menos de dos separaciones no entra ninguna pieza."""
    encontrados = tipos()
    assert encontrados, "la L tiene que tener al menos un encastre"
    a = placed_polygon(ele(), Transform.identity())
    for tipo in encontrados:
        b = placed_polygon(ele(), tipo.relative)
        assert SEP - 1e-6 <= a.distance(b) < 2 * SEP, tipo


def test_los_tipos_salen_de_menor_a_mayor_caja():
    encontrados = tipos()
    cajas = [t.box_area for t in encontrados]
    assert cajas == sorted(cajas)


def test_la_busqueda_corta_es_prefijo_de_la_larga():
    """Es el contrato que hace a normal prefijo de lento."""
    cortos = tipos(how_many=TIPOS_POR_CLASE["normal"])
    largos = tipos(how_many=TIPOS_POR_CLASE["lento"])
    assert largos[:len(cortos)] == cortos


def test_ningun_tipo_es_congruente_con_otro():
    """El par (A, B en r) y el (A, B en r⁻¹) son la misma pieza vista desde
    el otro miembro: contarlos dos veces gastaba lugares de la lista."""
    encontrados = tipos(how_many=10)
    choices = orientations(LIBRE, CONFIG)
    for i, uno in enumerate(encontrados):
        for otro in encontrados[:i]:
            assert congruence(uno.shape(1), otro.shape(2), choices) is None


def test_con_la_veta_respetada_ningun_b_queda_a_90():
    encontrados = tipos(sheet=CON_VETA)
    assert encontrados
    assert all(t.relative.angle_deg % 180.0 == 0.0 for t in encontrados)


def test_sin_espejo_ningun_b_queda_espejado():
    sin_espejo = NestConfig(sep=SEP, margin=5.0, angles=(0.0, 90.0, 180.0, 270.0),
                            mirror=False, resolution=2.0)
    encontrados = tipos(config=sin_espejo)
    assert encontrados
    assert not any(t.relative.mirror for t in encontrados)


def test_todo_par_entra_en_el_area_util_en_alguna_orientacion():
    for tipo in tipos():
        w, h = sorted((tipo.width, tipo.height))
        assert w <= min(UTIL) and h <= max(UTIL), tipo


def test_la_compuesta_es_un_solo_poligono_y_conserva_los_agujeros():
    agujero = ((300.0, 20.0), (400.0, 20.0), (400.0, 80.0), (300.0, 80.0))
    con_agujero = ele(holes=(agujero,))
    tipo = tipos(part=con_agujero)[0]

    forma = tipo.shape(99)
    poligono = Polygon(forma.outer, forma.holes)
    assert poligono.is_valid
    assert len(forma.holes) == 2, "el agujero de A y el de B"
    a = placed_polygon(con_agujero, Transform.identity())
    b = placed_polygon(con_agujero, tipo.relative)
    # La compuesta es A, B y un puente chico: el área de más es la del puente.
    assert 0.0 < poligono.area - (a.area + b.area) < 4 * SEP * 2


def test_el_puente_une_dos_poligonos_que_no_se_tocan():
    a = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    b = Polygon([(110, 0), (210, 0), (210, 100), (110, 100)])
    unida = union_with_bridge(a, b)
    assert unida is not None
    outer, holes = unida
    assert Polygon(outer, holes).area > a.area + b.area
    assert holes == ()


def test_solo_se_emparejan_las_clases_repetidas_y_grandes_hasta_dos():
    grande = Part(0, ((0, 0), (500, 0), (500, 400), (0, 400)), (), (0,))
    mediana = Part(2, ((0, 0), (400, 0), (400, 300), (0, 300)), (), (2,))
    otra = Part(4, ((0, 0), (300, 0), (300, 300), (0, 300)), (), (4,))
    listón = Part(6, ((0, 0), (300, 0), (300, 20), (0, 20)), (), (6,))
    sola = Part(8, ((0, 0), (600, 0), (600, 500), (0, 500)), (), (8,))
    identidad = Transform.identity()

    def clase(part, n):
        return Clase(part, tuple(Member(part.id + k, identidad) for k in range(n)))

    clases = [clase(otra, 2), clase(listón, 6), clase(sola, 1),
              clase(mediana, 3), clase(grande, 2)]
    util = 1190.0 * 2430.0

    elegidas = pairable_classes(clases, util, grain_respected=False)

    assert len(elegidas) == MAX_PAIRED_CLASSES
    assert [c.representative.id for c in elegidas] == [0, 2]


def test_con_la_veta_respetada_no_se_empareja_una_clase_con_miembros_girados():
    """Si una copia llega a la representante girada 3°, componerla con un
    par girado otros 3° la deja a 6°, fuera de una tolerancia de 5. Pasa sólo
    con ángulos personalizados, pero pasa, y nadie más lo revisa: `verify`
    no mira la veta."""
    pieza = Part(0, ((0, 0), (500, 0), (500, 400), (0, 400)), (), (0,))
    torcida = Clase(pieza, (Member(0, Transform.identity()),
                            Member(1, Transform(3.0, False, 0.0, 0.0))))
    assert pairable_classes([torcida], 1190.0 * 2430.0, grain_respected=True) == []
    assert pairable_classes([torcida], 1190.0 * 2430.0, grain_respected=False) == [torcida]


@pytest.mark.skipif(
    not BANQUETA.exists(),
    reason=f"falta {BANQUETA}: es un archivo de diseño del usuario y no se "
           "versiona (ver .gitignore). Copiá 'BANQUETA ALTA NESTING.ai' ahí.",
)
def test_sobre_el_marco_de_la_banqueta_aparecen_el_diagonal_y_el_apilado():
    from nesting.io.ai_reader import read_ai
    from nesting.pipeline import prepare_parts

    piezas, _, _ = prepare_parts(read_ai(BANQUETA))
    marco = max(piezas, key=lambda p: p.area)
    config = NestConfig(sep=8.0, margin=5.0, angles=tuple(i * 45.0 for i in range(8)),
                        mirror=True, resolution=1.0)
    placa = Sheet(1220.0, 2440.0, grain_tolerance=180.0)
    choices = orientations(placa, config)
    encontrados = find_pair_types(marco, choices, choices, config, (1210.0, 2430.0),
                                  TIPOS_POR_CLASE["normal"], MaskCache())

    def hay(w, h):
        return any(
            sorted((t.width, t.height)) == pytest.approx(sorted((w, h)), abs=5.0)
            for t in encontrados
        )

    assert hay(1511.0, 560.0), [(round(t.width), round(t.height)) for t in encontrados]
    assert hay(1055.0, 879.0), [(round(t.width), round(t.height)) for t in encontrados]
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/engine/test_pares.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'nesting.engine.pares'`

- [ ] **Step 3: Escribir `src/nesting/engine/pares.py`**

```python
"""Pares encastrados: dos copias de una pieza fundidas en una sola.

El motor de siempre ubica pieza por pieza y nunca vuelve atrás: cuando pone
el primer marco no sabe que conviene dejarle lugar al segundo en una
posición exacta. Acá se busca esa posición antes de acomodar nada -- todas
las posiciones relativas de golpe, por FFT --, y el par se le ofrece al
motor como una pieza más. El oráculo, las máscaras y el empacador no se
enteran de nada.

Spec: docs/superpowers/specs/2026-09-22-pares-y-cartera-design.es.md, sección 3.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.signal import fftconvolve
from shapely.geometry import LineString, Polygon
from shapely.ops import nearest_points, unary_union

from nesting.engine.iguales import Clase, congruence
from nesting.engine.oracle import NestConfig, transformed_bbox
from nesting.engine.raster.masks import MaskCache
from nesting.geometry.verify import placed_polygon
from nesting.model.entities import Point, Transform
from nesting.model.part import Part

TIPOS_POR_CLASE: dict[str, int] = {"rapido": 0, "normal": 6, "lento": 10}
"""Cuántos tipos de par se guardan por clase, según el esfuerzo."""

MIN_SHEET_SHARE = 0.02
"""Una clase se empareja si su pieza ocupa al menos el 2% del área útil.

Un listón emparejado casi no gana lugar y sí multiplica combinaciones.
"""

MAX_PAIRED_CLASSES = 2
"""Cuántas clases se emparejan como máximo, las de pieza más grande primero."""

NEIGHBOUR_MM = 200.0
"""Dos candidatos de la misma orientación a menos de esto son el mismo encastre.

LA SPEC DICE 60, Y 60 NO ALCANZA. Sin supresión, los doscientos mejores
candidatos son todos el mismo encastre corrido un píxel (lo mostró el
experimento de la spec). Con 60 mm, sobre el marco de la banqueta, los seis
tipos de `normal` salen todos de UNA familia que se desliza de a 60 mm:
1812x450, 1511x560, 1571x545, 1634x529, 1697x513, 1816x510; el apilado
(1055x879) recién aparece séptimo, así que `normal` nunca podía probar la
combinación que gana. Medido al escribir el plan (`rango2.py`): con 100 y
150 mm el apilado entra en los seis; con 200 mm la familia colapsa a sus
dos extremos (1812x450 y 1511x560) y la lista no cambia hasta 300 mm.
"""

CANDIDATES_PER_ORIENTATION = 15
"""Cuántos candidatos, ya suprimidos, se guardan por orientación de B."""

BRIDGE_RADIUS_MM = 1.0
"""Medio ancho del puente que une A con B, con puntas redondas.

Con puntas planas el puente no llegaba a fundirse con los dos polígonos en
el experimento, y la unión salía en dos pedazos. El cierre morfológico
(dilatar y erosionar) tampoco sirve: dos marcos que se tocan por una esquina
se vuelven a separar al erosionar.
"""

GAP_EPS = 1e-6
"""La misma holgura numérica que usa `verify`, para que un par a exactamente
`sep` no se descarte por ruido."""


@dataclass(frozen=True)
class PairType:
    """Una manera de encastrar dos copias: B relativa a A, con A en la identidad."""

    relative: Transform
    """Dónde va la copia B, en las coordenadas de la representante."""

    box_area: float
    """Área de la caja del par en mm², medida sobre las cajas en píxeles.

    Es la clave con la que se ordenan los tipos y las combinaciones. Sale de
    los píxeles y no de la geometría exacta porque así se calcula para todos
    los desplazamientos de una vez, sin rasterizar nada más; y como los tipos
    se aceptan en ese mismo orden, la lista queda ordenada por esta clave
    por construcción.
    """

    width: float
    """Ancho exacto de la caja de A ∪ B, en mm."""

    height: float
    orientation: tuple[float, bool]
    """La orientación de B con que se encontró (para la supresión de vecinos)."""

    offset_px: tuple[int, int]
    outer: tuple[Point, ...]
    """El contorno de A ∪ B ∪ puente, en las coordenadas de la representante."""

    holes: tuple[tuple[Point, ...], ...]
    """Los agujeros de A y de B, que siguen disponibles para piezas chicas."""

    def shape(self, part_id: int) -> Part:
        """La compuesta como una `Part` común, sin entidades de dibujo."""
        return Part(part_id, self.outer, self.holes, ())


def pairable_classes(
    classes: Sequence[Clase],
    usable_area: float,
    grain_respected: bool,
) -> list[Clase]:
    """Las clases que vale la pena emparejar, de pieza más grande a más chica.

    Con la veta respetada, una clase cuyos miembros llegan a la
    representante con un ángulo que no es múltiplo de 180 no se empareja: el
    ángulo final de un miembro es la suma del de la compuesta, el del par y
    el de `g`, y dos desvíos permitidos (3° + 3°) pueden sumar uno que no lo
    es. `verify` no mira la veta, así que nadie más lo atajaría.
    """
    elegibles = [
        c for c in classes
        if len(c.members) >= 2
        and c.representative.area >= MIN_SHEET_SHARE * usable_area
        and not (
            grain_respected
            and any(m.to_representative.angle_deg % 180.0 != 0.0 for m in c.members)
        )
    ]
    elegibles.sort(key=lambda c: c.representative.area, reverse=True)
    return elegibles[:MAX_PAIRED_CLASSES]


def b_orientations(
    choices: Sequence[tuple[float, bool]],
    grain_respected: bool,
) -> list[tuple[float, bool]]:
    """Las orientaciones de B relativas a A.

    Con la veta respetada, sólo 0° y 180° (y sus espejadas, si hay espejo):
    así la composición de la orientación del par (que ya filtra la veta de
    cada placa) con la de B sigue en el eje. Vale igual para un recorte de
    veta cruzada: 90° más 0° o 180° sigue en su eje.
    """
    if not grain_respected:
        return list(choices)
    return [(a, m) for a, m in choices if a % 180.0 == 0.0]


def union_with_bridge(
    a: Polygon, b: Polygon
) -> tuple[tuple[Point, ...], tuple[tuple[Point, ...], ...]] | None:
    """A ∪ B ∪ el puente entre sus dos puntos más cercanos, o None si no da
    un solo polígono.

    Los puntos más cercanos se buscan entre los polígonos y no entre sus
    contornos exteriores: si B cae adentro de un agujero de A, el punto de A
    más cercano está en el borde del agujero, y un puente al contorno
    exterior cruzaría el hueco entero.
    """
    qa, qb = nearest_points(a, b)
    bridge = LineString([qa, qb]).buffer(BRIDGE_RADIUS_MM)
    union = unary_union([a, b, bridge]).buffer(0)
    if union.geom_type != "Polygon":
        return None
    outer = tuple(union.exterior.coords)[:-1]
    holes = tuple(tuple(ring.coords)[:-1] for ring in union.interiors)
    return outer, holes


def _pixel_box(mask: np.ndarray) -> tuple[int, int, int, int]:
    """(col0, fila0, col1, fila1) de lo ocupado, inclusivo."""
    filas = np.nonzero(mask.any(axis=1))[0]
    columnas = np.nonzero(mask.any(axis=0))[0]
    return int(columnas[0]), int(filas[0]), int(columnas[-1]), int(filas[-1])


def _fits(part: Part, fit_choices: Sequence[tuple[float, bool]],
          usable: tuple[float, float]) -> bool:
    usable_w, usable_h = usable
    for angle, mirror in fit_choices:
        x0, y0, x1, y1 = transformed_bbox(part, angle, mirror)
        if x1 - x0 <= usable_w + GAP_EPS and y1 - y0 <= usable_h + GAP_EPS:
            return True
    return False


def find_pair_types(
    representative: Part,
    b_choices: Sequence[tuple[float, bool]],
    fit_choices: Sequence[tuple[float, bool]],
    config: NestConfig,
    usable: tuple[float, float],
    how_many: int,
    cache: MaskCache,
) -> list[PairType]:
    """Hasta `how_many` tipos de par de `representative`, de menor a mayor caja.

    `b_choices` son las orientaciones de B relativas a A (ver
    `b_orientations`); `fit_choices`, las que la placa del Material permite
    para el par entero, contra las que se mira que entre en `usable` y que
    un tipo nuevo no sea congruente con uno ya aceptado.

    Las máscaras salen del mismo `MaskCache` y con la misma resolución y
    separación que usa la corrida: `A.occupied` correlacionado con
    `B.clearance` da cero exactamente donde B no toca el halo de A.
    """
    if how_many <= 0 or config.sep <= 0.0:
        # Sin separación no hay hueco de "menos de dos separaciones" donde
        # esconder el puente, y el puente le robaría lugar a otra pieza.
        return []

    res, sep = config.resolution, config.sep
    a_masks = cache.get(representative, 0.0, False, res, sep)
    a_occupied = a_masks.occupied.astype(np.float32)
    a_box = _pixel_box(a_masks.occupied)
    vecino_px = NEIGHBOUR_MM / res

    candidatos: list[tuple[float, float, bool, int, int]] = []
    for angle, mirror in b_choices:
        b_masks = cache.get(representative, angle, mirror, res, sep)
        clearance = b_masks.clearance.astype(np.float32)
        # overlap[k] = suma de A.occupied(x) * B.clearance(x - k): cero
        # donde B, corrida k píxeles, no toca a A.
        overlap = fftconvolve(a_occupied, clearance[::-1, ::-1], mode="full")
        filas, columnas = np.nonzero(overlap < 0.5)
        oy = filas - (clearance.shape[0] - 1)
        ox = columnas - (clearance.shape[1] - 1)

        b_box = _pixel_box(b_masks.occupied)
        x0 = np.minimum(a_box[0], b_box[0] + ox)
        y0 = np.minimum(a_box[1], b_box[1] + oy)
        x1 = np.maximum(a_box[2], b_box[2] + ox)
        y1 = np.maximum(a_box[3], b_box[3] + oy)
        area = (x1 - x0) * (y1 - y0)

        # Supresión de vecinos ANTES de truncar: sin esto, los quince
        # mejores de cada orientación son el mismo encastre corrido de a un
        # píxel, y los demás encastres no llegan a la lista.
        tomados: list[tuple[int, int]] = []
        for k in np.argsort(area, kind="stable"):
            u, v = int(ox[k]), int(oy[k])
            if any(abs(u - tu) < vecino_px and abs(v - tv) < vecino_px for tu, tv in tomados):
                continue
            tomados.append((u, v))
            candidatos.append((float(area[k]) * res * res, angle, mirror, u, v))
            if len(tomados) >= CANDIDATES_PER_ORIENTATION:
                break

    candidatos.sort()

    a_polygon = placed_polygon(representative, Transform.identity())
    aceptados: list[PairType] = []
    for box_area, angle, mirror, u, v in candidatos:
        if any(
            t.orientation == (angle, mirror)
            and abs(t.offset_px[0] - u) < vecino_px
            and abs(t.offset_px[1] - v) < vecino_px
            for t in aceptados
        ):
            continue

        b_masks = cache.get(representative, angle, mirror, res, sep)
        # El píxel [0, 0] de B cae en el de A corrido (u, v) píxeles.
        relative = Transform(
            angle, mirror,
            a_masks.origin[0] + u * res - b_masks.origin[0],
            a_masks.origin[1] + v * res - b_masks.origin[1],
        )
        b_polygon = placed_polygon(representative, relative)
        gap = a_polygon.distance(b_polygon)
        if not (sep - GAP_EPS <= gap < 2 * sep):
            continue

        unida = union_with_bridge(a_polygon, b_polygon)
        if unida is None:
            continue
        outer, holes = unida
        forma = Part(-1, outer, holes, ())
        if not _fits(forma, fit_choices, usable):
            continue
        if any(congruence(forma, t.shape(-2), fit_choices) is not None for t in aceptados):
            continue

        bx0, by0, bx1, by1 = a_polygon.union(b_polygon).bounds
        aceptados.append(
            PairType(
                relative=relative,
                box_area=box_area,
                width=bx1 - bx0,
                height=by1 - by0,
                orientation=(angle, mirror),
                offset_px=(u, v),
                outer=outer,
                holes=holes,
            )
        )
        if len(aceptados) >= how_many:
            break

    return aceptados
```

- [ ] **Step 4: Correr los tests nuevos y la suite entera**

Run: `.venv/bin/pytest tests/engine/test_pares.py -v`
Expected: PASS, 12 tests (el de la banqueta sale `SKIPPED` con el motivo si falta el archivo; con el archivo, tarda unos 4 s).

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos.

- [ ] **Step 5: Commit**

```bash
git add src/nesting/engine/pares.py tests/engine/test_pares.py
git commit -m "Motor: tipos de par por FFT, con supresión de vecinos y la forma compuesta"
```

---

### Task 4: La compuesta con sus miembros, y desarmarla

Un par se acomoda como una `Part` más. Después, cada colocación de una
compuesta con transformación `T` se convierte en una colocación por miembro
con `componer(T, t)`. Se desarma **antes** de verificar: el verificador de
siempre revisa las piezas reales.

**Files:**
- Modify: `src/nesting/engine/pares.py`
- Test: `tests/engine/test_desarmar.py` (nuevo)

**Interfaces:**
- Consumes: `componer` (Tarea 1); `Member`, `find_classes` (Tarea 2); `PairType`, `find_pair_types`, `b_orientations` (Tarea 3); `PackResult`, `_pack_once`, `orientations` de `nesting.engine.packer`; `verify`.
- Produces, en `nesting.engine.pares`:
  - `Composite(part: Part, members: tuple[tuple[int, Transform], ...])`, frozen dataclass. `members[i] = (part_id, t)`: `t` lleva la pieza real `part_id` a su lugar adentro del par, en coordenadas de la compuesta.
  - `make_composite(part_id: int, pair_type: PairType, first: Member, second: Member) -> Composite`: A es `first`, con `t = g_A`; B es `second`, con `t = componer(pair_type.relative, g_B)`.
  - `disassemble(result: PackResult, composites: Sequence[Composite], parts: Sequence[Part]) -> PackResult`: sin compuestas devuelve `result` tal cual (el mismo objeto); con compuestas, un `PackResult` nuevo con las mismas placas, las colocaciones por miembro en el lugar de la compuesta, y el aprovechamiento recalculado con las áreas **reales** (sin el puente).

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/engine/test_desarmar.py`:

```python
"""Una compuesta se acomoda como una pieza y se desarma en sus dos miembros."""

import pytest
from shapely.ops import unary_union

from nesting.engine.iguales import find_classes
from nesting.engine.oracle import NestConfig
from nesting.engine.packer import PackResult, _pack_once, orientations
from nesting.engine.pares import (
    b_orientations,
    disassemble,
    find_pair_types,
    make_composite,
)
from nesting.engine.raster.masks import MaskCache
from nesting.engine.raster.oracle import RasterOracle
from nesting.geometry.transform import apply_points
from nesting.geometry.verify import placed_polygon, verify
from nesting.model.entities import Transform
from nesting.model.part import Part, Placement
from nesting.model.sheet import Sheet, SheetSupply

ELE = ((0.0, 0.0), (600.0, 0.0), (600.0, 110.0), (110.0, 110.0), (110.0, 300.0), (0.0, 300.0))
PLACA = Sheet(1400.0, 1400.0, grain_tolerance=180.0)
PLAN = SheetSupply(stock=PLACA, material_name="prueba")


def config(espejo):
    return NestConfig(sep=8.0, margin=5.0, angles=(0.0, 90.0, 180.0, 270.0),
                      mirror=espejo, resolution=2.0, effort="rapido")


def dibujada(part_id, t):
    """Una copia de la L tal como la dibujaría un usuario: en otro lugar,
    y girada o espejada."""
    return Part(part_id, apply_points(t, ELE), (), (part_id,))


def armar(espejo, segunda):
    cfg = config(espejo)
    piezas = [dibujada(0, Transform.identity()), dibujada(1, segunda)]
    choices = orientations(PLACA, cfg)
    clase = find_classes(piezas, choices)[0]
    assert len(clase.members) == 2, "las dos copias tienen que ser de la misma clase"
    tipo = find_pair_types(clase.representative, b_orientations(choices, False), choices,
                           cfg, (1390.0, 1390.0), 1, MaskCache())[0]
    compuesta = make_composite(100, tipo, clase.members[0], clase.members[1])
    return cfg, piezas, compuesta


@pytest.mark.parametrize("espejo, segunda", [
    (True, Transform(90.0, True, 2000.0, 500.0)),
    (False, Transform(270.0, False, -900.0, 1200.0)),
])
def test_las_piezas_reales_desarmadas_verifican(espejo, segunda):
    """La prueba que importa: el árbitro, mirando sólo las piezas reales,
    no encuentra nada. Con espejo la segunda copia está dibujada espejada
    y girada; sin espejo, sólo girada."""
    cfg, piezas, compuesta = armar(espejo, segunda)
    cache = MaskCache()
    acomodado = _pack_once([compuesta.part], PLAN, cfg, lambda: RasterOracle(cache=cache))

    real = disassemble(acomodado, [compuesta], piezas)

    assert sorted(p.part_id for p in real.placements) == [0, 1]
    assert verify(piezas, real.placements, real.sheets, sep=cfg.sep, margin=cfg.margin) == []


def test_los_miembros_ocupan_la_compuesta_salvo_el_puente():
    cfg, piezas, compuesta = armar(True, Transform(180.0, True, 50.0, 3000.0))
    colocada = Transform(90.0, True, 700.0, 20.0)
    resultado = PackResult(placements=[Placement(100, 0, colocada)], sheets=[PLACA])

    real = disassemble(resultado, [compuesta], piezas)

    por_id = {p.id: p for p in piezas}
    miembros = unary_union([placed_polygon(por_id[p.part_id], p.transform)
                            for p in real.placements])
    par = placed_polygon(compuesta.part, colocada)
    # El puente mide a lo sumo 2·sep de largo y 2 mm de ancho, con puntas
    # redondas: menos de 40 mm². Un miembro mal compuesto erra por miles.
    assert par.symmetric_difference(miembros).area < 40.0


def test_el_aprovechamiento_se_recalcula_sin_el_puente():
    cfg, piezas, compuesta = armar(True, Transform(0.0, False, 900.0, 0.0))
    resultado = PackResult(placements=[Placement(100, 0, Transform(0.0, False, 10.0, 10.0))],
                           sheets=[PLACA], utilization=[0.99], total_utilization=0.99)

    real = disassemble(resultado, [compuesta], piezas)

    esperado = sum(p.area for p in piezas) / PLACA.area
    assert real.utilization == [pytest.approx(esperado)]
    assert real.total_utilization == pytest.approx(esperado)


def test_sin_compuestas_se_devuelve_el_mismo_resultado():
    """La base no tiene pares: desarmarla no puede tocar un solo número."""
    resultado = PackResult(placements=[Placement(0, 0, Transform.identity())], sheets=[PLACA])
    assert disassemble(resultado, [], [dibujada(0, Transform.identity())]) is resultado


def test_las_sueltas_quedan_donde_estaban_y_en_su_orden():
    cfg, piezas, compuesta = armar(True, Transform(0.0, False, 900.0, 0.0))
    suelta = Part(7, ((0.0, 0.0), (50.0, 0.0), (50.0, 50.0), (0.0, 50.0)), (), (7,))
    antes = Placement(7, 0, Transform(0.0, False, 1200.0, 1200.0))
    resultado = PackResult(
        placements=[antes, Placement(100, 0, Transform.identity())], sheets=[PLACA],
    )

    real = disassemble(resultado, [compuesta], piezas + [suelta])

    assert real.placements[0] == antes
    assert [p.part_id for p in real.placements[1:]] == [0, 1]
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/engine/test_desarmar.py -v`
Expected: FAIL con `ImportError: cannot import name 'disassemble' from 'nesting.engine.pares'`

- [ ] **Step 3: Agregar `Composite`, `make_composite` y `disassemble` a `pares.py`**

Agregar a los imports de `src/nesting/engine/pares.py`:

```python
from nesting.engine.iguales import Member
from nesting.engine.packer import PackResult
from nesting.geometry.transform import componer
from nesting.model.part import Placement
```

(`packer` no importa `pares` a nivel de módulo, así que no hay ciclo: la
única referencia de `packer` a la cartera, en la Tarea 5, es un import
adentro de `pack()`.)

Agregar al final del archivo:

```python
@dataclass(frozen=True)
class Composite:
    """Un par ya armado con dos piezas reales, listo para acomodarse."""

    part: Part
    """La forma del par (`PairType.shape`), con un id que no usa ninguna pieza real."""

    members: tuple[tuple[int, Transform], ...]
    """`(part_id, t)` por miembro: `t` lleva la pieza real a su lugar adentro
    del par, en las coordenadas de la compuesta."""


def make_composite(part_id: int, pair_type: PairType, first: Member, second: Member) -> Composite:
    """El par `pair_type` hecho con las piezas reales `first` (como A) y `second` (como B).

    El par se construyó con la representante: A en la identidad y B en
    `relative`. Una pieza real llega a la representante con su `g`, así que
    A termina en `g_A` y B en `relative ∘ g_B`.
    """
    return Composite(
        part=pair_type.shape(part_id),
        members=(
            (first.part_id, first.to_representative),
            (second.part_id, componer(pair_type.relative, second.to_representative)),
        ),
    )


def disassemble(
    result: PackResult,
    composites: Sequence[Composite],
    parts: Sequence[Part],
) -> PackResult:
    """Cambia cada compuesta colocada por sus dos miembros, con `T ∘ t`.

    Corre ANTES de verificar y antes de escribir nada: una compuesta nunca
    llega a `verify`, al DXF ni a la previsualización. `parts` son las
    piezas reales; el aprovechamiento se recalcula con ellas, porque el
    área de la compuesta incluye el puente, que no es material de nadie.
    """
    by_composite = {c.part.id: c for c in composites}
    if not by_composite:
        return result

    placements: list[Placement] = []
    for placement in result.placements:
        composite = by_composite.get(placement.part_id)
        if composite is None:
            placements.append(placement)
            continue
        for member_id, inner in composite.members:
            placements.append(
                Placement(member_id, placement.sheet, componer(placement.transform, inner))
            )

    # La misma cuenta que `_pack_once`: áreas por placa y UNA división al
    # final, para que el total coincida con el de una corrida sin pares.
    by_id = {p.id: p for p in parts}
    areas = [0.0] * len(result.sheets)
    for placement in placements:
        areas[placement.sheet] += by_id[placement.part_id].area
    area_total = sum(sheet.area for sheet in result.sheets)
    return PackResult(
        placements=placements,
        sheets=list(result.sheets),
        utilization=[area / sheet.area for area, sheet in zip(areas, result.sheets)],
        total_utilization=sum(areas) / area_total if area_total else 0.0,
        seconds=result.seconds,
    )
```

- [ ] **Step 4: Correr los tests nuevos y la suite entera**

Run: `.venv/bin/pytest tests/engine/test_desarmar.py -v`
Expected: PASS, 6 tests

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos.

- [ ] **Step 5: Commit**

```bash
git add src/nesting/engine/pares.py tests/engine/test_desarmar.py
git commit -m "Motor: la compuesta con sus miembros, y desarmarla antes de verificar"
```

---

### Task 5: La cartera, en un solo proceso

`pack()` pasa a delegar en `cartera.run_portfolio`. Esta tarea arma todo lo
que la cartera decide -- qué variantes, en qué orden, cuál gana, cuándo no se
busca, cómo se cuenta el avance -- y las evalúa **una detrás de otra** en el
proceso principal. `NestConfig.workers` ya existe y ya es el tamaño `N` de la
tanda, pero todavía no crea procesos: eso es la Tarea 6, que sólo cambia
*dónde* corre cada variante, no *cuáles*.

Nadie le pasa `workers` al motor todavía (la CLI y la interfaz lo ganan en la
Tarea 7), así que en la aplicación `N = 1` hasta entonces.

**Files:**
- Create: `src/nesting/engine/cartera.py`
- Modify: `src/nesting/engine/packer.py` (`Avance`, `_pack_once`, `_best_over_orientations`, `pack`, se va `EFFORT_RESTARTS`)
- Modify: `src/nesting/engine/oracle.py` (`NestConfig.workers`)
- Modify: `src/nesting/cli.py:10,398` y `bench/calibrate.py:275` (`EFFORT_RESTARTS` -> `EFFORT_BATCHES`)
- Modify: `tests/engine/test_effort.py`, `tests/engine/test_progreso.py`, `tests/engine/test_consultas.py` (del plan 2), `tests/app/test_api_trabajos.py:186`
- Test: `tests/engine/test_packer.py`, `tests/engine/test_cartera.py` (nuevo)

**Interfaces:**
- Consumes: `find_classes` (Tarea 2); `pairable_classes`, `b_orientations`, `find_pair_types`, `TIPOS_POR_CLASE` (Tarea 3); `make_composite`, `disassemble`, `Composite` (Tarea 4); del plan 2, `initial_forecast(parts, supply, config)` (la previsión de arranque) y `_recuperar_de_la_ultima_placa` / `_compact_last_sheet` llamadas con sus parámetros opcionales por omisión.
- Produces:
  - `NestConfig.workers: int = 1` en `nesting.engine.oracle`.
  - `Avance.combinaciones: int = 0`, `Avance.combinaciones_hechas: int = 0`, `Avance.placa_minima: int = 0` (después de los campos del plan 2).
  - `_pack_once(order, supply, config, oracle_factory, aviso=None, orientation_ranks: Mapping[int, int] | None = None)` y `_best_over_orientations(oracle, part, choices, rank: int = 0)` en `packer`.
  - En `nesting.engine.cartera`: `EFFORT_BATCHES: dict[str, int]`, `QUERY_REPORT_EVERY = 25`, `cota_minima(parts, supply, margin) -> int | None`, `planned_variants(effort, workers) -> int`, `smallest_combinations(type_areas, members, loose_area, include_empty) -> Iterator[tuple[float, tuple[int, ...]]]`, `Variant`, `Outcome`, `PortfolioResult`, `VariantSource(parts, supply, config)` con `.base()` y `.batch(number, size, best)`, `_Watch`, `evaluate(variant, parts, supply, config, factory, watch, aviso=None) -> Outcome | None`, `run_portfolio(parts, supply, config, oracle_factory, progreso=None) -> PortfolioResult`, y la clase `_Evaluator` (secuencial acá; la Tarea 6 le agrega el pool).
  - `pack(...)` con la misma firma, devolviendo `run_portfolio(...).result`.

- [ ] **Step 1: Escribir los tests de los rangos de orientación, que fallan**

Agregar al final de `tests/engine/test_packer.py`:

```python
from nesting.engine.packer import _best_over_orientations


class _PuntajesFijos:
    """Un oráculo que puntúa cada ángulo con un número fijo y no ubica nada."""

    def __init__(self, puntajes):
        self.puntajes = puntajes

    def reset(self, sheet_w, sheet_h, config):
        pass

    def best_placement(self, part, angle, mirror):
        puntaje = self.puntajes.get(angle)
        return None if puntaje is None else (angle, 0.0, puntaje)

    def place(self, part, angle, mirror, x, y):
        pass


ANGULOS = [(0.0, False), (90.0, False), (180.0, False), (270.0, False)]


def test_el_rango_cero_es_la_mejor_orientacion_de_siempre():
    oraculo = _PuntajesFijos({0.0: 1.0, 90.0: 3.0, 180.0: 2.0})
    assert _best_over_orientations(oraculo, rect_part(0, 10, 10), ANGULOS)[0] == 90.0
    assert _best_over_orientations(oraculo, rect_part(0, 10, 10), ANGULOS, 0)[0] == 90.0


def test_el_rango_uno_es_la_segunda_mejor():
    oraculo = _PuntajesFijos({0.0: 1.0, 90.0: 3.0, 180.0: 2.0})
    assert _best_over_orientations(oraculo, rect_part(0, 10, 10), ANGULOS, 1)[0] == 180.0


def test_un_rango_mayor_que_las_opciones_se_queda_con_la_peor_que_entra():
    """Una pieza que entra en dos orientaciones no puede quedar sin lugar
    porque la perturbación pidió la tercera."""
    oraculo = _PuntajesFijos({0.0: 1.0, 90.0: 3.0})
    assert _best_over_orientations(oraculo, rect_part(0, 10, 10), ANGULOS, 2)[0] == 0.0


def test_pack_once_aplica_el_rango_solo_a_las_piezas_que_lo_piden():
    parts = [rect_part(0, 300.0, 100.0), rect_part(1, 300.0, 100.0)]
    sin = _pack_once(parts, PLAN_LIBRE, CONFIG, ShelfOracle)
    con = _pack_once(parts, PLAN_LIBRE, CONFIG, ShelfOracle, orientation_ranks={1: 1})

    angulo = {p.part_id: p.transform.angle_deg for p in con.placements}
    angulo_sin = {p.part_id: p.transform.angle_deg for p in sin.placements}
    assert angulo[0] == angulo_sin[0]
    assert angulo[1] != angulo_sin[1]
```

y agregar `_pack_once` al import de `nesting.engine.packer` de arriba del archivo.

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/engine/test_packer.py -k "rango" -v`
Expected: FAIL con `TypeError: _best_over_orientations() takes 3 positional arguments but 4 were given` y `TypeError: _pack_once() got an unexpected keyword argument 'orientation_ranks'`

- [ ] **Step 3: Implementar los rangos en `packer.py`**

Agregar `Mapping` al import de `collections.abc`:

```python
from collections.abc import Callable, Mapping, Sequence
```

Cambiar la firma de `_pack_once` (el cuerpo queda igual salvo una línea):

```python
def _pack_once(
    order: Sequence[Part],
    supply: SheetSupply,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    aviso: Callable[[int, int], None] | None = None,
    orientation_ranks: Mapping[int, int] | None = None,
) -> PackResult:
```

agregar al docstring:

```python
    `orientation_ranks`, si se pasa, dice para algunas piezas (por id) qué
    orientación tomar en vez de la mejor: 0 es la mejor, 1 la segunda, y
    así. Es la perturbación de orientaciones de `lento` (ver
    `cartera.VariantSource`); sin pasarlo, todo es exactamente como antes.
```

y en el bucle de piezas reemplazar

```python
            spot = _best_over_orientations(oracle, part, choices)
```

por

```python
            rank = orientation_ranks.get(part.id, 0) if orientation_ranks else 0
            spot = _best_over_orientations(oracle, part, choices, rank)
```

Reemplazar `_best_over_orientations` entero:

```python
def _best_over_orientations(
    oracle: Oracle,
    part: Part,
    choices: Sequence[tuple[float, bool]],
    rank: int = 0,
) -> tuple[float, bool, float, float] | None:
    """Ask the oracle about every orientation and keep the best-scoring one.

    Con `rank > 0` se queda con la `rank`-ésima mejor (o con la peor que
    entra, si hay menos). El camino de `rank == 0` es el de siempre, tal
    cual: la primera de `choices` con el puntaje más alto. Se deja separado
    a propósito para que ninguna corrida sin perturbación pueda cambiar un
    solo número por culpa de esto.
    """
    if rank == 0:
        best: tuple[float, bool, float, float] | None = None
        best_score = float("-inf")
        for angle, mirror in choices:
            spot = oracle.best_placement(part, angle, mirror)
            if spot is None:
                continue
            x, y, score = spot
            if score > best_score:
                best_score = score
                best = (angle, mirror, x, y)
        return best

    spots: list[tuple[float, int, float, bool, float, float]] = []
    for position, (angle, mirror) in enumerate(choices):
        spot = oracle.best_placement(part, angle, mirror)
        if spot is None:
            continue
        x, y, score = spot
        spots.append((-score, position, angle, mirror, x, y))
    if not spots:
        return None
    spots.sort()
    _, _, angle, mirror, x, y = spots[min(rank, len(spots) - 1)]
    return angle, mirror, x, y
```

- [ ] **Step 4: Correr los tests de rangos y la suite entera**

Run: `.venv/bin/pytest tests/engine/test_packer.py -v`
Expected: PASS

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos.

- [ ] **Step 5: Escribir los tests de la cartera, que fallan**

Crear `tests/conftest.py` (no existe todavía):

```python
"""Fixtures para toda la suite."""

import pytest


@pytest.fixture(autouse=True)
def _tanda_minima_de_uno(request, monkeypatch):
    """Baja `cartera.MIN_BATCH` a 1 salvo en los tests `minimo_real`.

    Con el mínimo de verdad (12), cada `pack()` en normal son trece pasadas
    y la suite tardaría horas; y las cuentas chicas de los tests (`workers=3`
    son cuatro variantes) dejarían de valer. El mínimo se prueba aparte, con
    la marca. Se importa adentro para que un test que no toca el motor no
    lo cargue.
    """
    if request.node.get_closest_marker("minimo_real"):
        return
    from nesting.engine import cartera

    monkeypatch.setattr(cartera, "MIN_BATCH", 1)
```

En `pyproject.toml`, sumar a `[tool.pytest.ini_options]`:

```toml
markers = [
    "minimo_real: usa `cartera.MIN_BATCH` de verdad en vez del 1 de los tests",
]
```

(La Tarea 9 reemplaza esta sección entera y tiene que conservar esta marca.)

El fixture sólo baja el número en el proceso de pytest. Las tandas en
paralelo de la Tarea 6 calculan el tamaño en el proceso principal, así que
el valor parcheado alcanza; los procesos `spawn` nunca lo leen.

Crear `tests/engine/test_cartera.py`:

```python
"""La cartera: variantes en un orden fijo, la mejor gana, y rápido no cambia."""

import math

from nesting.engine.cartera import (
    EFFORT_BATCHES,
    Variant,
    VariantSource,
    _Watch,
    cota_minima,
    evaluate,
    planned_variants,
    run_portfolio,
    smallest_combinations,
)
from nesting.engine.oracle import NestConfig
from nesting.engine.packer import (
    _compact_last_sheet,
    _pack_once,
    _recuperar_de_la_ultima_placa,
    layout_cost,
    pack,
)
from nesting.engine.raster.masks import MaskCache
from nesting.engine.raster.oracle import RasterOracle
from nesting.geometry.verify import verify
from nesting.model.part import Part
from nesting.model.sheet import Sheet, SheetSupply

PLACA = Sheet(1000.0, 1000.0, grain_tolerance=180.0)
PLAN = SheetSupply(stock=PLACA, material_name="prueba")


def rect(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def siete():
    """Siete rectángulos de 400 x 300 en un área útil de 970 x 970: entran
    seis por placa, así que la base abre dos, y la cota por área es una. Es
    el caso más chico donde la cartera tiene algo que buscar. Son el 12,8%
    del área útil: la clase se empareja."""
    return [rect(i, 400.0, 300.0) for i in range(7)]


def config(**cambios):
    base = dict(sep=8.0, margin=15.0, angles=(0.0, 90.0), mirror=False,
                resolution=4.0, effort="normal", seed=0, workers=1)
    base.update(cambios)
    return NestConfig(**base)


# Las corridas usan la clase `RasterOracle` como fábrica, no una lambda que
# capture un `MaskCache`: con `workers > 1` la Tarea 6 manda la fábrica a
# otros procesos, y una lambda no viaja. Así estos tests no cambian cuando
# la tanda pasa a correr en paralelo.


class Espia:
    """Una fábrica que cuenta cada `best_placement`, la unidad de trabajo."""

    def __init__(self):
        self.consultas = 0
        self._cache = MaskCache()

    def __call__(self):
        espia, oraculo = self, RasterOracle(cache=self._cache)

        class Contado:
            def reset(self, *args):
                oraculo.reset(*args)

            def best_placement(self, *args):
                espia.consultas += 1
                return oraculo.best_placement(*args)

            def place(self, *args):
                oraculo.place(*args)

        return Contado()


NUNCA = _Watch(cancelled=lambda: False, best_new_sheets=lambda: 10**9,
               on_queries=lambda total: None)


# --- la cota --------------------------------------------------------------

def test_la_cota_es_el_area_de_las_piezas_sobre_el_area_util():
    assert cota_minima(siete(), PLAN, 15.0) == 1
    trece = [rect(i, 400.0, 300.0) for i in range(13)]
    assert cota_minima(trece, PLAN, 15.0) == math.ceil(13 * 120_000 / 970**2) == 2


def test_con_recortes_no_hay_cota():
    """Con placas de distinto tamaño, la cuenta honesta no es ésa."""
    con_recorte = SheetSupply(stock=PLACA, scraps=(Sheet(500.0, 500.0, 180.0, scrap=True),))
    assert cota_minima(siete(), con_recorte, 15.0) is None


# --- las combinaciones ------------------------------------------------------

def test_las_combinaciones_salen_de_menor_a_mayor_costo_y_desempatan_por_tipo():
    """Tres tipos de cajas 10, 20 y 30, cuatro miembros de caja 100. Con dos
    pares no sobra nadie; con uno sobran dos sueltos (200 más)."""
    combos = [c for _, c in smallest_combinations([10.0, 20.0, 30.0], 4, 100.0, False)]
    assert combos == [(0, 0), (0, 1), (0, 2), (1, 1), (1, 2), (2, 2), (0,), (1,), (2,)]


def test_no_emparejar_es_la_combinacion_mas_cara_cuando_se_pide():
    combos = [c for _, c in smallest_combinations([10.0], 2, 100.0, True)]
    assert combos == [(0,), ()]


def test_sin_tipos_lo_unico_es_no_emparejar():
    assert list(smallest_combinations([], 4, 100.0, True)) == [(400.0, ())]


# --- las variantes ----------------------------------------------------------

def test_las_variantes_salen_en_el_mismo_orden_para_la_misma_semilla():
    uno, otro = VariantSource(siete(), PLAN, config()), VariantSource(siete(), PLAN, config())
    assert uno.base() == otro.base()
    assert uno.batch(1, 5, uno.base()) == otro.batch(1, 5, otro.base())


def test_la_base_es_la_pasada_de_hoy_por_area():
    fuente = VariantSource(siete() + [rect(9, 100.0, 50.0)], PLAN, config())
    base = fuente.base()
    assert base.index == 0 and base.kind == "base" and base.composites == ()
    assert [p.area for p in base.order] == sorted((p.area for p in base.order), reverse=True)


def test_la_primera_tanda_de_lento_es_la_de_normal():
    """Es lo que hace a normal prefijo de lento aunque lento busque diez
    tipos de par y normal seis."""
    normal = VariantSource(siete(), PLAN, config(effort="normal"))
    lento = VariantSource(siete(), PLAN, config(effort="lento"))
    assert normal.batch(1, 6, normal.base()) == lento.batch(1, 6, lento.base())


def test_primero_combinaciones_de_pares_y_despues_perturbaciones_de_orden():
    fuente = VariantSource(siete(), PLAN, config())
    tipos = [v.kind for v in fuente.batch(1, 200, fuente.base())]
    assert tipos[0] == "pares" and tipos[-1] == "orden"
    assert tipos == sorted(tipos, key=lambda t: t != "pares"), "no se intercalan"


def test_sin_clases_emparejables_la_tanda_es_de_perturbaciones():
    """Cuadrados de 100 x 100: el 1% del área útil, no se emparejan."""
    chicos = [rect(i, 100.0, 100.0) for i in range(20)]
    fuente = VariantSource(chicos, PLAN, config())
    assert {v.kind for v in fuente.batch(1, 4, fuente.base())} == {"orden"}


def test_la_tercera_tanda_perturba_orientaciones_de_la_mejor():
    fuente = VariantSource(siete() + [rect(9, 100.0, 50.0)], PLAN, config(effort="lento"))
    mejor = fuente.batch(1, 3, fuente.base())[0]
    tanda = fuente.batch(3, 3, mejor)

    assert {v.kind for v in tanda} == {"orientacion"}
    for variante in tanda:
        assert variante.order == mejor.order
        assert variante.composites == mejor.composites
        assert variante.orientation_ranks
        assert all(0 <= rango < 3 for _, rango in variante.orientation_ranks)


def test_cada_variante_de_pares_usa_cada_pieza_real_una_sola_vez():
    fuente = VariantSource(siete(), PLAN, config())
    for variante in fuente.batch(1, 10, fuente.base()):
        if variante.kind != "pares":
            continue
        miembros = [m for c in variante.composites for m, _ in c.members]
        sueltas = [p.id for p in variante.order if p.id < 7]
        assert sorted(miembros + sueltas) == list(range(7))


# --- evaluar ----------------------------------------------------------------

def test_una_variante_que_abre_mas_placas_que_la_mejor_se_corta():
    variante = Variant(1, "orden", tuple(siete()))
    ya_hay_una_de_cero = _Watch(cancelled=lambda: False, best_new_sheets=lambda: 0,
                                on_queries=lambda total: None)
    assert evaluate(variante, siete(), PLAN, config(), RasterOracle, ya_hay_una_de_cero) is None


def test_sin_corte_la_misma_variante_da_su_resultado():
    variante = Variant(1, "orden", tuple(siete()))
    resultado = evaluate(variante, siete(), PLAN, config(), RasterOracle, NUNCA)
    assert resultado is not None
    assert resultado.cost.placas_nuevas == 2


# --- run_portfolio ----------------------------------------------------------

def test_rapido_es_exactamente_la_pasada_de_siempre():
    """La garantía más importante del plan: rápido no cambia."""
    piezas = siete()
    cfg = config(effort="rapido")
    orden = sorted(piezas, key=lambda p: p.area, reverse=True)
    f = RasterOracle
    viejo = _pack_once(orden, PLAN, cfg, f)
    viejo = _recuperar_de_la_ultima_placa(viejo, piezas, cfg, f, PLAN.material_name)
    viejo = _compact_last_sheet(viejo, piezas, cfg, f, PLAN.material_name)

    nuevo = pack(piezas, PLAN, cfg, RasterOracle)

    assert nuevo.placements == viejo.placements
    assert nuevo.sheets == viejo.sheets
    assert nuevo.utilization == viejo.utilization


def test_si_la_base_alcanza_la_cota_no_se_prueba_nada_mas():
    cuatro = [rect(i, 400.0, 300.0) for i in range(4)]
    salida = run_portfolio(cuatro, PLAN, config(workers=3), RasterOracle)
    assert [v.kind for v in salida.evaluated] == ["base"]
    assert salida.lower_bound == 1 == salida.result.sheets_used


def test_normal_evalua_la_base_y_una_tanda_y_es_prefijo_de_lento():
    normal = run_portfolio(siete(), PLAN, config(effort="normal", workers=3), RasterOracle)
    lento = run_portfolio(siete(), PLAN, config(effort="lento", workers=3), RasterOracle)

    assert len(normal.evaluated) == planned_variants("normal", 3) == 4
    assert len(lento.evaluated) == planned_variants("lento", 3) == 10
    assert lento.evaluated[:4] == normal.evaluated


@pytest.mark.minimo_real
def test_con_pocos_nucleos_la_tanda_no_baja_del_minimo():
    """Decisión del usuario: el resultado no depende de la máquina. Con 4
    núcleos, normal prueba las mismas 12 variantes que con 12."""
    from nesting.engine.cartera import MIN_BATCH, batch_size

    assert MIN_BATCH == 12
    assert batch_size(1) == batch_size(4) == batch_size(12) == 12
    assert planned_variants("normal", 4) == planned_variants("normal", 12) == 13
    assert planned_variants("lento", 4) == 37


@pytest.mark.minimo_real
def test_con_mas_nucleos_que_el_minimo_la_tanda_crece():
    from nesting.engine.cartera import batch_size

    assert batch_size(14) == 14
    assert planned_variants("normal", 14) == 15


@pytest.mark.minimo_real
def test_rapido_no_paga_el_minimo():
    assert planned_variants("rapido", 4) == 1


def test_mas_esfuerzo_nunca_da_peor():
    costos = {
        e: layout_cost(pack(siete(), PLAN, config(effort=e, workers=2), RasterOracle), siete())
        for e in EFFORT_BATCHES
    }
    assert costos["lento"] <= costos["normal"] <= costos["rapido"]


def test_el_resultado_trae_solo_piezas_reales_y_verifica():
    piezas = siete()
    salida = run_portfolio(piezas, PLAN, config(effort="lento", workers=3), RasterOracle)
    resultado = salida.result

    assert sorted(p.part_id for p in resultado.placements) == list(range(7))
    assert verify(piezas, resultado.placements, resultado.sheets, sep=8.0, margin=15.0) == []


def test_el_avance_suma_consultas_y_nunca_retrocede():
    """Con `workers=1` todo corre en este proceso y el espía ve cada
    consulta: la cuenta del avance tiene que coincidir exacta. (En paralelo
    el espía viajaría a otros procesos y contaría allá.)"""
    avances = []
    espia = Espia()
    pack(siete(), PLAN, config(workers=1), espia,
         progreso=lambda a: avances.append(a) or True)

    hechas = [a.consultas_hechas for a in avances]
    assert hechas == sorted(hechas)
    assert all(a.consultas_previstas >= a.consultas_hechas for a in avances)
    assert hechas[-1] == espia.consultas


def test_el_avance_de_la_cartera_cuenta_combinaciones():
    avances = []
    pack(siete(), PLAN, config(workers=2), RasterOracle,
         progreso=lambda a: avances.append(a) or True)

    de_cartera = [a for a in avances if a.combinaciones]
    assert de_cartera, "la tanda tiene que avisar"
    assert all(a.combinaciones == planned_variants("normal", 2) for a in de_cartera)
    assert max(a.combinaciones_hechas for a in de_cartera) >= 2
    assert all(a.placa_minima >= 1 for a in de_cartera)
```

- [ ] **Step 6: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/engine/test_cartera.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'nesting.engine.cartera'`

- [ ] **Step 7: `NestConfig.workers` y los campos nuevos de `Avance`**

En `src/nesting/engine/oracle.py`, agregar a `NestConfig` después de `seed`:

```python
    workers: int = 1
    """Cuántas variantes por tanda prueba la cartera: la `N` de la spec.

    Es a la vez cuántos procesos corren a la par (Tarea 6 del plan de pares
    y cartera). Con 1 todo corre en el proceso que llama, sin crear nada: es
    el valor por omisión para que el motor, usado como biblioteca o desde un
    test, no dispare procesos que nadie pidió. La CLI y la interfaz pasan el
    valor que corresponde a la máquina (`nesting.params.nucleos_efectivos`).
    """
```

En `src/nesting/engine/packer.py`, agregar a `Avance`, después del último
campo que dejó el plan 2 (`consultas_previstas`):

```python
    combinaciones: int = 0
    """Cuántas variantes prevé la cartera en total, base incluida.

    Cero mientras corre la base: la pantalla muestra entonces el texto de
    siempre (piezas ubicadas, placa en curso). Distinto de cero mientras se
    prueban las tandas, cuando varias variantes corren a la vez y "ubicadas
    de tantas" deja de tener sentido.
    """

    combinaciones_hechas: int = 0
    """Variantes terminadas, base incluida."""

    placa_minima: int = 0
    """Placas de la mejor variante terminada hasta ahora."""
```

- [ ] **Step 8: Escribir `src/nesting/engine/cartera.py`**

```python
"""La cartera: varias maneras de acomodar lo mismo, y quedarse con la mejor.

`pack()` delega acá. Una VARIANTE es una lista de piezas -- sueltas y
compuestas (pares encastrados, ver `pares.py`) --, un orden de inserción y,
opcionalmente, una perturbación de orientaciones. Cada una se acomoda con la
misma pasada golosa de siempre (`_pack_once`), y gana la de menor
`CostoLayout`, con desempate por índice de variante: el resultado no depende
de en qué orden terminan.

La base es la pasada de hoy y se evalúa primero, sola. Si ya alcanza la cota
por área no se busca nada más. Si no, se evalúan tandas de `config.workers`
variantes, en el orden fijo de la spec (4.1). Recuperación y compactación
corren una sola vez, sobre la ganadora y todavía con compuestas, y recién
después se desarma.

Spec: docs/superpowers/specs/2026-09-22-pares-y-cartera-design.es.md, sección 4.
"""

import heapq
import itertools
import math
import random
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass

from nesting.engine import pares
from nesting.engine.iguales import Clase, find_classes
from nesting.engine.oracle import NestConfig, Oracle
from nesting.engine.packer import (
    Avance,
    Cancelado,
    CostoLayout,
    PackResult,
    PartTooLargeError,
    UnknownEffortError,
    _compact_last_sheet,
    _pack_once,
    _perturb,
    _recuperar_de_la_ultima_placa,
    initial_forecast,
    layout_cost,
    orientations,
)
from nesting.engine.raster.masks import MaskCache
from nesting.model.part import Part
from nesting.model.sheet import SheetSupply

EFFORT_BATCHES: dict[str, int] = {"rapido": 0, "normal": 1, "lento": 3}
"""Cuántas tandas de `NestConfig.workers` variantes se prueban después de la base.

Reemplaza a `EFFORT_RESTARTS` (1, 3 y 12 pasadas). Los reintentos de antes
sólo permutaban el orden de inserción, y seis copias idénticas permutadas
dan el mismo acomodo: sobre la banqueta alta esos reintentos no exploraban
nada (spec 1.1). Una tanda son `batch_size(N)` variantes: `N`, pero nunca
menos de `MIN_BATCH`. Con 12 núcleos o más, normal prueba `N` variantes en
el tiempo de una pasada; con menos, las mismas 12 en varias vueltas.

`lento <= normal <= rapido` sigue valiendo por construcción: con el mismo
`N` y la misma semilla, las variantes de `rapido` son un prefijo de las de
`normal`, y las de `normal` un prefijo de las de `lento` (ver
`VariantSource.batch`); y la ganadora sólo se reemplaza por una
estrictamente mejor. Con distinto `N` la garantía no aplica: más núcleos
exploran más.

HISTORIA: LA TABLA DE REINTENTOS QUE ESTO REEMPLAZA.
"""
```

A continuación de esa última línea, **dentro del mismo docstring**, pegar
el docstring entero de `EFFORT_RESTARTS` tal como está hoy en `packer.py`
(desde "How many insertion orders each effort level tries." hasta "nunca por
suerte de la semilla."). Son las mediciones que justificaron los números
viejos; se conservan porque explican por qué el esfuerzo extra rinde cerca
de un salto de placa y no lejos de uno, y eso sigue siendo cierto.

Seguir el archivo con:

```python
QUERY_REPORT_EVERY = 25
"""Cada cuántas consultas una variante informa su cuenta.

Informar cada consulta haría que el aviso cueste más que la consulta en las
placas vacías; cada 25, en la pasada más rápida medida, es un aviso cada
pocas décimas de segundo.
"""

ORIENTATION_RANKS = 3
"""Entre cuántas orientaciones de mejor puntaje elige la perturbación de `lento`."""

ORIENTATION_TOP_SHARE = 0.1
"""Qué parte de las piezas, las de más área, se perturban en orientación."""

MIN_BATCH = 12
"""Cuántas variantes tiene, como mínimo, cada tanda, aunque haya menos núcleos.

Decisión del usuario (2026-09-22): el resultado no puede depender de la
máquina. Sobre la banqueta alta, la combinación que gana sale octava; con
tandas de `N` variantes, una computadora de 4 núcleos no la encontraba ni en
lento (tres tandas de 2 con dos núcleos libres son seis). Con este mínimo,
toda máquina de hasta 12 núcleos prueba exactamente las mismas variantes y
da el mismo resultado; una de 4 tarda unas tres veces más en normal, y el
tiempo estimado lo avisa antes de arrancar. Con más de 12 núcleos la tanda
crece a `N`: más núcleos exploran más, en el mismo tiempo.

Los tests lo bajan a 1 con el fixture `_tanda_minima_de_uno` de
`tests/conftest.py`, para que las cuentas chicas de siempre sigan valiendo;
los que prueban el mínimo de verdad llevan `@pytest.mark.minimo_real`.
"""


def batch_size(workers: int) -> int:
    """Cuántas variantes tiene cada tanda: `N`, pero nunca menos de `MIN_BATCH`."""
    return max(1, workers, MIN_BATCH)


def cota_minima(parts: Sequence[Part], supply: SheetSupply, margin: float) -> int | None:
    """⌈área neta de las piezas / área útil de la placa del Material⌉.

    Con recortes no se informa: con placas de distinto tamaño la cuenta
    honesta no es ésta. Que el área permita menos placas no quiere decir que
    entren -- la banqueta con veta tiene cota 1 y el mínimo real es 2 --, así
    que sólo se usa en un sentido: si un layout la iguala, no hay nada que
    ganar en placas.
    """
    if supply.scraps or not parts:
        return None
    usable = (supply.stock.width - 2 * margin) * (supply.stock.height - 2 * margin)
    if usable <= 0:
        return None
    # El 1e-9 es para que un área que da justo k placas no suba a k+1 por
    # el ruido de la suma.
    return max(1, math.ceil(sum(p.area for p in parts) / usable - 1e-9))


def planned_variants(effort: str, workers: int) -> int:
    """Cuántas variantes prevé la cartera, base incluida, si no corta por la cota."""
    return 1 + EFFORT_BATCHES[effort] * batch_size(workers)


def smallest_combinations(
    type_areas: Sequence[float],
    members: int,
    loose_area: float,
    include_empty: bool,
) -> Iterator[tuple[float, tuple[int, ...]]]:
    """Cada multiconjunto de tipos de par para una clase, de menor a mayor costo.

    Un multiconjunto es una tupla no decreciente de índices de tipo, uno por
    par: `(0, 0, 1)` son dos pares del tipo 0 y uno del tipo 1. Su costo es
    la suma de las cajas de sus pares más la caja de cada miembro que queda
    suelto. Los empates se ordenan por la tupla, que es "por índice de tipo".

    Es perezoso a propósito: con veinte copias y diez tipos hay millones de
    multiconjuntos, y la cartera nunca necesita más que unas decenas. Como
    `type_areas` viene de menor a mayor (`find_pair_types` lo garantiza),
    subir un índice nunca baja el costo, y un montículo alcanza para
    sacarlos en orden sin generarlos todos.
    """
    max_pairs = members // 2 if type_areas else 0

    def cost(combo: tuple[int, ...]) -> float:
        return sum(type_areas[i] for i in combo) + (members - 2 * len(combo)) * loose_area

    heap: list[tuple[float, tuple[int, ...]]] = []
    seen: set[tuple[int, ...]] = set()
    for pairs in range(0 if include_empty else 1, max_pairs + 1):
        combo = (0,) * pairs
        heapq.heappush(heap, (cost(combo), combo))
        seen.add(combo)

    while heap:
        value, combo = heapq.heappop(heap)
        yield value, combo
        for i in range(len(combo)):
            bumped = combo[i] + 1
            if bumped < len(type_areas) and (i == len(combo) - 1 or bumped <= combo[i + 1]):
                following = combo[:i] + (bumped,) + combo[i + 1:]
                if following not in seen:
                    seen.add(following)
                    heapq.heappush(heap, (cost(following), following))


@dataclass(frozen=True)
class Variant:
    index: int
    kind: str
    """Uno de "base", "pares", "orden" u "orientacion"."""

    order: tuple[Part, ...]
    """Las piezas a acomodar, sueltas y compuestas, en orden de inserción."""

    composites: tuple[pares.Composite, ...] = ()
    pair_types: tuple[tuple[int, int], ...] = ()
    """(clase, tipo) de cada par, en el orden de `composites`."""

    orientation_ranks: tuple[tuple[int, int], ...] = ()
    """(id de pieza, rango) para la perturbación de orientaciones."""


@dataclass
class Outcome:
    index: int
    packed: PackResult
    """El acomodo tal como salió, todavía con compuestas."""

    cost: CostoLayout
    """El costo del acomodo YA DESARMADO, sobre las piezas reales: el área
    de una compuesta incluye su puente, que no es material de nadie."""

    queries: int


@dataclass
class PortfolioResult:
    result: PackResult
    """El ganador, con recuperación y compactación, desarmado: sólo piezas reales."""

    winner: Variant
    evaluated: list[Variant]
    lower_bound: int | None


@dataclass(frozen=True)
class _PairPlan:
    classes: tuple[Clase, ...]
    types: tuple[tuple[pares.PairType, ...], ...]


def _box_area(part: Part) -> float:
    x0, y0, x1, y1 = part.bbox
    return (x1 - x0) * (y1 - y0)


def _build_pair_plan(
    parts: Sequence[Part], supply: SheetSupply, config: NestConfig, cache: MaskCache
) -> _PairPlan:
    stock = supply.stock
    usable_w = stock.width - 2 * config.margin
    usable_h = stock.height - 2 * config.margin
    if usable_w <= 0 or usable_h <= 0:
        return _PairPlan((), ())
    choices = orientations(stock, config)
    grain = stock.grain_tolerance < 90.0
    classes = pares.pairable_classes(find_classes(parts, choices), usable_w * usable_h, grain)
    how_many = pares.TIPOS_POR_CLASE[config.effort]
    kept_classes: list[Clase] = []
    kept_types: list[tuple[pares.PairType, ...]] = []
    for clase in classes:
        types = pares.find_pair_types(
            clase.representative, pares.b_orientations(choices, grain), choices,
            config, (usable_w, usable_h), how_many, cache,
        )
        if types:
            kept_classes.append(clase)
            kept_types.append(tuple(types))
    return _PairPlan(tuple(kept_classes), tuple(kept_types))


class VariantSource:
    """Las variantes, en el orden fijo de la spec (4.1).

    Depende sólo de las piezas, la config y la semilla -- y, para la tercera
    tanda de `lento`, de cuál fue la mejor hasta ahí, que a su vez depende
    sólo de lo mismo. Nunca del orden en que terminan los procesos.
    """

    def __init__(self, parts: Sequence[Part], supply: SheetSupply, config: NestConfig) -> None:
        self._parts = list(parts)
        self._supply = supply
        self._config = config
        self._by_area = sorted(parts, key=lambda p: p.area, reverse=True)
        self._rng = random.Random(config.seed)
        self._plan: _PairPlan | None = None
        self._used: set[tuple[tuple[int, ...], ...]] = set()
        self._next_index = 1
        self._next_id = max((p.id for p in parts), default=-1) + 1

    def base(self) -> Variant:
        return Variant(0, "base", tuple(self._by_area))

    def batch(self, number: int, size: int, best: Variant) -> list[Variant]:
        """La tanda `number` (1, 2 o 3), de `size` variantes.

        1 (normal y lento): combinaciones de pares con los primeros
          `TIPOS_POR_CLASE["normal"]` tipos, y si no alcanzan, perturbaciones
          de orden.
        2 (lento): combinaciones con los `TIPOS_POR_CLASE["lento"]` tipos que
          todavía no se probaron, y si no alcanzan, perturbaciones de orden.
        3 (lento): perturbaciones de orientación de `best`, la mejor hasta ahí
          -- la base si ningún par ayudó, la mejor combinación si alguna sí.

        La 1 es idéntica en normal y en lento: el mismo límite de tipos, los
        mismos tipos (el orden de `find_pair_types` es un contrato) y el mismo
        generador consumido igual. Eso hace a normal prefijo de lento.
        """
        if number >= 3:
            return [self._orientation_variant(best) for _ in range(size)]
        limit = pares.TIPOS_POR_CLASE["normal" if number == 1 else "lento"]
        variants = [self._pair_variant(c) for c in self._combinations(limit, size)]
        while len(variants) < size:
            variants.append(self._new("orden", tuple(_perturb(self._by_area, self._rng))))
        return variants

    def _new(self, kind: str, order: tuple[Part, ...], **rest) -> Variant:
        variant = Variant(self._next_index, kind, order, **rest)
        self._next_index += 1
        return variant

    def _pair_plan(self) -> _PairPlan:
        if self._plan is None:
            self._plan = _build_pair_plan(self._parts, self._supply, self._config, MaskCache())
        return self._plan

    def _combinations(self, type_limit: int, size: int) -> list[tuple[tuple[int, ...], ...]]:
        plan = self._pair_plan()
        if not plan.classes:
            return []
        want = size + len(self._used)
        streams = [
            (clase, [t.box_area for t in types[:type_limit]])
            for clase, types in zip(plan.classes, plan.types)
        ]
        if len(streams) == 1:
            clase, areas = streams[0]
            ranked = [
                (combo,)
                for _, combo in itertools.islice(
                    smallest_combinations(areas, len(clase.members),
                                          _box_area(clase.representative), False),
                    want,
                )
            ]
        else:
            per_class = [
                list(itertools.islice(
                    smallest_combinations(areas, len(clase.members),
                                          _box_area(clase.representative), True),
                    want + 1,
                ))
                for clase, areas in streams
            ]
            product = sorted(
                (cost_a + cost_b, (combo_a, combo_b))
                for cost_a, combo_a in per_class[0]
                for cost_b, combo_b in per_class[1]
                if combo_a or combo_b
            )
            ranked = [combo for _, combo in product[:want]]
        fresh = [combo for combo in ranked if combo not in self._used][:size]
        self._used.update(fresh)
        return fresh

    def _pair_variant(self, combo: tuple[tuple[int, ...], ...]) -> Variant:
        plan = self._pair_plan()
        composites: list[pares.Composite] = []
        pair_types: list[tuple[int, int]] = []
        paired: set[int] = set()
        for class_index, (clase, choice) in enumerate(zip(plan.classes, combo)):
            for k, type_index in enumerate(choice):
                first, second = clase.members[2 * k], clase.members[2 * k + 1]
                composites.append(pares.make_composite(
                    self._next_id, plan.types[class_index][type_index], first, second,
                ))
                self._next_id += 1
                pair_types.append((class_index, type_index))
                paired.update((first.part_id, second.part_id))
        loose = [p for p in self._by_area if p.id not in paired]
        order = sorted([c.part for c in composites] + loose, key=lambda p: p.area, reverse=True)
        return self._new("pares", tuple(order), composites=tuple(composites),
                         pair_types=tuple(pair_types))

    def _orientation_variant(self, best: Variant) -> Variant:
        top = max(1, math.ceil(len(best.order) * ORIENTATION_TOP_SHARE))
        largest = sorted(best.order, key=lambda p: p.area, reverse=True)[:top]
        ranks = tuple((p.id, self._rng.randrange(ORIENTATION_RANKS)) for p in largest)
        return self._new("orientacion", best.order, composites=best.composites,
                         pair_types=best.pair_types, orientation_ranks=ranks)


# --- vigilar una variante mientras corre -------------------------------------

@dataclass
class _Watch:
    """Lo que una variante necesita saber de afuera mientras corre."""

    cancelled: Callable[[], bool]
    best_new_sheets: Callable[[], int]
    """Placas nuevas de la mejor variante terminada."""

    on_queries: Callable[[int], None]
    """Recibe el total de consultas de ESTA variante hasta ahora."""

    report_every: int = QUERY_REPORT_EVERY
    """Cada cuántas consultas se llama a `on_queries`. La base y el tramo
    final usan 1: ahí `on_queries` sólo anota, no avisa, y el aviso sale por
    el `aviso` de siempre, con la cuenta al día."""


def _never_beaten() -> int:
    return sys.maxsize


class _Beaten(Exception):
    """La variante ya abrió más placas que la mejor terminada: no puede ganar."""


class _QueryCounter:
    def __init__(self, watch: _Watch) -> None:
        self.total = 0
        self._reported = 0
        self._watch = watch

    def add(self) -> None:
        self.total += 1
        if self.total - self._reported >= self._watch.report_every:
            self.flush()

    def flush(self) -> None:
        if self.total != self._reported:
            self._reported = self.total
            self._watch.on_queries(self.total)


class _WatchedOracle:
    """Un oráculo que cuenta cada consulta y mira si hay que cancelar.

    La consulta es la unidad de trabajo del tiempo estimado (spec de tiempo
    estimado, 2): contarla acá, envolviendo al oráculo, la hace independiente
    de qué fase la pidió -- base, tanda, recuperación o compactación -- y de
    en qué proceso corre.
    """

    def __init__(self, inner: Oracle, counter: _QueryCounter, watch: _Watch) -> None:
        self._inner = inner
        self._counter = counter
        self._watch = watch

    def reset(self, sheet_w: float, sheet_h: float, config: NestConfig) -> None:
        self._inner.reset(sheet_w, sheet_h, config)

    def best_placement(self, part: Part, angle: float, mirror: bool):
        if self._watch.cancelled():
            raise Cancelado("el trabajo se canceló")
        self._counter.add()
        return self._inner.best_placement(part, angle, mirror)

    def place(self, part: Part, angle: float, mirror: bool, x: float, y: float) -> None:
        self._inner.place(part, angle, mirror, x, y)


class _WatchedFactory:
    """La fábrica de siempre, más el corte de lo que ya perdió.

    `_pack_once` pide un oráculo por placa, así que contar los pedidos es
    contar placas abiertas. Si una variante abre más placas nuevas que la
    mejor terminada, no puede ganar -- `placas_nuevas` manda sobre todo lo
    demás -- y se abandona. Las placas nuevas abiertas son al menos las
    pedidas menos los recortes del plan, y la cuenta usa esa cota: nunca
    corta una variante que todavía podría ganar.
    """

    def __init__(self, inner: Callable[[], Oracle], counter: _QueryCounter,
                 watch: _Watch, scraps: int) -> None:
        self._inner = inner
        self._counter = counter
        self._watch = watch
        self._scraps = scraps
        self.opened = 0

    def __call__(self) -> Oracle:
        self.opened += 1
        if self.opened - self._scraps > self._watch.best_new_sheets():
            raise _Beaten()
        return _WatchedOracle(self._inner(), self._counter, self._watch)


def evaluate(
    variant: Variant,
    parts: Sequence[Part],
    supply: SheetSupply,
    config: NestConfig,
    factory: Callable[[], Oracle],
    watch: _Watch,
    aviso: Callable[[int, int], None] | None = None,
) -> Outcome | None:
    """Acomoda una variante. `None` si se cortó o si una compuesta no entra.

    La base no se corta nunca (se la llama con `_never_beaten`) y su
    `PartTooLargeError` sí se propaga: es el error de siempre, "esta pieza no
    entra en una placa vacía". En las demás variantes, una compuesta que el
    oráculo no logra ubicar ni en una placa vacía descarta la variante, no
    el trabajo: las piezas sueltas sí entran, como lo probó la base.
    """
    counter = _QueryCounter(watch)
    watched = _WatchedFactory(factory, counter, watch, len(supply.scraps))
    try:
        packed = _pack_once(
            list(variant.order), supply, config, watched, aviso,
            orientation_ranks=dict(variant.orientation_ranks) or None,
        )
    except _Beaten:
        counter.flush()
        return None
    except PartTooLargeError:
        if variant.kind == "base":
            raise
        counter.flush()
        return None
    counter.flush()
    real = pares.disassemble(packed, variant.composites, parts)
    return Outcome(variant.index, packed, layout_cost(real, parts), counter.total)


# --- avance -----------------------------------------------------------------

class _Progress:
    """Suma las consultas de todo `run_portfolio` y arma cada `Avance`.

    Tres fases: la base (el texto de siempre: piezas ubicadas y placa en
    curso), la cartera (variantes terminadas de tantas, y la placa mínima
    hasta ahora) y el tramo final (recuperación y compactación, que la
    pantalla muestra como "compactando").

    Las consultas se suman por variante y no se reinician nunca, así que
    `consultas_hechas` no retrocede; `consultas_previstas` se corrige a
    medida que se sabe más y nunca queda por debajo de las hechas.
    """

    def __init__(self, progreso: Callable[[Avance], bool] | None,
                 totales: int, planned: int, initial_queries: int) -> None:
        self._progreso = progreso
        self._totales = totales
        self._planned = planned
        self._queries: dict[object, int] = {}
        # La previsión de arranque del plan 2 (`initial_forecast`), que con
        # `_restarts_for` apuntando a `planned_variants` cuenta una pasada
        # por variante prevista, más la recuperación y la compactación.
        self._planned_queries = initial_queries
        self._phase = "base"
        self._ubicadas = 0
        self._placa = 1
        self._done = 0
        self._best_sheets = 0
        self.cancel_requested = False

    @property
    def queries(self) -> int:
        return sum(self._queries.values())

    def record(self, slot: object, total: int) -> None:
        # `max` y no asignación: en paralelo (Tarea 6) el total de una
        # variante llega dos veces, por la cola y con su resultado, y un
        # mensaje viejo de la cola puede llegar después del definitivo.
        self._queries[slot] = max(self._queries.get(slot, 0), total)

    @property
    def listening(self) -> bool:
        return self._progreso is not None

    def watch(self, slot: object, best_new_sheets: Callable[[], int],
              emit: bool = True) -> _Watch:
        """Lo que mira una variante mientras corre.

        Con `emit=True` (las tandas) cada `QUERY_REPORT_EVERY` consultas se
        anotan y se avisa. Con `emit=False` (la base y el tramo final) cada
        consulta se anota y NO se avisa: ahí avisa el `aviso` de siempre,
        uno por pieza intentada, que es lo que el plan 2 fijó y sus tests
        cuentan (1 al entrar + uno por pieza + 1 al terminar, en la
        compactación de una sola placa).
        """
        def on_queries(total: int) -> None:
            self.record(slot, total)
            if emit:
                self.emit()

        return _Watch(
            cancelled=lambda: self.cancel_requested,
            best_new_sheets=best_new_sheets,
            on_queries=on_queries,
            report_every=QUERY_REPORT_EVERY if emit else 1,
        )

    def placed(self, ubicadas: int, placa: int) -> None:
        """El `aviso` de `_pack_once` para la base."""
        self._ubicadas, self._placa = ubicadas, placa
        self.emit()

    def base_done(self, outcome: Outcome) -> None:
        self._phase = "cartera"
        self._done = 1
        self._best_sheets = outcome.packed.sheets_used
        # Ya se sabe cuánto costó una pasada de verdad: las que faltan se
        # prevén iguales, más una para el tramo final.
        self._planned_queries = outcome.queries * (self._planned + 1)

    def variant_done(self, outcome: Outcome | None) -> None:
        self._done += 1
        if outcome is not None:
            self._best_sheets = min(self._best_sheets, outcome.packed.sheets_used)
        self.emit()

    def final(self) -> None:
        self._phase = "final"
        self._planned_queries = self.queries + max(self._queries.get("base", 0), 1)
        self.emit()

    def emit(self) -> None:
        if self._progreso is None:
            return
        hechas = self.queries
        comunes = dict(
            intentos=self._planned,
            totales=self._totales,
            consultas_hechas=hechas,
            consultas_previstas=max(self._planned_queries, hechas),
        )
        if self._phase == "base":
            avance = Avance(intento=1, ubicadas=self._ubicadas, placa=self._placa, **comunes)
        elif self._phase == "cartera":
            avance = Avance(
                intento=min(self._done + 1, self._planned), ubicadas=0,
                placa=self._best_sheets, combinaciones=self._planned,
                combinaciones_hechas=self._done, placa_minima=self._best_sheets,
                **comunes,
            )
        else:
            avance = Avance(intento=self._planned, ubicadas=self._totales, placa=0,
                            compactando=True, **comunes)
        if not self._progreso(avance):
            self.cancel_requested = True
            raise Cancelado("el trabajo se canceló")


# --- evaluar tandas -----------------------------------------------------------

class _Evaluator:
    """Evalúa tandas de variantes. En esta versión, una detrás de otra.

    Es un administrador de contexto porque la Tarea 6 le agrega un pool de
    procesos que hay que cerrar pase lo que pase.
    """

    def __init__(self, config: NestConfig, factory: Callable[[], Oracle]) -> None:
        self._config = config
        self._factory = factory

    def __enter__(self) -> "_Evaluator":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def run(self, batch: Sequence[Variant], parts: Sequence[Part], supply: SheetSupply,
            best_new_sheets: int, progress: _Progress) -> list[Outcome]:
        """Los resultados de la tanda que no se cortaron, en orden de índice."""
        mejor = best_new_sheets
        outcomes: list[Outcome] = []
        for variant in batch:
            outcome = evaluate(
                variant, parts, supply, self._config, self._factory,
                progress.watch(("variante", variant.index), lambda: mejor),
            )
            progress.variant_done(outcome)
            if outcome is not None:
                outcomes.append(outcome)
                mejor = min(mejor, outcome.cost.placas_nuevas)
        return outcomes


def _finish(best: Outcome, winner: Variant, parts: Sequence[Part], supply: SheetSupply,
            config: NestConfig, factory: Callable[[], Oracle], progress: _Progress) -> PackResult:
    """Recuperación y compactación sobre la ganadora, todavía con compuestas, y desarmar.

    Avisa como avisaba `pack()` después del plan 2: una vez al entrar, una
    por pieza que la recuperación o la compactación intentan (su `aviso`), y
    una al terminar. Cancelar corta en cualquiera de esos avisos, y también
    en la próxima consulta (`_WatchedOracle`).
    """
    progress.final()
    watch = progress.watch("final", _never_beaten, emit=False)
    counter = _QueryCounter(watch)
    watched = _WatchedFactory(factory, counter, watch, 0)

    def aviso(ubicadas: int, placa: int) -> None:
        progress.emit()

    avisar = aviso if progress.listening else None
    working = list(winner.order)
    result = _recuperar_de_la_ultima_placa(best.packed, working, config, watched,
                                           supply.material_name, avisar)
    result = _compact_last_sheet(result, working, config, watched,
                                 supply.material_name, avisar)
    counter.flush()
    progress.emit()
    return pares.disassemble(result, winner.composites, parts)


def run_portfolio(
    parts: Sequence[Part],
    supply: SheetSupply,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    progreso: Callable[[Avance], bool] | None = None,
) -> PortfolioResult:
    """Acomoda `parts` probando la cartera que corresponde al esfuerzo."""
    if config.effort not in EFFORT_BATCHES:
        raise UnknownEffortError(
            f"nivel de esfuerzo {config.effort!r} desconocido; "
            f"use uno de {', '.join(EFFORT_BATCHES)}"
        )

    started = time.perf_counter()
    lower = cota_minima(parts, supply, config.margin)
    source = VariantSource(parts, supply, config)
    base = source.base()
    if not parts:
        return PortfolioResult(PackResult(seconds=time.perf_counter() - started), base, [], lower)

    size = batch_size(config.workers)
    planned = planned_variants(config.effort, config.workers)
    progress = _Progress(progreso, len(parts), planned,
                         initial_forecast(parts, supply, config))

    best = evaluate(base, parts, supply, config, oracle_factory,
                    progress.watch("base", _never_beaten, emit=False), aviso=progress.placed)
    progress.base_done(best)
    winner = base
    evaluated = [base]

    with _Evaluator(config, oracle_factory) as evaluator:
        for number in range(1, EFFORT_BATCHES[config.effort] + 1):
            if lower is not None and best.cost.placas_nuevas <= lower:
                break
            batch = source.batch(number, size, winner)
            by_index = {v.index: v for v in batch}
            for outcome in evaluator.run(batch, parts, supply, best.cost.placas_nuevas, progress):
                # Estrictamente menor: entre costos iguales gana el índice
                # más bajo, y `run` devuelve en orden de índice.
                if outcome.cost < best.cost:
                    best, winner = outcome, by_index[outcome.index]
            evaluated.extend(batch)

    result = _finish(best, winner, parts, supply, config, oracle_factory, progress)
    result.seconds = time.perf_counter() - started
    return PortfolioResult(result, winner, evaluated, lower)
```

- [ ] **Step 9: `pack()` delega en la cartera, y `EFFORT_RESTARTS` se va**

En `src/nesting/engine/packer.py`:

1. Borrar `EFFORT_RESTARTS` y su docstring (ya se pegó en `cartera.EFFORT_BATCHES`).
2. Reemplazar el cuerpo entero de `pack()` -- desde `if config.effort not in EFFORT_RESTARTS:` hasta `return best` -- y su docstring por:

```python
def pack(
    parts: Sequence[Part],
    supply: SheetSupply,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    progreso: Callable[[Avance], bool] | None = None,
) -> PackResult:
    """Acomoda todo probando la cartera de variantes; ver `nesting.engine.cartera`.

    La firma es la de siempre. `progreso`, si se pasa, recibe un `Avance`
    por pieza intentada durante la base, cada `cartera.QUERY_REPORT_EVERY`
    consultas durante las tandas, y durante el tramo final (recuperación y
    compactación) con `compactando=True`: al entrar, por pieza intentada y
    al terminar. Devolver `False` en cualquiera de
    esas llamadas pide abandonar, y `pack` levanta `Cancelado`. No pasarlo
    deja el comportamiento exactamente como estaba.

    El resultado trae sólo piezas reales: las compuestas se desarman antes
    de volver.
    """
    # Import tardío: la cartera importa este módulo.
    from nesting.engine.cartera import run_portfolio

    return run_portfolio(parts, supply, config, oracle_factory, progreso).result
```

3. `import random` se queda en `packer.py`: lo usa la anotación de `_perturb` (`rng: random.Random`).
4. Borrar `_QueryCounter`, `_CountingOracle`, `_counting` e `_Informe` (los del plan 2): el cuerpo viejo de `pack()` era su único usuario, y la cartera cuenta con `_WatchedOracle`. Borrar también `_forecast_final_phases` y `_compaction_forecast` si, después de esto, `grep -rn "_forecast_final_phases\|_compaction_forecast" src tests bench` sólo los encuentra en su propia definición.
5. Reemplazar `_restarts_for` por:

```python
def _restarts_for(config: NestConfig) -> int:
    """Cuántas pasadas golosas prevé la cartera para esta config, o el error de siempre.

    Antes era `EFFORT_RESTARTS[config.effort]`. Ahora cada variante de la
    cartera es una pasada, así que son `planned_variants`: la base más las
    tandas de `config.workers`. `initial_forecast` lo usa para la previsión
    de arranque, que cuenta consultas TOTALES -- sumadas entre procesos, como
    las cuenta el avance --; la estimación previa de tiempo usa
    `cartera.wall_forecast` (Tarea 7), que las divide por los núcleos.
    """
    from nesting.engine.cartera import EFFORT_BATCHES, planned_variants

    if config.effort not in EFFORT_BATCHES:
        raise UnknownEffortError(
            f"nivel de esfuerzo {config.effort!r} desconocido; "
            f"use uno de {', '.join(EFFORT_BATCHES)}"
        )
    return planned_variants(config.effort, config.workers)
```

En `src/nesting/cli.py`, sacar `EFFORT_RESTARTS` del import de `nesting.engine.packer`, agregar `from nesting.engine.cartera import EFFORT_BATCHES` y cambiar la línea 398:

```python
    parser.add_argument("--esfuerzo", choices=sorted(EFFORT_BATCHES), default="normal",
```

En `bench/calibrate.py:275`, cambiar `EFFORT_RESTARTS en engine/packer.py` por `EFFORT_BATCHES en engine/cartera.py`.

Run: `grep -rn "EFFORT_RESTARTS\|_Informe\|_CountingOracle" src tests bench`
Expected: sólo las líneas de tests que el Paso 10 reescribe.

- [ ] **Step 10: Adaptar los tests que hablaban de reintentos**

En `tests/engine/test_effort.py`:

- En el import de `nesting.engine.packer`, borrar `EFFORT_RESTARTS,` y agregar `from nesting.engine.cartera import EFFORT_BATCHES`.
- Reemplazar `test_the_effort_table_has_the_three_levels`:

```python
def test_the_effort_table_has_the_three_levels():
    assert set(EFFORT_BATCHES) == {"rapido", "normal", "lento"}
    assert EFFORT_BATCHES["rapido"] < EFFORT_BATCHES["normal"] < EFFORT_BATCHES["lento"]
```

- Reemplazar `test_different_seeds_can_give_different_results` entero:

```python
def test_different_seeds_can_give_different_results():
    """Con la cartera, la semilla decide las perturbaciones de orden, que
    llegan cuando no hay clases emparejables (o cuando se acaban las
    combinaciones). Estas medidas son las del fixture viejo con las tres que
    pasaban el 2% del área útil (970 x 970 = 940.900 mm², el 2% son 18.818)
    achicadas por debajo: 150x150 -> 150x120, 140x140 -> 140x130,
    90x220 -> 85x220. Sin pares, la tanda de normal con `workers=2` son dos
    perturbaciones desde `by_area` con el mismo generador: exactamente los
    dos reintentos del normal viejo.

    Se miran cuatro semillas y se pide al menos dos layouts distintos, que
    es lo que el docstring viejo medía (cuatro layouts entre cuatro
    semillas), en vez de apostar a que justo las semillas 1 y 2 difieran."""
    sizes = [(120.0, 90.0), (200.0, 60.0), (150.0, 120.0), (80.0, 200.0),
             (250.0, 40.0), (100.0, 100.0), (170.0, 110.0), (60.0, 300.0),
             (140.0, 130.0), (85.0, 220.0)]
    parts = [rect_part(i, *sizes[i % len(sizes)]) for i in range(52)]
    layouts = {
        tuple((p.part_id, p.sheet, p.transform) for p in pack(
            parts, PLAN_LIBRE,
            base_config(effort="normal", seed=seed, workers=2), RasterOracle,
        ).placements)
        for seed in (1, 2, 3, 4)
    }
    assert len(layouts) >= 2
```

  Si este test falla con un solo layout, es que con estas medidas la base ya iguala la cota por área y la tanda no corre: imprimir `cota_minima(parts, PLAN_LIBRE, 15.0)` y `pack(..., effort="rapido").sheets_used`; si coinciden, subir a 56 piezas (`range(56)`), que agrega área sin cambiar la mezcla, y volver a correr.

- Reemplazar `test_the_reported_time_grows_with_the_effort`:

```python
def test_the_reported_time_grows_with_the_effort():
    """Treinta círculos: entran 25 por placa, así que la base abre dos y la
    cota por área es una. Con diez, la base ya igualaba la cota, normal no
    buscaba nada y tardaba lo mismo que rápido."""
    parts = [circle_part(i, 90.0) for i in range(30)]
    quick = pack(parts, PLAN_LIBRE, base_config(effort="rapido"), RasterOracle)
    normal = pack(parts, PLAN_LIBRE, base_config(effort="normal"), RasterOracle)
    assert normal.seconds > quick.seconds
```

En `tests/engine/test_progreso.py`:

- Cambiar el import `from nesting.engine.packer import Avance, Cancelado, EFFORT_RESTARTS, pack` por `from nesting.engine.packer import Avance, Cancelado, pack` y agregar `from nesting.engine.cartera import planned_variants`.
- En `test_la_cantidad_de_intentos_se_sabe_desde_el_primer_aviso`, cambiar la aserción a `assert avances[0].intentos == planned_variants("normal", 1)` y en su docstring `Sale de EFFORT_RESTARTS` por `Sale de planned_variants`.
- Reemplazar `test_los_intentos_llegan_hasta_el_ultimo`:

```python
def test_los_intentos_llegan_hasta_el_ultimo():
    """Doce cuadrados de 400: cuatro por placa, tres placas, y la cota por
    área es dos, así que la tanda corre. Con cuatro cuadrados de 100 la base
    igualaba la cota y no había segundo intento que ver."""
    piezas = [cuadrado(i, lado=400.0) for i in range(12)]
    avances = []

    pack(piezas, PLAN_LIBRE, config(effort="normal"), fabrica(),
         progreso=lambda a: avances.append(a) or True)

    intentos = {a.intento for a in avances if not a.compactando}
    assert intentos == set(range(1, planned_variants("normal", 1) + 1))
```

- `test_cancelar_durante_la_recuperacion_levanta` sigue valiendo tal cual: el tramo final avisa una vez al entrar (`_Progress.final`) y después una vez por pieza que la recuperación intenta, como después del plan 2. Lo mismo `test_la_compactacion_avisa` y `test_la_compactacion_se_cancela` de `tests/engine/test_consultas.py`.

En `tests/engine/test_consultas.py` (del plan 2), en
`test_la_prevision_de_arranque_de_un_caso_a_mano`, el "normal son 3
intentos" pasa a ser "normal son `planned_variants('normal', 1)` pasadas":

```python
    assert initial_forecast(piezas, PLAN, cfg) == forecast_pack(
        10, 8, 1, planned_variants("normal", 1)
    )
```

(con `from nesting.engine.cartera import planned_variants` en los imports, y
el docstring corregido igual). `test_el_primer_aviso_trae_la_prevision_de_arranque`
sigue valiendo tal cual: el primer `Avance` de la cartera trae
`initial_forecast`. Correr `tests/engine/test_consultas.py` entero: cualquier
otra falla ahí que dependa de "3 intentos" se corrige igual, cambiando el 3
por `planned_variants`; una que dependa de cuándo avisa cada fase se revisa
contra `_Progress` (la base y el tramo final avisan por pieza intentada, con
el `aviso` de siempre; el tramo final, además, una vez al entrar y una al
terminar; las tandas, cada `QUERY_REPORT_EVERY` consultas).

En `tests/app/test_api_trabajos.py:186`, cambiar `assert visto["intentos"] == 12` por:

```python
    from nesting.engine.cartera import planned_variants
    assert visto["intentos"] == planned_variants("lento", 1)
```

- [ ] **Step 11: Correr los tests nuevos y la suite entera**

Run: `.venv/bin/pytest tests/engine/test_cartera.py tests/engine/test_effort.py tests/engine/test_progreso.py -v`
Expected: PASS

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos. En particular `tests/engine/test_recortes.py` y `tests/test_cli_full.py` siguen verdes sin tocarlos: `pack()` conserva la firma.

- [ ] **Step 12: Commit**

```bash
git add src/nesting/engine/cartera.py src/nesting/engine/packer.py src/nesting/engine/oracle.py \
        src/nesting/cli.py bench/calibrate.py tests/engine/test_cartera.py tests/engine/test_packer.py \
        tests/engine/test_effort.py tests/engine/test_progreso.py tests/engine/test_consultas.py \
        tests/app/test_api_trabajos.py
git commit -m "Motor: la cartera de variantes, con pares y perturbaciones, en un proceso"
```

---

### Task 6: Las tandas en paralelo

Cambia **dónde** corre cada variante de una tanda, no **cuáles**: con
`workers > 1`, un `ProcessPoolExecutor` con contexto `spawn`, creado la
primera vez que hace falta y reusado entre tandas. Cada proceso arma su
propio `MaskCache` y sus oráculos, manda sus consultas por una cola, mira un
`Event` compartido para cancelar y un `Value` compartido para cortar lo que
ya perdió. La base, la recuperación y la compactación siguen en el proceso
principal.

**Files:**
- Modify: `src/nesting/engine/cartera.py` (`_Evaluator` gana el pool; `_init_worker`, `_run_in_worker`)
- Modify: `src/nesting/engine/raster/oracle.py` (`RasterOracleFactory`)
- Modify: `src/nesting/cli.py` (`freeze_support`, la fábrica), `src/nesting_app/desktop.py` (`freeze_support`), `src/nesting_app/corredor.py` (la fábrica), `bench/run_bench.py` (la fábrica)
- Modify: `src/nesting_app/api.py` (`_avance_a_dict`), `src/nesting_app/web/app.js` (`textoDeAvance`)
- Test: `tests/engine/test_cartera_paralelo.py` (nuevo), `tests/engine/raster/test_fabrica.py` (nuevo), `tests/test_cli.py`, `tests/app/test_desktop.py`, `tests/app/test_api_trabajos.py`, `tests/app/test_web_javascript.py`

**Interfaces:**
- Consumes: todo lo de la Tarea 5; `Avance.combinaciones`, `combinaciones_hechas`, `placa_minima`.
- Produces:
  - `RasterOracleFactory(max_bytes: int = DEFAULT_CACHE_BUDGET_BYTES)` en `nesting.engine.raster.oracle`: invocable, devuelve un `RasterOracle` que comparte el `MaskCache` de la fábrica; se serializa sin su caché. Propiedad `cache -> MaskCache`.
  - `_Evaluator(config, factory, processes: int | None = None)` en `cartera`: con `processes` (o `config.workers`) mayor que 1 y tandas de más de una variante, evalúa en un pool `spawn`. Levanta `TypeError` si la fábrica no se puede serializar.
  - `POLL_SECONDS = 0.2` en `cartera`.
  - `_avance_a_dict` devuelve además `combinaciones`, `combinaciones_hechas`, `placa_minima`.

- [ ] **Step 1: Escribir los tests de la fábrica serializable, que fallan**

Crear `tests/engine/raster/test_fabrica.py`:

```python
"""La fábrica de oráculos que se puede mandar a otro proceso."""

import pickle

from nesting.engine.raster.oracle import RasterOracle, RasterOracleFactory


def test_cada_oraculo_de_una_fabrica_comparte_su_cache():
    fabrica = RasterOracleFactory()
    uno, otro = fabrica(), fabrica()
    assert isinstance(uno, RasterOracle)
    assert uno._cache is otro._cache is fabrica.cache


def test_viaja_sin_su_cache_y_del_otro_lado_arma_una_propia():
    """Un proceso `spawn` sólo recibe lo que se serializa. Mandar el caché
    lleno sería mandar cientos de MB que el otro proceso igual tiene que
    poder rehacer; mandarlo vacío es lo mismo que no mandarlo."""
    fabrica = RasterOracleFactory(max_bytes=1234)
    fabrica()  # llena el caché de este lado
    copia = pickle.loads(pickle.dumps(fabrica))
    assert copia._cache is None
    assert copia.cache is not fabrica.cache
    assert copia.cache._max_bytes == 1234
```

- [ ] **Step 2: Correr para verlos fallar**

Run: `.venv/bin/pytest tests/engine/raster/test_fabrica.py -v`
Expected: FAIL con `ImportError: cannot import name 'RasterOracleFactory'`

- [ ] **Step 3: Implementar `RasterOracleFactory`**

En `src/nesting/engine/raster/oracle.py`, agregar `DEFAULT_CACHE_BUDGET_BYTES` al import de `nesting.engine.raster.masks` y, al final del archivo:

```python
class RasterOracleFactory:
    """Fabrica `RasterOracle`s que comparten un `MaskCache`, y viaja a otros procesos.

    Lo que usaban la CLI y la interfaz -- `lambda: RasterOracle(cache=cache)`
    -- no se puede serializar, y un proceso creado con `spawn` sólo recibe
    lo que se serializa. Esta fábrica viaja SIN su caché: del otro lado arma
    uno propio la primera vez que se la usa. La cartera la manda una sola
    vez por proceso, en el inicializador del pool (`cartera._init_worker`),
    así que ese caché sirve para todas las variantes que ese proceso evalúe.
    """

    def __init__(self, max_bytes: int = DEFAULT_CACHE_BUDGET_BYTES) -> None:
        self._max_bytes = max_bytes
        self._cache: MaskCache | None = None

    @property
    def cache(self) -> MaskCache:
        if self._cache is None:
            self._cache = MaskCache(self._max_bytes)
        return self._cache

    def __call__(self) -> RasterOracle:
        return RasterOracle(cache=self.cache)

    def __getstate__(self) -> dict:
        return {"_max_bytes": self._max_bytes, "_cache": None}
```

Run: `.venv/bin/pytest tests/engine/raster/test_fabrica.py -v`
Expected: PASS, 2 tests

- [ ] **Step 4: Escribir los tests del paralelo, que fallan**

Crear `tests/engine/test_cartera_paralelo.py`:

```python
"""Las tandas en paralelo: el mismo resultado, y ningún proceso colgado."""

import multiprocessing

import pytest

from nesting.engine.cartera import (
    Variant,
    VariantSource,
    _Evaluator,
    _Progress,
    run_portfolio,
)
from nesting.engine.oracle import NestConfig
from nesting.engine.packer import Cancelado, pack
from nesting.engine.raster.masks import MaskCache
from nesting.engine.raster.oracle import RasterOracle, RasterOracleFactory
from nesting.model.part import Part
from nesting.model.sheet import Sheet, SheetSupply

PLAN = SheetSupply(stock=Sheet(1000.0, 1000.0, grain_tolerance=180.0), material_name="prueba")


def rect(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def siete():
    """El caso de `test_cartera.py`: la base abre dos placas, la cota es una."""
    return [rect(i, 400.0, 300.0) for i in range(7)]


def config(**cambios):
    base = dict(sep=8.0, margin=15.0, angles=(0.0, 90.0), mirror=False,
                resolution=4.0, effort="normal", seed=0, workers=4)
    base.update(cambios)
    return NestConfig(**base)


def sin_avance():
    return _Progress(None, totales=7, planned=5, initial_queries=1)


def test_el_pool_se_crea_con_spawn():
    """En Linux el contexto por omisión es `fork`; la spec pide que las tres
    plataformas se comporten igual."""
    assert _Evaluator(config(), RasterOracleFactory())._context.get_start_method() == "spawn"


def test_la_misma_tanda_da_lo_mismo_con_uno_y_con_cuatro_procesos():
    """El determinismo que la spec exige: el resultado no depende de cuándo
    termina cada proceso, porque se ordena por índice y se desempata por
    índice."""
    fuente = VariantSource(siete(), PLAN, config())
    tanda = fuente.batch(1, 4, fuente.base())

    def correr(procesos):
        with _Evaluator(config(), RasterOracleFactory(), processes=procesos) as evaluador:
            return evaluador.run(tanda, siete(), PLAN, 10**9, sin_avance())

    uno, cuatro = correr(1), correr(4)
    assert [(o.index, o.cost, o.packed.placements) for o in uno] == \
           [(o.index, o.cost, o.packed.placements) for o in cuatro]


def test_la_cartera_entera_da_lo_mismo_dos_veces_en_paralelo():
    una = run_portfolio(siete(), PLAN, config(effort="lento", workers=3), RasterOracleFactory())
    otra = run_portfolio(siete(), PLAN, config(effort="lento", workers=3), RasterOracleFactory())
    assert una.winner == otra.winner
    assert una.result.placements == otra.result.placements


def test_en_paralelo_tambien_se_corta_lo_que_ya_perdio():
    tanda = [Variant(1, "orden", tuple(siete())),
             Variant(2, "orden", tuple(reversed(siete())))]
    with _Evaluator(config(workers=2), RasterOracleFactory()) as evaluador:
        assert evaluador.run(tanda, siete(), PLAN, 0, sin_avance()) == []


def test_una_fabrica_que_no_viaja_se_rechaza_con_un_mensaje_claro():
    cache = MaskCache()
    tanda = [Variant(1, "orden", tuple(siete())),
             Variant(2, "orden", tuple(reversed(siete())))]
    with pytest.raises(TypeError, match="RasterOracleFactory"):
        with _Evaluator(config(workers=2), lambda: RasterOracle(cache=cache)) as evaluador:
            evaluador.run(tanda, siete(), PLAN, 10**9, sin_avance())


def test_las_consultas_de_todos_los_procesos_se_suman():
    avances = []
    pack(siete(), PLAN, config(workers=3), RasterOracleFactory(),
         progreso=lambda a: avances.append(a) or True)

    hechas = [a.consultas_hechas for a in avances]
    assert hechas == sorted(hechas), "la cuenta no puede retroceder"
    assert all(a.consultas_previstas >= a.consultas_hechas for a in avances)
    base = max(a.consultas_hechas for a in avances
               if not a.combinaciones and not a.compactando)
    de_tanda = [a for a in avances if a.combinaciones]
    assert de_tanda and de_tanda[-1].consultas_hechas > base, "la tanda tiene que sumar"


def test_cancelar_en_la_tanda_no_deja_ningun_proceso_vivo():
    def cortar_apenas_arranca_la_tanda(avance):
        return not avance.combinaciones

    with pytest.raises(Cancelado):
        pack(siete(), PLAN, config(workers=2), RasterOracleFactory(),
             progreso=cortar_apenas_arranca_la_tanda)

    assert multiprocessing.active_children() == []
```

- [ ] **Step 5: Correr para verlos fallar**

Run: `.venv/bin/pytest tests/engine/test_cartera_paralelo.py -v`
Expected: FAIL. `test_el_pool_se_crea_con_spawn` con `AttributeError: '_Evaluator' object has no attribute '_context'`; `test_la_misma_tanda...` con `TypeError: _Evaluator.__init__() got an unexpected keyword argument 'processes'`; `test_una_fabrica_que_no_viaja...` con `DID NOT RAISE`.

- [ ] **Step 6: El pool en `cartera.py`**

Agregar a los imports de `src/nesting/engine/cartera.py`:

```python
import multiprocessing
import pickle
import queue
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
```

Agregar después de `QUERY_REPORT_EVERY`:

```python
POLL_SECONDS = 0.2
"""Cada cuánto el proceso principal junta los avisos de los procesos y
avisa. Es también cuánto puede tardar en notarse un "cancelar"."""
```

Agregar antes de `class _Evaluator`:

```python
_worker: dict = {}
"""El estado de un proceso del pool: lo llena `_init_worker` una vez."""


def _init_worker(factory, cancel, best, reports) -> None:
    """Corre una vez en cada proceso nuevo del pool.

    La fábrica, el evento de cancelar, el mejor `placas_nuevas` y la cola de
    avisos llegan acá y no con cada variante: los objetos de sincronización
    de `multiprocessing` sólo se pueden pasar por herencia al crear el
    proceso, y la fábrica, pasada una sola vez, conserva su `MaskCache` entre
    todas las variantes que ese proceso evalúe.
    """
    _worker.update(factory=factory, cancel=cancel, best=best, reports=reports)


def _run_in_worker(variant: Variant, parts: Sequence[Part], supply: SheetSupply,
                   config: NestConfig) -> tuple[int, Outcome | None, int]:
    reports = _worker["reports"]
    last = [0]

    def on_queries(total: int) -> None:
        last[0] = total
        reports.put((variant.index, total))

    watch = _Watch(
        cancelled=_worker["cancel"].is_set,
        best_new_sheets=lambda: _worker["best"].value,
        on_queries=on_queries,
    )
    outcome = evaluate(variant, parts, supply, config, _worker["factory"], watch)
    # El total viaja también con el resultado: la cola es asíncrona, y el
    # último mensaje puede llegar después de que el principal vio terminar
    # a la variante.
    return variant.index, outcome, last[0]
```

Reemplazar `class _Evaluator` entera:

```python
class _Evaluator:
    """Evalúa tandas de variantes: acá mismo, o en un pool de procesos `spawn`.

    Con un proceso, o con una tanda de una sola variante, corre acá, una
    detrás de otra. Si no, en un `ProcessPoolExecutor` que se crea la
    primera vez que hace falta y se reusa entre tandas. Es un administrador
    de contexto para que el pool se cierre pase lo que pase -- cancelación
    incluida -- sin dejar ningún proceso vivo.
    """

    def __init__(self, config: NestConfig, factory: Callable[[], Oracle],
                 processes: int | None = None) -> None:
        self._config = config
        self._factory = factory
        self._processes = max(1, config.workers if processes is None else processes)
        # `spawn` en todas las plataformas: en Linux el por omisión es
        # `fork`, y un proceso hecho con fork hereda hilos y cerrojos a medio
        # tomar del principal (el servidor de la interfaz tiene varios).
        self._context = multiprocessing.get_context("spawn")
        self._pool: ProcessPoolExecutor | None = None
        self._cancel = None
        self._best = None
        self._reports = None

    def __enter__(self) -> "_Evaluator":
        return self

    def __exit__(self, *exc) -> bool:
        if self._pool is not None:
            # Primero el evento: un proceso a mitad de una variante lo ve en
            # su próxima consulta y levanta `Cancelado`, así que `shutdown`
            # no espera a que termine una pasada entera.
            self._cancel.set()
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None
            self._reports.close()
            self._reports.join_thread()
        return False

    def run(self, batch: Sequence[Variant], parts: Sequence[Part], supply: SheetSupply,
            best_new_sheets: int, progress: _Progress) -> list[Outcome]:
        """Los resultados de la tanda que no se cortaron, en orden de índice."""
        if self._processes == 1 or len(batch) <= 1:
            return self._run_here(batch, parts, supply, best_new_sheets, progress)
        return self._run_in_pool(batch, parts, supply, best_new_sheets, progress)

    def _run_here(self, batch, parts, supply, best_new_sheets, progress) -> list[Outcome]:
        mejor = best_new_sheets
        outcomes: list[Outcome] = []
        for variant in batch:
            outcome = evaluate(
                variant, parts, supply, self._config, self._factory,
                progress.watch(("variante", variant.index), lambda: mejor),
            )
            progress.variant_done(outcome)
            if outcome is not None:
                outcomes.append(outcome)
                mejor = min(mejor, outcome.cost.placas_nuevas)
        return outcomes

    def _start_pool(self) -> None:
        try:
            pickle.dumps(self._factory)
        except Exception as error:
            raise TypeError(
                "para probar variantes en paralelo, la fábrica de oráculos tiene "
                "que poder mandarse a otro proceso, y ésta no se puede serializar "
                "(una lambda que captura un MaskCache no se puede). Usá "
                "nesting.engine.raster.oracle.RasterOracleFactory, una clase, o "
                "NestConfig(workers=1)."
            ) from error
        self._cancel = self._context.Event()
        self._best = self._context.Value("q", 0)
        self._reports = self._context.Queue()
        self._pool = ProcessPoolExecutor(
            max_workers=self._processes,
            mp_context=self._context,
            initializer=_init_worker,
            initargs=(self._factory, self._cancel, self._best, self._reports),
        )

    def _drain(self, progress: _Progress) -> None:
        while True:
            try:
                index, total = self._reports.get_nowait()
            except queue.Empty:
                return
            progress.record(("variante", index), total)

    def _run_in_pool(self, batch, parts, supply, best_new_sheets, progress) -> list[Outcome]:
        if self._pool is None:
            self._start_pool()
        # "Cortar lo que ya perdió": el menor `placas_nuevas` terminado. Sólo
        # lo escribe este proceso, y sólo para bajarlo; los del pool lo leen.
        self._best.value = best_new_sheets
        pending = {
            self._pool.submit(_run_in_worker, variant, list(parts), supply, self._config)
            for variant in batch
        }
        outcomes: list[Outcome] = []
        while pending:
            done, pending = wait(pending, timeout=POLL_SECONDS, return_when=FIRST_COMPLETED)
            self._drain(progress)
            for future in done:
                index, outcome, total = future.result()
                progress.record(("variante", index), total)
                progress.variant_done(outcome)
                if outcome is not None:
                    outcomes.append(outcome)
                    if outcome.cost.placas_nuevas < self._best.value:
                        self._best.value = outcome.cost.placas_nuevas
            if not done:
                # Nadie terminó en este intervalo, pero las consultas sí
                # subieron, y sólo avisando se entera el principal de que le
                # pidieron cancelar.
                progress.emit()
        self._drain(progress)
        return sorted(outcomes, key=lambda o: o.index)
```

`run_portfolio` no cambia: ya entra al `with _Evaluator(config, oracle_factory)`.

- [ ] **Step 7: Correr los tests del paralelo**

Run: `.venv/bin/pytest tests/engine/test_cartera_paralelo.py tests/engine/test_cartera.py -v`
Expected: PASS. Los de `test_cartera.py` con `workers >= 2` ahora pasan por el pool (tardan unos segundos más, lo que cuesta arrancar los procesos).

- [ ] **Step 8: `freeze_support` y la fábrica en los que llaman al motor**

Escribir primero los tests. En `tests/test_cli.py`, al final:

```python
def test_freeze_support_es_lo_primero_que_hace_main(monkeypatch):
    """PyInstaller lo exige para `spawn`: sin esto, cada proceso del pool
    del ejecutable vuelve a arrancar la CLI entera en vez de ser un proceso
    del pool. En el repo funciona igual con o sin él, por eso hace falta un
    test que lo mire."""
    import multiprocessing

    import nesting.cli

    llamadas = []
    monkeypatch.setattr(multiprocessing, "freeze_support", lambda: llamadas.append(1))
    with pytest.raises(SystemExit):
        nesting.cli.main(["--no-existe-esta-opcion"])
    assert llamadas == [1]
```

En `tests/app/test_desktop.py`, al final:

```python
def test_freeze_support_es_lo_primero_que_hace_main(monkeypatch):
    """El ejecutable arranca por acá. Un proceso `spawn` del pool vuelve a
    ejecutar este mismo binario con una marca que sólo `freeze_support`
    entiende: tiene que llamarse antes de que argparse la rechace."""
    import multiprocessing

    llamadas = []
    monkeypatch.setattr(multiprocessing, "freeze_support", lambda: llamadas.append(1))
    with pytest.raises(SystemExit):
        desktop.main(["--no-existe-esta-opcion"])
    assert llamadas == [1]
```

Run: `.venv/bin/pytest tests/test_cli.py tests/app/test_desktop.py -k freeze -v`
Expected: FAIL con `assert [] == [1]`

En `src/nesting/cli.py`: agregar `import multiprocessing` a los imports; como primera línea de `main()`:

```python
    # Antes que nada, incluido argparse: en el ejecutable congelado, un
    # proceso del pool arranca este mismo binario con argumentos que sólo
    # `freeze_support` entiende. Fuera de un ejecutable no hace nada.
    multiprocessing.freeze_support()
```

reemplazar `from nesting.engine.raster.masks import MaskCache` y `from nesting.engine.raster.oracle import RasterOracle` por `from nesting.engine.raster.oracle import RasterOracleFactory`, y el bloque que arma el caché y llama a `pack` (hoy `cache = MaskCache()` ... `result = pack(parts, supply, config, lambda: RasterOracle(cache=cache))`) por:

```python
        # Una sola fábrica para todo el `pack()`: sus oráculos comparten un
        # `MaskCache`, porque las máscaras dependen sólo de (pieza, ángulo,
        # espejo, resolución, sep) y nunca del estado de la placa. Y se puede
        # mandar a los procesos de la cartera, que una lambda no.
        result = pack(parts, supply, config, RasterOracleFactory())
```

(el `supply` lo arma `a_supply` desde el plan 1; esa línea no cambia).

En `src/nesting_app/desktop.py`: agregar `import multiprocessing` y como primera línea de `main()`:

```python
    # Antes que nada, incluido argparse: ver `nesting.cli.main`.
    multiprocessing.freeze_support()
```

En `src/nesting_app/corredor.py`: cambiar los imports de `MaskCache` y `RasterOracle` por `from nesting.engine.raster.oracle import RasterOracleFactory`, borrar `cache = MaskCache()` y cambiar la llamada a:

```python
        resultado = pack(
            piezas, supply, config, RasterOracleFactory(), progreso=progreso
        )
```

En `bench/run_bench.py`, `_new_raster_factory` pasa a devolver `RasterOracleFactory()` (el docstring sigue valiendo: una fábrica nueva por archivo, con su caché), y el import de `RasterOracle` se cambia por el de `RasterOracleFactory`.

Run: `grep -rn "lambda: RasterOracle" src bench`
Expected: nada. Si aparecen otras (las de `probe_query_seconds` en `corredor.estimar_segundos` y en `bench/calibrate.py`, del plan 2), cambiarlas también por `RasterOracleFactory()`, que es lo mismo con un caché nuevo, y sacar los imports de `MaskCache`/`RasterOracle` que queden sin uso.

- [ ] **Step 9: El avance de la cartera en la API y en la pantalla**

Tests primero. En `tests/app/test_api_trabajos.py`, en `test_el_avance_se_ve_mientras_corre`, después de la aserción de `intentos`:

```python
    assert {"combinaciones", "combinaciones_hechas", "placa_minima"} <= set(visto)
```

En `tests/app/test_web_javascript.py`, al final:

```python
def test_el_avance_de_la_cartera_dice_combinaciones_y_placa_minima(js):
    """En paralelo, "ubicadas 12 de 57" deja de tener sentido: hay doce
    variantes a la vez, cada una con su cuenta."""
    cuerpo = _cuerpo_de_funcion(js, "textoDeAvance")
    assert "a.combinaciones" in cuerpo
    assert "Probando combinaciones" in cuerpo
    assert "a.combinaciones_hechas" in cuerpo
    assert "placa mínima hasta ahora" in cuerpo
    assert "a.placa_minima" in cuerpo
    assert cuerpo.index("a.compactando") < cuerpo.index("a.combinaciones"), (
        "compactando manda: es el tramo final, después de la cartera"
    )
```

Run: `.venv/bin/pytest tests/app/test_api_trabajos.py::test_el_avance_se_ve_mientras_corre tests/app/test_web_javascript.py -k "avance" -v`
Expected: FAIL en los dos nuevos.

En `src/nesting_app/api.py`, `_avance_a_dict` gana tres claves (junto a las que agregó el plan 2):

```python
            "combinaciones": avance.combinaciones,
            "combinaciones_hechas": avance.combinaciones_hechas,
            "placa_minima": avance.placa_minima,
```

En `src/nesting_app/web/app.js`, en `textoDeAvance`, agregar esta rama justo después de la de `compactando` y sin tocar el resto de la función (que después del plan 2 puede traer más cosas):

```js
  if (a.combinaciones) {
    return (
      `Probando combinaciones ${a.combinaciones_hechas} de ${a.combinaciones} · ` +
      `placa mínima hasta ahora: ${a.placa_minima}`
    );
  }
```

- [ ] **Step 10: Correr la suite entera**

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos.

- [ ] **Step 11: Commit**

```bash
git add src/nesting/engine/cartera.py src/nesting/engine/raster/oracle.py src/nesting/cli.py \
        src/nesting_app/desktop.py src/nesting_app/corredor.py src/nesting_app/api.py \
        src/nesting_app/web/app.js bench/run_bench.py \
        tests/engine/test_cartera_paralelo.py tests/engine/raster/test_fabrica.py tests/test_cli.py \
        tests/app/test_desktop.py tests/app/test_api_trabajos.py tests/app/test_web_javascript.py
git commit -m "Motor: las tandas de la cartera en paralelo, con spawn, cancelables y sin procesos colgados"
```

---

### Task 7: Núcleos

Cuántos núcleos usar pasa a ser un parámetro de la corrida: `NestParams.nucleos`
(`None` es "el valor por omisión de esta máquina"), `--nucleos` en la CLI, un
desplegable debajo de Esfuerzo en la pantalla y la ruta `GET /api/sistema`
que le dice a la pantalla cuántos hay. El tope depende de los núcleos **y** de
la memoria: cada proceso de la cartera lleva su propio `MaskCache`.

**Files:**
- Create: `src/nesting/engine/workers.py`
- Modify: `src/nesting/engine/cartera.py` (`wall_passes`)
- Modify: `src/nesting/params.py`, `src/nesting/cli.py`, `src/nesting_app/api.py`, `src/nesting_app/corredor.py`
- Modify: `corredor.estimar_segundos` del plan 2 (Paso 11), que pasa a usar `cartera.wall_forecast`
- Modify: `src/nesting_app/web/index.html`, `src/nesting_app/web/app.js`, `src/nesting_app/web/app.css`, `src/nesting_app/web/info.js`
- Test: `tests/engine/test_workers.py` (nuevo), `tests/test_params.py`, `tests/test_cli.py`, `tests/app/test_api_trabajos.py`, `tests/app/test_corredor.py`, `tests/app/test_web_estatico.py`, `tests/app/test_web_javascript.py`

**Interfaces:**
- Consumes: `NestConfig.workers` (Tarea 5), `EFFORT_BATCHES` (Tarea 5); del plan 2, `initial_forecast`, `_usable_area`, `prevision.estimate_sheets`, `prevision.forecast_greedy_pass` y `corredor.estimar_segundos`.
- Produces:
  - En `nesting.engine.workers`: `MEMORY_PER_WORKER_BYTES`, `MEMORY_SHARE = 0.5`, `cpu_count() -> int`, `total_memory_bytes() -> int | None`, `worker_cap(cpus: int, memory: int | None) -> int`, `default_workers(cpus: int, cap: int) -> int`, `Machine(cpus: int, cap: int, default: int)` y `machine() -> Machine`.
  - `cartera.wall_passes(effort: str, workers: int) -> float` y `cartera.wall_forecast(parts, supply, config) -> float`.
  - `NestParams.nucleos: int | None = None`; `validar` exige `nucleos >= 1`; `FLAG_POR_CAMPO["nucleos"] = "--nucleos"`; `nucleos_efectivos(p: NestParams) -> tuple[int, str | None]` (el valor a usar y, si hubo que recortarlo, el aviso); `a_config` pone `workers`.
  - `ParamsEntrada.nucleos: int | None = None`; `GET /api/sistema -> {"nucleos": int, "tope": int, "omision": int}`.
  - En la pantalla: `<select id="nucleos">`, `<span id="nucleos-total">`, `cargarSistema()` en `app.js`, clave `"nucleos"` en `info.js`.

- [ ] **Step 1: Escribir los tests de `workers.py`, que fallan**

Crear `tests/engine/test_workers.py`:

```python
"""Cuántos núcleos puede usar la cartera en esta máquina."""

from nesting.engine import workers
from nesting.engine.workers import (
    MEMORY_PER_WORKER_BYTES,
    Machine,
    default_workers,
    machine,
    worker_cap,
)

GB = 1024**3


def test_con_memoria_de_sobra_el_tope_son_los_nucleos():
    assert worker_cap(14, 64 * GB) == 14


def test_con_poca_memoria_el_tope_lo_pone_la_memoria():
    """La mitad de la memoria, dividida por lo que ocupa un proceso."""
    memoria = 12 * MEMORY_PER_WORKER_BYTES * 2
    assert worker_cap(14, memoria) == 12


def test_el_tope_nunca_baja_de_uno():
    assert worker_cap(14, 1) == 1
    assert worker_cap(1, 64 * GB) == 1


def test_sin_saber_la_memoria_el_tope_son_los_nucleos():
    assert worker_cap(8, None) == 8


def test_por_omision_se_dejan_dos_nucleos_libres():
    assert default_workers(14, 14) == 12
    assert default_workers(14, 10) == 10, "y nunca por encima del tope"
    assert default_workers(2, 2) == 1
    assert default_workers(1, 1) == 1


def test_la_maquina_se_lee_una_vez_con_las_tres_cifras(monkeypatch):
    monkeypatch.setattr(workers, "cpu_count", lambda: 14)
    monkeypatch.setattr(workers, "total_memory_bytes", lambda: 64 * GB)
    assert machine() == Machine(cpus=14, cap=14, default=12)


def test_la_memoria_de_esta_maquina_se_puede_leer():
    """En macOS y Linux por `os.sysconf`, en Windows por
    `GlobalMemoryStatusEx`. Si una plataforma no la da, el tope cae a la
    cantidad de núcleos, pero en las tres donde corre esto sí la da."""
    memoria = workers.total_memory_bytes()
    assert memoria is not None and memoria > GB
```

- [ ] **Step 2: Correr para verlos fallar**

Run: `.venv/bin/pytest tests/engine/test_workers.py -v`
Expected: FAIL con `ImportError: cannot import name 'workers' from 'nesting.engine'`

- [ ] **Step 3: Escribir `src/nesting/engine/workers.py`**

```python
"""Cuántos procesos puede correr la cartera en esta máquina.

El tope no es sólo la cantidad de núcleos: cada proceso arma su propio
`MaskCache` y sus grillas de placa, así que doce procesos en una máquina de
8 GB la dejarían sin memoria antes de terminar la primera tanda. No se
agregan dependencias para leer la memoria: `os.sysconf` en macOS y Linux,
`GlobalMemoryStatusEx` por `ctypes` en Windows.
"""

import os
import sys
from dataclasses import dataclass

MEMORY_PER_WORKER_BYTES = 400 * 1024 * 1024
"""Lo que ocupa, como mucho, un proceso de la cartera.

El `MaskCache` tiene un presupuesto de 256 MB (`DEFAULT_CACHE_BUDGET_BYTES`),
y a eso se suman las grillas de la placa (la del oráculo y las
correlaciones de la búsqueda, del orden de decenas de MB a 1 mm/px en la
placa más grande del catálogo) y el propio intérprete con numpy, scipy y
shapely cargados. MEDIDO en la Tarea 7, Paso 4: ver el número que quedó
escrito ahí; si el pico medido superó 400 MB, este valor ya se subió al
pico redondeado hacia arriba a 50 MB.
"""

MEMORY_SHARE = 0.5
"""Qué parte de la memoria total se deja usar a la cartera. La otra mitad es
del sistema, de la interfaz y de lo que el usuario tenga abierto."""


@dataclass(frozen=True)
class Machine:
    cpus: int
    cap: int
    default: int


def cpu_count() -> int:
    return os.cpu_count() or 1


def total_memory_bytes() -> int | None:
    """La memoria física total, o None si la plataforma no la dice."""
    if sys.platform == "win32":
        return _windows_total_memory()
    try:
        return int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (ValueError, OSError, AttributeError):
        return None


def _windows_total_memory() -> int | None:
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return int(status.ullTotalPhys)


def worker_cap(cpus: int, memory: int | None) -> int:
    """El máximo de procesos: los núcleos, o lo que entra en la mitad de la memoria."""
    by_memory = cpus if memory is None else int(memory * MEMORY_SHARE // MEMORY_PER_WORKER_BYTES)
    return max(1, min(cpus, by_memory))


def default_workers(cpus: int, cap: int) -> int:
    """Todos menos dos, para que la máquina se pueda seguir usando; nunca más que el tope."""
    return max(1, min(cpus - 2, cap))


def machine() -> Machine:
    cpus = cpu_count()
    cap = worker_cap(cpus, total_memory_bytes())
    return Machine(cpus=cpus, cap=cap, default=default_workers(cpus, cap))
```

Run: `.venv/bin/pytest tests/engine/test_workers.py -v`
Expected: PASS, 7 tests

- [ ] **Step 4: Medir lo que ocupa un proceso y dejar el número**

Correr, con la banqueta si está y con la muestra si no:

```bash
.venv/bin/python bench/make_sample.py
.venv/bin/python - <<'PY'
import resource, sys
from pathlib import Path
from nesting.engine.cartera import run_portfolio
from nesting.engine.oracle import NestConfig
from nesting.engine.raster.oracle import RasterOracleFactory
from nesting.io.ai_reader import read_ai
from nesting.io.dxf_reader import read_dxf
from nesting.model.sheet import Sheet, SheetSupply
from nesting.pipeline import prepare_parts

banqueta = Path("bench/files/banqueta-alta.ai")
if banqueta.exists():
    piezas, _, _ = prepare_parts(read_ai(banqueta))
    placa = Sheet(1220.0, 2440.0, grain_tolerance=180.0)
    angulos = tuple(i * 45.0 for i in range(8))
else:
    from nesting.engine.packer import replicate
    piezas, _, _ = prepare_parts(read_dxf(Path("bench/files/muestra.dxf")))
    piezas = replicate(piezas, 6)
    placa = Sheet(1830.0, 2600.0, grain_tolerance=180.0)
    angulos = (0.0, 90.0, 180.0, 270.0)
config = NestConfig(sep=8.0, margin=5.0, angles=angulos, mirror=True,
                    resolution=1.0, effort="normal", workers=2)
run_portfolio(piezas, SheetSupply(stock=placa), config, RasterOracleFactory())
pico = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
# macOS da bytes; Linux da kilobytes.
mb = pico / 2**20 if sys.platform == "darwin" else pico / 2**10
print(f"pico de un proceso de la cartera: {mb:.0f} MB")
PY
```

Expected: una línea `pico de un proceso de la cartera: N MB`. Escribir ese
número y la fecha en el docstring de `MEMORY_PER_WORKER_BYTES` (reemplazar la
frase "ver el número que quedó escrito ahí" por "medido: N MB sobre
<archivo>, 1 mm/px, el AAAA-MM-DD"). Si `N > 400`, cambiar el valor a `N`
redondeado hacia arriba a un múltiplo de 50 MB y volver a correr
`tests/engine/test_workers.py`.

- [ ] **Step 5: `nucleos` en los parámetros, tests primero**

Agregar a `tests/test_params.py`:

```python
from nesting.engine import workers
from nesting.params import nucleos_efectivos


def test_nucleos_arranca_en_el_valor_de_la_maquina():
    assert NestParams(material="mdf18").nucleos is None


@pytest.mark.parametrize("valor", [0, -2])
def test_nucleos_tiene_que_ser_al_menos_uno(valor):
    with pytest.raises(ParamsInvalidosError) as info:
        validar(NestParams(material="mdf18", nucleos=valor))
    assert info.value.rota.campo == "nucleos"
    assert mensaje_cli(info.value.rota).startswith("--nucleos tiene que ser >= 1")


def test_sin_nucleos_se_usa_el_valor_por_omision(monkeypatch):
    monkeypatch.setattr(workers, "machine", lambda: workers.Machine(14, 14, 12))
    assert nucleos_efectivos(NestParams(material="mdf18")) == (12, None)


def test_por_encima_del_tope_se_recorta_con_un_aviso(monkeypatch):
    monkeypatch.setattr(workers, "machine", lambda: workers.Machine(14, 10, 10))
    valor, aviso = nucleos_efectivos(NestParams(material="mdf18", nucleos=16))
    assert valor == 10
    assert "16" in aviso and "10" in aviso


def test_a_config_lleva_los_nucleos_al_motor(monkeypatch):
    monkeypatch.setattr(workers, "machine", lambda: workers.Machine(14, 14, 12))
    assert a_config(NestParams(material="mdf18", nucleos=3)).workers == 3
    assert a_config(NestParams(material="mdf18")).workers == 12
```

(`pytest`, `NestParams`, `ParamsInvalidosError`, `validar`, `mensaje_cli` y
`a_config` ya están importados en ese archivo; si alguno falta, sumarlo al
import de `nesting.params`.)

Run: `.venv/bin/pytest tests/test_params.py -k nucleos -v`
Expected: FAIL con `ImportError: cannot import name 'nucleos_efectivos'`

En `src/nesting/params.py`:

- Agregar `from nesting.engine import workers` a los imports.
- En `NestParams`, después del último campo (el plan 1 dejó `veta` al final):

```python
    nucleos: int | None = None
    """Cuántos núcleos usa la cartera. `None` es el valor por omisión de la
    máquina (`workers.machine().default`): todos menos dos, con el tope por
    memoria. Más núcleos prueban más combinaciones en el mismo tiempo."""
```

- En `FLAG_POR_CAMPO`, agregar `"nucleos": "--nucleos",`.
- En `validar`, después de la regla de `resolucion`:

```python
    if p.nucleos is not None and p.nucleos < 1:
        raise ParamsInvalidosError(ReglaRota("nucleos", ">= 1", p.nucleos))
```

- Agregar la función:

```python
def nucleos_efectivos(p: NestParams) -> tuple[int, str | None]:
    """Los núcleos que de verdad se usan, y el aviso si hubo que recortar.

    Un valor por encima del tope se acepta y se recorta al tope, con un
    aviso: rechazarlo haría que el mismo pedido ande en una máquina y falle
    en otra, y el usuario no eligió mal, eligió en otra computadora.
    """
    maquina = workers.machine()
    if p.nucleos is None:
        return maquina.default, None
    if p.nucleos > maquina.cap:
        return maquina.cap, (
            f"se pidieron {p.nucleos} núcleos y esta máquina da para "
            f"{maquina.cap} (por la cantidad de núcleos y la memoria): se "
            f"usan {maquina.cap}."
        )
    return p.nucleos, None
```

- En `a_config`, agregar `workers=nucleos_efectivos(p)[0],` a los argumentos de `NestConfig`.

Run: `.venv/bin/pytest tests/test_params.py -v`
Expected: PASS

- [ ] **Step 6: `--nucleos` en la CLI, tests primero**

Agregar a `tests/test_cli.py`:

```python
def test_nucleos_cero_es_un_error_de_entrada(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 100)])
    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--nucleos", "0", "-o", tmp_path / "out.dxf"])
    assert code == 1
    assert "--nucleos tiene que ser >= 1" in capsys.readouterr().err


def test_nucleos_de_mas_se_recortan_con_un_aviso(tmp_path, capsys, monkeypatch):
    from nesting.engine import workers

    monkeypatch.setattr(workers, "machine", lambda: workers.Machine(4, 2, 2))
    source = write_input(tmp_path, [(0, 0, 100)])
    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--esfuerzo", "rapido", "--nucleos", "9", "-o", tmp_path / "out.dxf"])
    assert code == 0
    salida = capsys.readouterr().out
    assert "aviso: se pidieron 9 núcleos" in salida
```

Run: `.venv/bin/pytest tests/test_cli.py -k nucleos -v`
Expected: FAIL (argparse no conoce `--nucleos`: sale con código 1 pero por "unrecognized arguments", y el segundo test falla por el mismo motivo).

En `src/nesting/cli.py`:

- Agregar al parser, después de `--esfuerzo`:

```python
    parser.add_argument("--nucleos", type=int, default=None,
                        help="cuántos núcleos usar para probar combinaciones en "
                             "paralelo (por omisión, todos menos dos)")
```

- En el `NestParams(...)` que `main` arma para `validar` (después del plan 1
  ya está guardado en una variable para `a_supply`; si todavía se construye
  adentro de la llamada, sacarlo a `params = NestParams(...)` y pasar
  `params`), agregar `nucleos=args.nucleos,`.
- Importar `nucleos_efectivos` de `nesting.params`, y en el `NestConfig(...)`
  de `main` agregar `workers=nucleos,`, con estas dos líneas justo antes:

```python
    nucleos, aviso_nucleos = nucleos_efectivos(params)
    if aviso_nucleos is not None:
        print(f"aviso: {aviso_nucleos}")
```

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 7: `/api/sistema`, `ParamsEntrada.nucleos` y el aviso del corredor, tests primero**

Agregar a `tests/app/test_api_trabajos.py`:

```python
def test_el_sistema_dice_nucleos_tope_y_omision(cliente, monkeypatch):
    from nesting.engine import workers

    monkeypatch.setattr(workers, "machine", lambda: workers.Machine(14, 12, 12))
    assert cliente.get("/api/sistema").json() == {"nucleos": 14, "tope": 12, "omision": 12}


def test_nucleos_viaja_hasta_los_parametros():
    from nesting_app.api import ParamsEntrada

    assert ParamsEntrada(material="mdf18", nucleos=3).a_params().nucleos == 3
    assert ParamsEntrada(material="mdf18").a_params().nucleos is None


def test_nucleos_cero_se_rechaza_debajo_de_su_campo(cliente, tmp_path):
    fuente_id = fuente_de(cliente, tmp_path)
    respuesta = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id,
        "params": {"material": "mdf18", "esfuerzo": "rapido", "nucleos": 0},
    })
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["campo"] == "nucleos"
```

y, en `test_el_avance_se_ve_mientras_corre`, cambiar la aserción de la Tarea 5 por:

```python
    from nesting.engine import workers
    from nesting.engine.cartera import planned_variants
    assert visto["intentos"] == planned_variants("lento", workers.machine().default)
```

Agregar a `tests/app/test_corredor.py`:

```python
def test_los_nucleos_recortados_quedan_en_los_avisos(tmp_path, deposito, monkeypatch):
    from nesting.engine import workers

    monkeypatch.setattr(workers, "machine", lambda: workers.Machine(4, 2, 2))
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)]))
    carpeta = tmp_path / "salida"
    carpeta.mkdir()

    resultado = corredor.acomodar(fuente, params(nucleos=9), lambda a: True, carpeta)

    assert any("se pidieron 9 núcleos" in aviso for aviso in resultado.avisos)
```

Run: `.venv/bin/pytest tests/app/test_api_trabajos.py tests/app/test_corredor.py -k "nucleos or sistema" -v`
Expected: FAIL (404 en `/api/sistema`; `ParamsEntrada` no tiene `nucleos`; sin aviso).

En `src/nesting_app/api.py`:

- Agregar `from nesting.engine import workers` a los imports.
- En `ParamsEntrada`, después del último campo: `nucleos: int | None = None`, y en `a_params` pasar `nucleos=self.nucleos,`.
- En `crear_app`, antes de la sección de materiales:

```python
    # --- sistema ------------------------------------------------------------

    @app.get("/api/sistema")
    def sistema() -> dict:
        """Cuántos núcleos hay, hasta cuántos se pueden usar y cuántos por omisión.

        El tope sale de los núcleos y de la memoria (`nesting.engine.workers`):
        la pantalla lo usa como último valor del desplegable.
        """
        maquina = workers.machine()
        return {"nucleos": maquina.cpus, "tope": maquina.cap, "omision": maquina.default}
```

En `src/nesting_app/corredor.py`: importar `nucleos_efectivos` de `nesting.params` y, justo después de `config = a_config(params)`:

```python
        _, aviso_nucleos = nucleos_efectivos(params)
        if aviso_nucleos is not None:
            avisos.append(aviso_nucleos)
```

Run: `.venv/bin/pytest tests/app/test_api_trabajos.py tests/app/test_corredor.py -v`
Expected: PASS

- [ ] **Step 8: El control en la pantalla, tests primero**

En `tests/app/test_web_estatico.py`: agregar `"nucleos", "nucleos-total"` a `IDS_OBLIGATORIOS`, `"nucleos"` a la tupla de `test_todo_campo_tiene_su_etiqueta`, y al final:

```python
def test_nucleos_va_debajo_de_esfuerzo(html):
    assert html.index('id="esfuerzo"') < html.index('id="nucleos"') < html.index('id="posiciones"')


def test_nucleos_tiene_su_boton_de_informacion(html):
    assert 'data-info="nucleos"' in html


def test_los_textos_de_esfuerzo_ya_no_hablan_de_pasadas_fijas(html):
    """Normal y lento dejaron de ser "tres" y "doce" pasadas: ahora son
    tandas de tantas combinaciones como núcleos."""
    select = html[html.index('id="esfuerzo"'):html.index("</select>", html.index('id="esfuerzo"'))]
    assert "tres pasadas" not in select and "doce pasadas" not in select
    assert "Rápido — una pasada" in select
    assert "Normal — una tanda de combinaciones" in select
    assert "Lento — tres tandas de combinaciones" in select
```

En `tests/app/test_web_javascript.py`: agregar `"nucleos"` a `CLAVES_CON_GLOBO`, `"/api/sistema"` a la lista de `test_usa_la_ruta_que_la_api_expone`, y al final:

```python
def test_el_desplegable_de_nucleos_va_de_uno_al_tope_y_arranca_en_la_omision(js):
    cuerpo = _cuerpo_de_funcion(js, "cargarSistema")
    assert '"/api/sistema"' in cuerpo
    assert "datos.tope" in cuerpo
    assert "datos.omision" in cuerpo
    assert "datos.nucleos" in cuerpo
    assert re.search(r"for\s*\(\s*let\s+n\s*=\s*1\s*;\s*n\s*<=\s*datos\.tope", cuerpo), cuerpo


def test_los_nucleos_viajan_con_los_parametros(js):
    cuerpo = _cuerpo_de_funcion(js, "parametros")
    assert re.search(r'nucleos:\s*Number\(\$\("nucleos"\)\.value\)\s*\|\|\s*null', cuerpo), cuerpo


def test_la_pantalla_pide_el_sistema_al_arrancar(js):
    limpio = _sin_comentarios(js)
    assert re.search(r"^cargarSistema\(\)\.catch\(", limpio, re.M), (
        "sin esto el desplegable queda vacío y Acomodar manda nucleos: null"
    )
```

Run: `.venv/bin/pytest tests/app/test_web_estatico.py tests/app/test_web_javascript.py -v`
Expected: FAIL en los tests nuevos y en los parametrizados por `nucleos`.

En `src/nesting_app/web/index.html`, cambiar las opciones de Esfuerzo:

```html
          <option value="rapido" selected>Rápido — una pasada</option>
          <option value="normal">Normal — una tanda de combinaciones</option>
          <option value="lento">Lento — tres tandas de combinaciones</option>
```

y agregar, justo después del `</div>` que cierra el campo de Esfuerzo:

```html
    <div class="campo">
      <div class="titulo-campo">
        <label class="etiqueta" for="nucleos">Núcleos</label>
        <button type="button" class="boton-info" data-info="nucleos" aria-label="Qué es Núcleos" aria-expanded="false"><svg viewBox="0 0 16 16" class="icono" stroke-linecap="round" aria-hidden="true"><circle cx="8" cy="8" r="6.25"></circle><path d="M8 7.5v3.5"></path><path d="M8 5v.01"></path></svg></button>
      </div>
      <div class="fila fila-nucleos">
        <div class="desplegable">
          <select id="nucleos" class="control"></select>
          <svg viewBox="0 0 16 16" class="icono flecha" aria-hidden="true"><path d="M4 6.5l4 4 4-4"></path></svg>
        </div>
        <span id="nucleos-total" class="unidad"></span>
      </div>
    </div>
```

En `src/nesting_app/web/app.css`, después de `.fila > .campo { ... }`:

```css
/* "[ 12 ▾ ] de 14": el texto al lado del desplegable, centrado con él. */
.fila-nucleos { align-items: center; }
```

En `src/nesting_app/web/app.js`, en `parametros()`, agregar después de `esfuerzo`:

```js
    nucleos: Number($("nucleos").value) || null,
```

y en la sección de arranque, después de `refrescarMateriales`:

```js
// Cuántos núcleos hay y hasta cuántos se pueden usar. Si la ruta falla, el
// desplegable queda vacío y `parametros()` manda `null`: el servidor usa
// su valor por omisión, que es el mismo que este desplegable mostraría.
async function cargarSistema() {
  const datos = await apiJson("/api/sistema");
  const select = $("nucleos");
  select.innerHTML = "";
  for (let n = 1; n <= datos.tope; n++) {
    const opcion = document.createElement("option");
    opcion.value = String(n);
    opcion.textContent = String(n);
    select.append(opcion);
  }
  select.value = String(datos.omision);
  $("nucleos-total").textContent = `de ${datos.nucleos}`;
}
```

y al final del archivo, después del `refrescarMateriales().catch(...)`:

```js
cargarSistema().catch((error) =>
  mostrarError("No se pudo saber cuántos núcleos tiene la máquina", error.message)
);
```

En `src/nesting_app/web/info.js`, agregar a `TEXTOS` (una línea, como las demás) y reescribir la de `esfuerzo`:

```js
  "esfuerzo": "Cuántas maneras de acomodar prueba antes de quedarse con la mejor: Rápido prueba una, Normal una tanda de tantas como núcleos, Lento tres tandas. Más esfuerzo nunca da un resultado peor, pero tarda más.",
  "nucleos": "Más núcleos prueban más combinaciones en el mismo tiempo. Dejá alguno libre si vas a usar la computadora mientras acomoda.",
```

- [ ] **Step 9: Correr los tests de la pantalla**

Run: `.venv/bin/pytest tests/app/test_web_estatico.py tests/app/test_web_javascript.py -v`
Expected: PASS. Si `test_estan_las_diez_claves_y_ninguna_de_mas` falla, es sólo porque la lista `CLAVES_CON_GLOBO` y `TEXTOS` quedaron distintas: tienen que tener las mismas claves (las del plan 1 más `"nucleos"`).

- [ ] **Step 10: `wall_passes` y `wall_forecast`, tests primero**

Agregar a `tests/engine/test_cartera.py`:

```python
import pytest

from nesting.engine.cartera import wall_forecast, wall_passes


def test_las_pasadas_de_reloj_multiplican_por_la_tanda_y_dividen_por_n():
    """Spec 6: el tiempo estimado previo multiplica por las variantes de la
    tanda y divide por N. Con la tanda de N variantes en N núcleos, cada
    tanda cuesta una pasada de reloj."""
    assert wall_passes("rapido", 12) == 1.0
    assert wall_passes("normal", 12) == 2.0
    assert wall_passes("lento", 4) == 4.0
    assert wall_passes("normal", 1) == 2.0


def test_la_prevision_de_reloj_suma_una_pasada_por_tanda_y_no_depende_de_n():
    rapido = wall_forecast(siete(), PLAN, config(effort="rapido", workers=4))
    normal = wall_forecast(siete(), PLAN, config(effort="normal", workers=4))
    lento = wall_forecast(siete(), PLAN, config(effort="lento", workers=4))

    pasada = normal - rapido
    assert pasada > 0
    assert lento == pytest.approx(rapido + 3 * pasada)
    assert wall_forecast(siete(), PLAN, config(effort="normal", workers=1)) == pytest.approx(normal)


def test_la_prevision_de_reloj_de_rapido_es_la_de_arranque():
    """Con una sola pasada no hay nada que repartir: la cuenta del plan 2
    tiene que salir intacta."""
    from nesting.engine.packer import initial_forecast

    cfg = config(effort="rapido", workers=4)
    assert wall_forecast(siete(), PLAN, cfg) == initial_forecast(siete(), PLAN, cfg)
```

Run: `.venv/bin/pytest tests/engine/test_cartera.py -k reloj -v`
Expected: FAIL con `ImportError`

En `src/nesting/engine/cartera.py`, después de `planned_variants`:

```python
def wall_passes(effort: str, workers: int) -> float:
    """Cuántas pasadas golosas "de reloj" cuesta la cartera, para el tiempo estimado previo.

    La base es una pasada. Cada tanda son `workers` variantes repartidas en
    `workers` núcleos: la previsión de consultas se multiplica por las
    variantes de la tanda y se divide por `N` (spec de pares y cartera, 6).
    Es una cota de arriba: si la base iguala la cota por área, las tandas
    no corren.
    """
    n = max(1, workers)
    # Las variantes de una tanda se reparten en `n` núcleos: son
    # ⌈tanda / n⌉ vueltas, cada una del tiempo de una pasada.
    return 1.0 + EFFORT_BATCHES[effort] * math.ceil(batch_size(workers) / n)


def wall_forecast(parts: Sequence[Part], supply: SheetSupply, config: NestConfig) -> float:
    """Las consultas "de reloj" de la cartera: lo que tarda en un núcleo, contando el paralelo.

    Es la previsión de arranque del plan 2 para UNA pasada (con recuperación
    y compactación), más una pasada golosa por cada tanda: cada tanda son
    `N` variantes en `N` núcleos. `initial_forecast` cuenta consultas
    TOTALES, sumadas entre procesos, y sirve para la barra; ésta sirve para
    multiplicarla por los segundos que tarda una consulta en UN núcleo.
    """
    if not parts:
        return 0.0
    una = initial_forecast(parts, supply, replace(config, effort="rapido"))
    sheets = prevision.estimate_sheets(
        sum(p.area for p in parts),
        [_usable_area(s, config.margin) for s in supply.scraps],
        _usable_area(supply.stock, config.margin),
    )
    pasada = prevision.forecast_greedy_pass(
        len(parts), len(orientations(supply.stock, config)), sheets
    )
    return una + (wall_passes(config.effort, config.workers) - 1.0) * pasada
```

y a los imports de `cartera.py`: `from dataclasses import dataclass, replace`
(en lugar de `from dataclasses import dataclass`), `from nesting.engine import
prevision`, y `_usable_area` en el import de `nesting.engine.packer`.

Run: `.venv/bin/pytest tests/engine/test_cartera.py -k reloj -v`
Expected: PASS

- [ ] **Step 11: El tiempo estimado previo usa `wall_forecast`**

Test primero, en `tests/app/test_api_trabajos.py`:

```python
def test_estimar_cuenta_las_tandas_y_los_nucleos(cliente, tmp_path, monkeypatch):
    """Spec 6: el tiempo estimado previo multiplica por las variantes de la
    tanda y divide por N. El cuerpo es el `PedidoTrabajo` que el plan 2 usa
    para `/api/estimar`."""
    from nesting.engine import cartera

    vistas = []
    real = cartera.wall_passes
    monkeypatch.setattr(cartera, "wall_passes", lambda e, n: vistas.append((e, n)) or real(e, n))
    fuente_id = fuente_de(cliente, tmp_path)

    respuesta = cliente.post("/api/estimar", json={
        "fuente_id": fuente_id,
        "params": {"material": "mdf18", "esfuerzo": "lento", "nucleos": 1},
    })

    assert respuesta.status_code == 200
    assert respuesta.json()["segundos"] is not None
    assert ("lento", 1) in vistas
```

Run: `.venv/bin/pytest tests/app/test_api_trabajos.py -k estimar_cuenta -v`
Expected: FAIL con `assert ('lento', 1) in []`

En `src/nesting_app/corredor.py`, en `estimar_segundos` (del plan 2), cambiar
la última línea

```python
    return por_consulta * initial_forecast(piezas, supply, config) * FACTOR_LLENO
```

por

```python
    # En un núcleo: la prueba mide UNA consulta en UN núcleo, y las tandas
    # corren repartidas en `config.workers` (spec de pares y cartera, 6).
    return por_consulta * cartera.wall_forecast(piezas, supply, config) * FACTOR_LLENO
```

con `from nesting.engine import cartera` en los imports (y `initial_forecast`
fuera del import de `nesting.engine.packer` si ya no se usa en el archivo).
`wall_forecast` llama a `wall_passes` a través del módulo, así que el test la
puede espiar. El `config` que llega ya trae `workers`: `estimar` lo arma con
`a_config(params)`, que desde el Paso 5 lo toma de `nucleos_efectivos`.

El test del plan 2 `test_la_estimacion_es_prueba_por_prevision_por_factor`
usa `rapido`, donde `wall_forecast` es igual a `initial_forecast` (Paso 10),
así que sigue pasando sin tocarlo.

- [ ] **Step 12: Correr la suite entera**

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos.

- [ ] **Step 13: Commit**

```bash
git add src/nesting/engine/workers.py src/nesting/engine/cartera.py src/nesting/params.py \
        src/nesting/cli.py src/nesting_app/api.py src/nesting_app/corredor.py \
        src/nesting_app/web/index.html src/nesting_app/web/app.js src/nesting_app/web/app.css \
        src/nesting_app/web/info.js tests/engine/test_workers.py tests/engine/test_cartera.py \
        tests/test_params.py tests/test_cli.py tests/app/test_api_trabajos.py \
        tests/app/test_corredor.py tests/app/test_web_estatico.py tests/app/test_web_javascript.py
git commit -m "Núcleos: parámetro, --nucleos, /api/sistema y el control debajo de Esfuerzo"
```

---

### Task 8: "No se puede con menos placas."

Cuando el resultado iguala la cota mínima por área, se dice, en la pantalla y
en la CLI. Si no, nada: que el área permita menos placas no quiere decir que
entren (la banqueta con veta tiene cota 1 y el mínimo real es 2). Con
recortes no se informa nunca.

**Files:**
- Modify: `src/nesting_app/jobs.py` (`Resultado.es_minimo`), `src/nesting_app/corredor.py`, `src/nesting_app/api.py`, `src/nesting_app/web/app.js` (`terminar`), `src/nesting/cli.py` (`_print_summary`)
- Test: `tests/app/test_corredor.py`, `tests/app/test_api_trabajos.py`, `tests/app/test_web_javascript.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `cota_minima(parts, supply, margin)` (Tarea 5).
- Produces: `Resultado.es_minimo: bool = False`; `"es_minimo"` en el resultado de `GET /api/trabajos/{id}`; `_print_summary(result, parts, material, part_count, out_path, es_minimo: bool)`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/app/test_corredor.py`:

```python
def test_si_iguala_la_cota_dice_que_no_se_puede_con_menos(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200), (300, 0, 150)]))
    salida = tmp_path / "t"
    salida.mkdir()

    resultado = corredor.acomodar(fuente, params(resolucion=4.0), lambda a: True, salida)

    assert resultado.placas == 1
    assert resultado.es_minimo is True


def test_si_no_la_iguala_no_dice_nada(tmp_path, deposito):
    """Tres cuadrados de 1100 en una placa de 1830 x 2600: el área da para
    una (3,63 m² contra 4,67 útiles) pero no entran dos lado a lado. Dos
    placas, cota una: no se dice nada, porque no se sabe si 2 es el mínimo."""
    fuente = deposito.registrar_local(
        dxf_con(tmp_path, [(0, 0, 1100), (1200, 0, 1100), (2400, 0, 1100)])
    )
    salida = tmp_path / "t"
    salida.mkdir()

    resultado = corredor.acomodar(fuente, params(resolucion=4.0), lambda a: True, salida)

    assert resultado.placas == 2
    assert resultado.es_minimo is False


def test_con_recortes_nunca_se_dice(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)]))
    salida = tmp_path / "t"
    salida.mkdir()

    resultado = corredor.acomodar(
        fuente, params(recortes=(Recorte(700.0, 700.0),), resolucion=4.0),
        lambda a: True, salida,
    )

    assert resultado.es_minimo is False
```

En `tests/app/test_api_trabajos.py`, en `test_el_ciclo_completo`, agregar:

```python
    assert cuerpo["resultado"]["es_minimo"] is True
```

En `tests/app/test_web_javascript.py`, al final:

```python
def test_el_resultado_dice_cuando_no_se_puede_con_menos_placas(js):
    cuerpo = _cuerpo_de_funcion(js, "terminar")
    assert "r.es_minimo" in cuerpo
    assert "No se puede con menos placas." in cuerpo
```

En `tests/test_cli.py`, al final:

```python
def test_la_cli_dice_cuando_no_se_puede_con_menos_placas(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 200), (300, 0, 150)])
    run([source, "--material", "test", "--materiales", catalogue(tmp_path),
         "--esfuerzo", "rapido", "-o", tmp_path / "out.dxf"])
    assert "No se puede con menos placas." in capsys.readouterr().out


def test_la_cli_no_lo_dice_si_no_iguala_la_cota(tmp_path, capsys):
    """Tres cuadrados de 600 en una placa de 1000: uno por placa, tres
    placas, y la cota por área es dos."""
    source = write_input(tmp_path, [(0, 0, 600), (700, 0, 600), (1400, 0, 600)])
    run([source, "--material", "test", "--materiales", catalogue(tmp_path),
         "--esfuerzo", "rapido", "-o", tmp_path / "out.dxf"])
    assert "No se puede con menos placas." not in capsys.readouterr().out
```

- [ ] **Step 2: Correr para verlos fallar**

Run: `.venv/bin/pytest tests/app/test_corredor.py tests/app/test_api_trabajos.py::test_el_ciclo_completo tests/app/test_web_javascript.py tests/test_cli.py -k "minimo or menos or cota or ciclo_completo or recortes_nunca" -v`
Expected: FAIL con `AttributeError: 'Resultado' object has no attribute 'es_minimo'`, `KeyError: 'es_minimo'` y los dos de texto sin encontrar la frase (el de "no lo dice" pasa desde ya, y está bien: es la otra mitad de la regla).

- [ ] **Step 3: Implementar**

En `src/nesting_app/jobs.py`, agregar a `Resultado`, después de `recortes_usados`:

```python
    es_minimo: bool = False
    """El acomodo iguala la cota por área: con menos placas no entra.

    Lo calcula el corredor con `cartera.cota_minima`, que no informa nada con
    recortes. En falso no dice "se puede con menos": dice que no se sabe.
    """
```

En `src/nesting_app/corredor.py`, importar `from nesting.engine.cartera import cota_minima` y, en el `return Resultado(...)` del final de `acomodar`, agregar:

```python
        es_minimo=cota_minima(piezas, supply, config.margin) == resultado.sheets_used,
```

(`cota_minima` devuelve `None` con recortes, y `None == n` es falso.)

En `src/nesting_app/api.py`, en el diccionario `resultado` de `ver_trabajo`, agregar `"es_minimo": trabajo.resultado.es_minimo,`.

En `src/nesting_app/web/app.js`, en `terminar(t)`, reemplazar la asignación de `$("resultado").innerHTML` por:

```js
  $("resultado").innerHTML =
    `<strong>${placas}</strong> · <strong>${(100 * r.total).toFixed(1)}%</strong> ` +
    `aprovechado · sobrante <strong>${r.sobrante_mm.toFixed(0)} mm</strong> · ` +
    `<strong>${r.material_ultima_placa_m2.toFixed(3)} m²</strong> en la última placa` +
    (r.es_minimo ? " · <strong>No se puede con menos placas.</strong>" : "");
```

En `src/nesting/cli.py`, importar `from nesting.engine.cartera import cota_minima`, cambiar la llamada a

```python
    _print_summary(
        result, parts, material, len(parts), args.salida,
        es_minimo=cota_minima(parts, supply, config.margin) == result.sheets_used,
    )
```

y en `_print_summary`, agregar el parámetro `es_minimo: bool` al final de la firma y, justo después del `print` de la línea `"{part_count} piezas - ..."`:

```python
    if es_minimo:
        print("No se puede con menos placas.")
```

- [ ] **Step 4: Correr los tests y la suite entera**

Run: `.venv/bin/pytest tests/app/test_corredor.py tests/app/test_api_trabajos.py tests/app/test_web_javascript.py tests/test_cli.py -v`
Expected: PASS

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos.

- [ ] **Step 5: Commit**

```bash
git add src/nesting_app/jobs.py src/nesting_app/corredor.py src/nesting_app/api.py \
        src/nesting_app/web/app.js src/nesting/cli.py tests/app/test_corredor.py \
        tests/app/test_api_trabajos.py tests/app/test_web_javascript.py tests/test_cli.py
git commit -m "Resultado: decir cuando no se puede con menos placas, sólo si iguala la cota"
```

---

### Task 9: Las pruebas que importan, la fila del banco y el autotest con dos procesos

Tres cosas que prueban el conjunto de punta a punta: un caso sintético rápido
con la misma trampa que la banqueta, la banqueta misma (lenta, y salteada con
un motivo claro si el archivo no está, porque `bench/files/` no se versiona),
y un `--autotest` que ejerce el pool de verdad, porque un `spawn` sin
`freeze_support` anda en el repo y se cuelga en el ejecutable.

Estas pruebas miran comportamiento que las Tareas 1 a 8 ya construyeron, así
que **se espera que pasen al escribirlas**. Si una falla, no es el paso rojo
de un ciclo TDD: es un hallazgo, y el paso que corresponde lo dice.

**El caso sintético** (medido al escribir el plan, `sweep2.py`, con
`NEIGHBOUR_MM = 200` y los tipos congruentes descartados): seis copias de una
L de 600 × 300 con brazos de 110 mm,

```
(0,300) ┌──┐
        │  │
        │  └─────────────┐ (600,110)
(0,0)   └────────────────┘ (600,0)
         brazo de 110 mm
```

en una placa de 1200 × 690, sep 8, borde 5, 0°/90°/180°/270° con espejo,
2 mm/px. La base (seis sueltas) abre 2 placas; la cota por área es 1 (6 ×
86.900 mm² contra 1190 × 680 útiles). Los seis tipos son `724×300`,
`676×424`, `724×424` (tres, no congruentes entre sí) y `600×614`. De las 56
combinaciones de tres pares, **ninguna de un solo tipo** entra en una placa,
y entran dos mezcladas: la de puesto 1 (`724×300` ×2 + `676×424`) y la de
puesto 25. Con `workers = 2` la tanda de `normal` son los puestos 0 y 1, así
que la encuentra.

**Files:**
- Modify: `pyproject.toml` (marca `lento`)
- Create: `tests/engine/test_aceptacion_pares.py`
- Modify: `bench/run_bench.py` (`CasoFijo`, `CASOS_FIJOS`, `run_fixed`), `tests/test_bench.py`
- Modify: `src/nesting_app/desktop.py` (`_prueba_de_procesos`, `_autotest`), `tests/app/test_desktop.py`
- Modify: `packaging/construir.sh` (comentario)

**Interfaces:**
- Consumes: `run_portfolio`, `PortfolioResult.winner.pair_types`, `PortfolioResult.lower_bound`, `find_pair_types`, `b_orientations`, `TIPOS_POR_CLASE`, `_pack_once`, `RasterOracleFactory`.
- Produces: la marca `lento` (excluida por omisión; se corre con `-m lento`); `run_bench.CasoFijo(archivo: str, placa: Sheet, config: NestConfig, esperado: int)`, `run_bench.CASOS_FIJOS`, `run_bench.run_fixed(caso, files_dir=FILES_DIR) -> BenchResult | None`; `desktop._prueba_de_procesos(timeout: float = 120.0) -> None`.

- [ ] **Step 1: Registrar la marca `lento`**

En `pyproject.toml`, reemplazar la sección `[tool.pytest.ini_options]` por:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
# Las pruebas de minutos no corren en cada `pytest`: se piden con
# `.venv/bin/pytest -m lento`. Un `-m` en la línea de comandos pisa éste.
addopts = "-q -m 'not lento'"
markers = [
    "lento: pruebas de minutos (la banqueta alta, la confirmación del caso sintético); correr con `.venv/bin/pytest -m lento`",
    "minimo_real: usa `cartera.MIN_BATCH` de verdad en vez del 1 de los tests",
]
```

Run: `.venv/bin/pytest --markers | grep lento`
Expected: la línea de la marca.

- [ ] **Step 2: Escribir las pruebas de aceptación**

Crear `tests/engine/test_aceptacion_pares.py`:

```python
"""Las pruebas que importan: seis marcos que sólo entran encastrados de a
pares, y con dos tipos de par distintos."""

import itertools
from pathlib import Path

import pytest

from nesting.engine.cartera import run_portfolio
from nesting.engine.oracle import NestConfig
from nesting.engine.packer import PartTooLargeError, _pack_once, orientations
from nesting.engine.pares import TIPOS_POR_CLASE, b_orientations, find_pair_types
from nesting.engine.raster.masks import MaskCache
from nesting.engine.raster.oracle import RasterOracleFactory
from nesting.geometry.verify import verify
from nesting.model.part import Part
from nesting.model.sheet import Sheet, SheetSupply

# --- el caso sintético ------------------------------------------------------
#
# Medido al escribir el plan (ver la Tarea 9 del plan de pares y cartera):
# sin pares, 2 placas; ninguna combinación de tres pares de UN solo tipo
# entra en una; dos mezclas sí, y la de puesto 1 cae en la tanda de normal
# con dos núcleos.

ELE = ((0.0, 0.0), (600.0, 0.0), (600.0, 110.0), (110.0, 110.0), (110.0, 300.0), (0.0, 300.0))
PLACA = Sheet(1200.0, 690.0, grain_tolerance=180.0)
PLAN = SheetSupply(stock=PLACA, material_name="sintética")
UTIL = (PLACA.width - 10.0, PLACA.height - 10.0)


def seis():
    return [Part(i, ELE, (), (i,)) for i in range(6)]


def config(**cambios):
    base = dict(sep=8.0, margin=5.0, angles=(0.0, 90.0, 180.0, 270.0), mirror=True,
                resolution=2.0, effort="normal", seed=0, workers=2)
    base.update(cambios)
    return NestConfig(**base)


def test_seis_eles_entran_en_una_placa_solo_con_pares_de_dos_tipos():
    piezas = seis()

    rapido = run_portfolio(piezas, PLAN, config(effort="rapido"), RasterOracleFactory())
    assert rapido.result.sheets_used == 2, "sin pares, la trampa tiene que atrapar a la pasada golosa"

    normal = run_portfolio(piezas, PLAN, config(), RasterOracleFactory())
    resultado = normal.result

    assert resultado.sheets_used == 1
    assert normal.lower_bound == 1, "y entonces se puede decir que no se puede con menos"
    tipos = {tipo for _, tipo in normal.winner.pair_types}
    assert len(tipos) >= 2, f"ganó una combinación de un solo tipo: {normal.winner.pair_types}"
    assert sorted(p.part_id for p in resultado.placements) == list(range(6))
    assert verify(piezas, resultado.placements, resultado.sheets, sep=8.0, margin=5.0) == []


@pytest.mark.lento
def test_el_caso_sintetico_necesita_mezclar_tipos():
    """La confirmación de que el caso de arriba es la trampa que dice ser, y
    no uno que un tipo solo ya resuelve: se prueban las 56 combinaciones de
    tres pares, cada una con una pasada golosa. Tarda del orden de 15 s."""
    cfg = config(effort="rapido")
    choices = orientations(PLACA, cfg)
    tipos = find_pair_types(seis()[0], b_orientations(choices, False), choices, cfg,
                            UTIL, TIPOS_POR_CLASE["normal"], MaskCache())
    fabrica = RasterOracleFactory()

    assert _pack_once(seis(), PLAN, cfg, fabrica).sheets_used == 2

    una_placa = []
    for combo in itertools.combinations_with_replacement(range(len(tipos)), 3):
        orden = sorted((tipos[t].shape(100 + k) for k, t in enumerate(combo)),
                       key=lambda p: p.area, reverse=True)
        try:
            placas = _pack_once(orden, PLAN, cfg, fabrica).sheets_used
        except PartTooLargeError:
            continue
        if placas == 1:
            una_placa.append(combo)

    puros = [c for c in una_placa if len(set(c)) == 1]
    assert puros == [], f"un solo tipo alcanza, la trampa no es tal: {puros}"
    assert una_placa, "ninguna mezcla de tres pares entra en una placa"


# --- la banqueta alta ---------------------------------------------------------

BANQUETA = Path(__file__).resolve().parents[2] / "bench" / "files" / "banqueta-alta.ai"

falta_la_banqueta = pytest.mark.skipif(
    not BANQUETA.exists(),
    reason=(
        f"falta {BANQUETA}: es un archivo de diseño del usuario y no se versiona "
        "(bench/files/ está en .gitignore). Copiá ahí 'BANQUETA ALTA NESTING.ai' "
        "con ese nombre para correr esta prueba."
    ),
)


def piezas_de_la_banqueta():
    from nesting.io.ai_reader import read_ai
    from nesting.pipeline import prepare_parts

    piezas, _, _ = prepare_parts(read_ai(BANQUETA))
    return piezas


def config_banqueta():
    """8 posiciones, sep 8, borde 5, 1 mm/px, normal, con `workers = 4` a
    propósito: la combinación que gana sale octava, y es `MIN_BATCH` el que
    garantiza que una máquina de 4 núcleos también la pruebe. Las pruebas que
    usan esto llevan `@pytest.mark.minimo_real`; sin la marca, el fixture de
    `tests/conftest.py` bajaría la tanda a 4 y la banqueta daría 2 placas."""
    return NestConfig(sep=8.0, margin=5.0, angles=tuple(i * 45.0 for i in range(8)),
                      mirror=True, resolution=1.0, effort="normal", seed=0, workers=4)


@pytest.mark.lento
@pytest.mark.minimo_real
@falta_la_banqueta
def test_la_banqueta_alta_entra_en_una_placa_libre():
    piezas = piezas_de_la_banqueta()
    assert len(piezas) == 57
    plan = SheetSupply(stock=Sheet(1220.0, 2440.0, grain_tolerance=180.0), material_name="libre")

    salida = run_portfolio(piezas, plan, config_banqueta(), RasterOracleFactory())

    assert salida.result.sheets_used == 1, (salida.winner.kind, salida.winner.pair_types)
    assert salida.lower_bound == 1
    assert verify(piezas, salida.result.placements, salida.result.sheets,
                  sep=8.0, margin=5.0) == []


@pytest.mark.lento
@falta_la_banqueta
def test_la_banqueta_alta_con_veta_son_dos_placas_y_no_dice_minimo():
    """Con la veta respetada, 1 placa es imposible (la columna de seis marcos
    a 0° y 180° mide 2530 mm contra 2430 útiles), y la cota por área sigue
    siendo 1: el cartel de mínimo no tiene que salir."""
    piezas = piezas_de_la_banqueta()
    plan = SheetSupply(stock=Sheet(1220.0, 2440.0, grain_tolerance=5.0),
                       material_name="multilam18")

    salida = run_portfolio(piezas, plan, config_banqueta(), RasterOracleFactory())

    assert salida.result.sheets_used == 2
    assert salida.lower_bound == 1 != salida.result.sheets_used
    assert verify(piezas, salida.result.placements, salida.result.sheets,
                  sep=8.0, margin=5.0) == []
```

- [ ] **Step 3: Correr la rápida**

Run: `.venv/bin/pytest tests/engine/test_aceptacion_pares.py -v`
Expected: `test_seis_eles_entran_en_una_placa_solo_con_pares_de_dos_tipos` PASS (unos segundos: arranca dos procesos); las tres `lento`, `deselected`.

Si falla con `sheets_used == 2` en `normal`, antes de tocar nada correr la
confirmación del paso siguiente: dice si el caso dejó de ser la trampa (por
ejemplo, porque la lista de tipos cambió respecto de la medida) o si la
cartera no la encuentra.

- [ ] **Step 4: Confirmar que el caso de verdad necesita mezclar tipos**

Run: `.venv/bin/pytest -m lento tests/engine/test_aceptacion_pares.py::test_el_caso_sintetico_necesita_mezclar_tipos -v`
Expected: PASS.

Si falla, la placa elegida dejó de exhibir la trampa. Ajustar así, en este
orden, cambiando `PLACA` (y nada más) y volviendo a correr los Pasos 3 y 4
con cada valor:

1. `Sheet(1180.0, 690.0, ...)`: también medida, con el mismo resultado (ningún puro, las mismas dos mezclas).
2. Si tampoco: barrer el alto de 660 a 720 de a 10 mm, con anchos de 1160 a 1220 de a 20, y quedarse con la primera placa que cumpla las tres condiciones de la prueba (base en 2 placas, ningún puro, al menos una mezcla) **y** donde `test_seis_eles...` pase. Para el barrido, el cuerpo de la prueba lenta se puede correr en un bucle desde `.venv/bin/python` cambiando `PLACA`/`PLAN`/`UTIL`; lo que se commitea es sólo la placa elegida.
3. Si ninguna placa del barrido sirve con esta L, cambiar el brazo de 110 a 120 y repetir el barrido: con el algoritmo viejo (60 mm, sin descarte de congruentes) la L de brazo 120 en 1250 × 650 mostraba la trampa, y es el siguiente candidato.

Actualizar el comentario de arriba del archivo y el de esta tarea con la placa
que quedó y los tipos que se vieron.

- [ ] **Step 5: Correr la banqueta**

Run: `.venv/bin/pytest -m lento tests/engine/test_aceptacion_pares.py -k banqueta -v`
Expected: las dos PASS (del orden de 6 a 10 minutos cada una en la máquina de 14 núcleos), o las dos SKIPPED con el motivo "falta .../bench/files/banqueta-alta.ai ..." si el archivo no está.

Si `test_la_banqueta_alta_entra_en_una_placa_libre` da 2 placas: NO se
relaja la prueba. Imprimir los tipos que encontró la búsqueda
(`find_pair_types` sobre el marco, como en `test_pares.py`) y compararlos con
los de la Decisión 3 (`1812×450`, `1511×560`, `1055×879`, `1055×886`,
`2108×450`, `1055×902`); si difieren, el desvío está en `pares.py`; si son
esos, está en el orden de las combinaciones de `cartera.py` (la ganadora
medida es la de puesto 8, "caja mínima + diagonal + apilado"). Reportarlo con
esos datos.

- [ ] **Step 6: La fila fija del banco, tests primero**

Agregar a `tests/test_bench.py`:

```python
def test_un_caso_fijo_sin_su_archivo_se_saltea(tmp_path):
    import run_bench

    assert run_bench.run_fixed(run_bench.CASOS_FIJOS[0], files_dir=tmp_path) is None


def test_la_banqueta_alta_es_un_caso_fijo_del_banco():
    import run_bench

    caso = next(c for c in run_bench.CASOS_FIJOS if c.archivo == "banqueta-alta.ai")
    assert caso.esperado == 1
    assert (caso.placa.width, caso.placa.height, caso.placa.grain_tolerance) == (1220.0, 2440.0, 180.0)
    assert caso.config.resolution == 1.0 and caso.config.workers == 12
    assert caso.config.effort == "normal"
```

Run: `.venv/bin/pytest tests/test_bench.py -k fijo -v`
Expected: FAIL con `AttributeError: module 'run_bench' has no attribute 'run_fixed'`

En `bench/run_bench.py`, agregar a los imports `from nesting.model.sheet import Sheet, SheetSupply` (en lugar del de `SheetSupply` solo) y, después de `run_one`:

```python
@dataclass(frozen=True)
class CasoFijo:
    """Un archivo real con su propia placa y su propia configuración.

    El barrido de `*.dxf` usa una sola configuración para todo; estos casos
    son trabajos concretos con un resultado conocido, que se miden tal cual.
    """

    archivo: str
    placa: Sheet
    config: NestConfig
    esperado: int
    """Las placas del resultado verificado a mano."""


CASOS_FIJOS = (
    # Diego lo acomodó a mano en 1 placa; el motor sin pares daba 2. Ver la
    # spec de pares y cartera, 1. `workers` fijo en 12 porque el resultado
    # depende de N.
    CasoFijo(
        archivo="banqueta-alta.ai",
        placa=Sheet(1220.0, 2440.0, grain_tolerance=180.0),
        config=NestConfig(sep=8.0, margin=5.0, angles=tuple(i * 45.0 for i in range(8)),
                          mirror=True, resolution=1.0, effort="normal", workers=12),
        esperado=1,
    ),
)


def run_fixed(caso: CasoFijo, files_dir: Path = FILES_DIR) -> BenchResult | None:
    """Mide un caso fijo, o `None` si su archivo no está en `files_dir`.

    Los archivos de diseño no se versionan: que falte uno no es un error.
    """
    path = files_dir / caso.archivo
    if not path.exists():
        return None
    material = Material(caso.archivo, caso.placa.width, caso.placa.height,
                        caso.placa.grain_tolerance)
    return run_one(path, material, caso.config, RasterOracleFactory(), "cartera")
```

y en `main()`, justo antes del `if failed:` final:

```python
    for caso in CASOS_FIJOS:
        result = run_fixed(caso)
        if result is None:
            print(f"{caso.archivo:<24}(falta en bench/files: se saltea)")
            continue
        flag = "  VIOLACIONES!" if result.violations else ""
        esperado = "" if result.sheets == caso.esperado else f"  (esperado {caso.esperado})"
        print(
            f"{result.name:<24}{result.engine:<10}{result.parts:>7}{result.sheets:>8}"
            f"{result.total_utilization * 100:>8.1f}%"
            f"{result.first_sheet_utilization * 100:>10.1f}%"
            f"{result.seconds:>8.1f}{esperado}{flag}"
        )
```

Run: `.venv/bin/pytest tests/test_bench.py -v`
Expected: PASS

- [ ] **Step 7: El autotest corre la cartera con dos procesos, tests primero**

Agregar a `tests/app/test_desktop.py`:

```python
def test_el_autotest_falla_si_la_corrida_con_dos_procesos_falla(tmp_path, monkeypatch, capsys):
    """Es lo que tiene que frenar a un ejecutable al que le falta
    `freeze_support`: en el repo el `spawn` anda igual, en el paquete se
    cuelga."""
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")
    monkeypatch.setattr(desktop, "motor_de_ventana", lambda: None)

    def colgada(timeout=120.0):
        raise RuntimeError("la corrida con 2 procesos no terminó")

    monkeypatch.setattr(desktop, "_prueba_de_procesos", colgada)

    assert desktop.main(["--autotest"]) == 1
    assert "2 procesos" in capsys.readouterr().err


def test_la_corrida_con_dos_procesos_no_deja_procesos_vivos():
    import multiprocessing

    desktop._prueba_de_procesos()
    assert multiprocessing.active_children() == []
```

Run: `.venv/bin/pytest tests/app/test_desktop.py -k "procesos" -v`
Expected: FAIL con `AttributeError: module 'nesting_app.desktop' has no attribute '_prueba_de_procesos'`

En `src/nesting_app/desktop.py`, agregar antes de `_autotest`:

```python
def _prueba_de_procesos(timeout: float = 120.0) -> None:
    """Una corrida de la cartera con dos procesos, con tiempo límite.

    Un `spawn` sin `multiprocessing.freeze_support()` anda perfecto desde el
    repo y se cuelga en el ejecutable congelado: cada proceso del pool
    vuelve a arrancar el programa entero en vez de ser un proceso del pool.
    Ningún test normal lo ve. Esto sí, en la máquina que arma el paquete.

    Tres cuadrados de 600 en una placa de 1000: uno por placa, tres placas,
    y la cota por área es dos, así que la cartera no se conforma con la base
    y manda una tanda de dos variantes al pool.
    """
    from nesting.engine.cartera import run_portfolio
    from nesting.engine.oracle import NestConfig
    from nesting.engine.raster.oracle import RasterOracleFactory
    from nesting.model.part import Part
    from nesting.model.sheet import Sheet, SheetSupply

    piezas = [
        Part(i, ((0.0, 0.0), (600.0, 0.0), (600.0, 600.0), (0.0, 600.0)), (), (i,))
        for i in range(3)
    ]
    config = NestConfig(sep=5.0, margin=10.0, angles=(0.0, 90.0), mirror=False,
                        resolution=5.0, effort="normal", workers=2)
    plan = SheetSupply(stock=Sheet(1000.0, 1000.0, grain_tolerance=180.0))
    salida: list = []

    def correr() -> None:
        try:
            salida.append(run_portfolio(piezas, plan, config, RasterOracleFactory()))
        except BaseException as error:  # noqa: BLE001 - se relanza abajo
            salida.append(error)

    hilo = threading.Thread(target=correr, daemon=True)
    hilo.start()
    hilo.join(timeout)
    if hilo.is_alive():
        raise RuntimeError(
            f"la corrida con 2 procesos no terminó en {timeout:.0f} s: "
            "¿falta multiprocessing.freeze_support() al principio de main?"
        )
    if isinstance(salida[0], BaseException):
        raise salida[0]
    if salida[0].result.sheets_used != 3:
        raise RuntimeError(
            f"la corrida con 2 procesos dio {salida[0].result.sheets_used} placas "
            "y tenían que ser 3"
        )
```

y en `_autotest`, dentro del `try`, después de `urllib.request.urlopen(url, timeout=10).read()`:

```python
        # Al final y no al principio: es lo más lento del autotest (arranca
        # dos procesos), y si el paquete está roto por otra cosa conviene
        # enterarse antes.
        _prueba_de_procesos()
```

En `packaging/construir.sh`, arriba de `echo "== verificando el paquete =="`, agregar:

```bash
# El autotest incluye una corrida de la cartera con 2 procesos: un spawn sin
# freeze_support anda en el repo y se cuelga en el ejecutable.
```

Run: `.venv/bin/pytest tests/app/test_desktop.py -v`
Expected: PASS (el `test_autotest_sale_con_cero` de siempre ahora también arranca los dos procesos: tarda unos segundos más).

- [ ] **Step 8: Correr la suite entera**

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos; las pruebas `lento` aparecen como `deselected`.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml tests/engine/test_aceptacion_pares.py bench/run_bench.py tests/test_bench.py \
        src/nesting_app/desktop.py tests/app/test_desktop.py packaging/construir.sh
git commit -m "Pruebas de aceptación de los pares, la banqueta en el banco y el autotest con dos procesos"
```

---

### Task 9b: Las combinaciones se ordenan por placas previstas

Agregada el 2026-09-23 por decisión del usuario, después de que la Tarea 9
midiera que, con las clases bien armadas (los seis marcos en una sola clase),
la banqueta daba 2 placas en normal: ordenadas sólo por área de cajas, las
doce primeras combinaciones eran todas imposibles y la que entra quedaba
afuera. Spec 4.1, punto 2, reescrito.

**Files:**
- Create: `src/nesting/engine/estantes.py` (armado de rectángulos por estantes, puro, sin dependencias del motor)
- Modify: `src/nesting/engine/cartera.py` (`_combinations` ordena por `(placas previstas, costo, tupla)`)
- Test: `tests/engine/test_estantes.py` (nuevo), `tests/engine/test_cartera.py`

**Interfaces:**
- Consumes: `PairType.width`/`height` (caja del par en la orientación de la representante), `Clase.members`, `Clase.representative`, `orientations(stock, config)`, `NestConfig.sep`/`margin`.
- Produces: `estantes.predicted_sheets(boxes: Sequence[tuple[float, float]], usable: tuple[float, float], sep: float, can_turn: bool) -> int`; en `cartera`, el orden nuevo de `_combinations` para una y dos clases.

Reglas del armado (`predicted_sheets`), que son las del spec:
- Cada caja se orienta así: si `can_turn` es falso, tal cual; si es verdadero, entre (w, h) y (h, w) se toma la que entra en el ancho útil y, si entran las dos, la de menor alto.
- Una caja que no entra en el área útil en ninguna orientación cuenta como una placa propia (no levanta).
- Primero la más alta (empates por ancho descendente, después por el orden de entrada). Estantes llenados en orden: cada caja va al primer estante de la placa en curso donde entra a lo ancho (con `sep` entre cajas y el estante tan alto como su primera caja); si no entra en ninguno, abre un estante nuevo encima (con `sep` entre estantes); si el estante nuevo no entra en el alto útil, abre una placa nueva.
- `can_turn` es verdadero cuando `orientations(stock, config)` incluye algún ángulo a 90° o 270°.

Qué cajas entran en la predicción de una combinación: la de cada par (`PairType.width × height`), la de cada miembro suelto de cada clase emparejable (caja de la representante), y la de toda otra pieza cuya área neta sea al menos el 2% del área útil (la misma cota que `pares.pairable_classes`).

Orden en `_combinations`: se sacan de `smallest_combinations` las primeras `max(want × 8, 400)` combinaciones por costo (con dos clases, del producto), se calcula `predicted_sheets` de cada una, y se ordenan de forma estable por `(placas previstas, costo, tupla)`. La tanda 1 de normal y lento sigue siendo idéntica (mismo límite de tipos, misma cuenta), así que normal sigue siendo prefijo de lento.

- [ ] **Step 1: Tests de `predicted_sheets`, que fallan**

`tests/engine/test_estantes.py` con, como mínimo, estos casos sobre el área útil de la banqueta `(1210.0, 2430.0)` y `sep = 8.0`, con `can_turn=True` (las cajas son las medidas en la Tarea 9: mínima 1809×451, diagonal 1508×560, apilado 1056×875, marco suelto 1055×450):
- diagonal ×2 + apilado → 1
- diagonal ×2 + marco ×2 → 1
- mínima + diagonal + apilado → 2
- mínima ×3 → 2; diagonal ×3 → 2; apilado ×3 → 2
- con `can_turn=False`, diagonal ×2 + apilado → 2 (1508 no entra en 1210 sin girar)
- una caja más grande que la placa en las dos orientaciones cuenta una placa y no levanta
- lista vacía → 0

- [ ] **Step 2: Correrlos y verlos fallar** (`ModuleNotFoundError`).

- [ ] **Step 3: Implementar `estantes.py`** con las reglas de arriba, y docstrings que expliquen que es una predicción para ordenar, no un acomodo.

- [ ] **Step 4: Correrlos y verlos pasar.**

- [ ] **Step 5: Test de orden en `tests/engine/test_cartera.py`, que falla**: sobre la banqueta (se saltea si falta `bench/files/banqueta-alta.ai`), con la config de la Tarea 9 (placa libre 1220×2440, sep 8, borde 5, 8 posiciones, espejo, 1 mm/px, normal), la primera combinación de la tanda 1 tiene placas previstas 1, y la combinación "diagonal ×2 + apilado" (buscar los índices de tipo por su caja, ±5 mm) está entre las primeras 12. Y un test sintético sin archivos: dos tipos donde el de menor área no entra como rectángulo y el otro sí; la combinación que entra sale primero.

- [ ] **Step 6: Implementar el orden nuevo en `_combinations`** (una clase y dos clases), y verlo pasar.

- [ ] **Step 7: Correr las aceptaciones**: el test rápido de las seis eles (si deja de encontrar la mezcla, no aflojarlo: medir y avisar) y, con `-m lento` (en segundo plano, mirando la salida en primer plano de a menos de 10 minutos), las dos de la banqueta: libre → 1 placa, con veta → 2 placas.

- [ ] **Step 8: Suite por omisión entera en primer plano** (partida si pasa de 10 minutos). Sin procesos `spawn_main` al final.

- [ ] **Step 9: Commit**

```bash
git add src/nesting/engine/estantes.py src/nesting/engine/cartera.py tests/engine/test_estantes.py tests/engine/test_cartera.py
git commit -m "Cartera: primero las combinaciones que entran como rectángulos"
```

---

### Task 10: Documentación

Las tablas de opciones de los dos README dicen hoy que `normal` son 3 pasadas
y `lento` 12, y no tienen fila para Núcleos. El README del banco no sabe de
la fila fija ni de `-m lento`.

**Files:**
- Modify: `README.es.md`, `README.md`, `bench/README.es.md`, `bench/README.md`

**Interfaces:**
- Consumes: los nombres de las Tareas 7 a 9 (`--nucleos`, "No se puede con menos placas.", `CASOS_FIJOS`, la marca `lento`).
- Produces: nada que use código.

- [ ] **Step 1: README en español**

En `README.es.md`, en la tabla de "Opciones", reemplazar la fila de Esfuerzo y agregar la de Núcleos debajo:

```markdown
| Esfuerzo | `--esfuerzo` | `rapido` (una pasada), `normal` (la pasada más una tanda de tantas variantes como núcleos: las piezas repetidas grandes encastradas de a pares con distintos tipos de encastre, y si no hay, otros órdenes) o `lento` (tres tandas: más tipos de par y orientaciones perturbadas). |
| Núcleos | `--nucleos` | Cuántos núcleos usa para probar variantes a la vez. Arranca en todos menos dos, con un tope por memoria (cada núcleo usa unos 400 MB). Más núcleos prueban más variantes en el mismo tiempo, así que con otra cantidad de núcleos el resultado puede cambiar. |
```

y reemplazar el párrafo que sigue a la tabla por:

```markdown
**Más esfuerzo no siempre da un resultado mejor, pero nunca da uno peor**:
con la misma cantidad de núcleos, lo que prueba Normal es el principio de lo
que prueba Lento, y se queda con la mejor de todas.

Cuando el resultado usa tantas placas como el mínimo que permite el área de
las piezas, lo dice: **No se puede con menos placas.** Si no lo dice, no
quiere decir que se pueda: el área es una cota, no una promesa. Con recortes
no se informa.
```

- [ ] **Step 2: README en inglés**

En `README.md`, lo mismo:

```markdown
| Esfuerzo | `--esfuerzo` | `rapido` (one pass), `normal` (that pass plus one batch of as many variants as cores: the large repeated parts nested in pairs with different kinds of interlock, and when there are none, other insertion orders) or `lento` (three batches: more pair types and perturbed orientations). |
| Núcleos | `--nucleos` | How many cores to use to try variants at the same time. Starts at all but two, capped by memory (each core uses about 400 MB). More cores try more variants in the same time, so a different number of cores can change the result. |
```

```markdown
**More effort does not always give a better result, but it never gives a worse
one**: with the same number of cores, what Normal tries is the beginning of
what Lento tries, and it keeps the best of all of them.

When the result uses as many sheets as the minimum the parts' area allows, it
says so: **No se puede con menos placas** ("it cannot be done with fewer
sheets"). If it does not say it, that does not mean it can: area is a bound,
not a promise. It is not reported when offcuts are loaded.
```

- [ ] **Step 3: README del banco**

En `bench/README.es.md`, al final:

```markdown
## Casos fijos

Además del barrido de `*.dxf`, `run_bench.py` mide los trabajos de
`CASOS_FIJOS`, cada uno con su placa y su configuración, y avisa si el
resultado no es el esperado. Hoy es uno: `banqueta-alta.ai` (57 piezas,
placa 1220 × 2440 libre, sep 8, borde 5, 8 posiciones, normal, 1 mm/px,
12 núcleos), que tiene que dar **1 placa**. Si el archivo no está en
`bench/files/` (no se versiona), la fila dice que se saltea.

La misma banqueta es una prueba lenta de la suite, que no corre con un
`pytest` a secas:

    .venv/bin/pytest -m lento
```

En `bench/README.md`, al final:

```markdown
## Fixed cases

Besides sweeping `*.dxf`, `run_bench.py` measures the jobs in `CASOS_FIJOS`,
each one with its own sheet and configuration, and flags a result that is not
the expected one. Today there is one: `banqueta-alta.ai` (57 parts, free
1220 × 2440 sheet, sep 8, border 5, 8 positions, normal, 1 mm/px, 12 cores),
which has to give **1 sheet**. If the file is not in `bench/files/` (it is not
versioned), the row says it is skipped.

The same bench is a slow test of the suite, which a plain `pytest` does not
run:

    .venv/bin/pytest -m lento
```

- [ ] **Step 4: Verificar que no quedó nada viejo**

Run: `grep -n "normal\` (3)\|lento\` (12)\|tres pasadas\|doce pasadas" README.md README.es.md src/nesting_app/web/index.html src/nesting_app/web/info.js`
Expected: nada.

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos.

- [ ] **Step 5: Commit**

```bash
git add README.md README.es.md bench/README.md bench/README.es.md
git commit -m "Documentación: Núcleos, el esfuerzo por tandas, el cartel de mínimo y la banqueta en el banco"
```

---

### Task 11: Fase 2 — acelerar una sola combinación (sujeta a medición)

Cuando la tanda ocupa todos los núcleos, repartir una combinación no suma
nada; sí suma en `rapido` y en trabajos sin piezas repetidas. Dos ideas, que
**se miden antes de decidir**:

- **A. No repetir trabajo:** para cada una de las 16 orientaciones de una pieza, `fftconvolve` vuelve a transformar la placa, que no cambió. Reusar la transformada de la placa entre orientaciones, a un tamaño de FFT común.
- **B. Repartir orientaciones:** las consultas de una pieza son independientes; repartirlas en hilos, si scipy libera el GIL en las FFT.

**Criterio, fijado antes de medir:** se queda lo que baje **al menos un 30%**
el tiempo total de `rapido` sobre los archivos de `bench/files` con **el
mismo resultado, byte a byte**, en todos. Si ninguna llega, se documenta la
medición y no se hace. Esta tarea es la única de este plan que puede
terminar sin cambiar el motor.

"Byte a byte" se mide sobre el layout (`part_id`, placa y `Transform` de
cada colocación, en orden, con `repr` de los floats) y no sobre el DXF:
ezdxf graba la fecha de creación en la cabecera, así que dos DXF del mismo
layout no son iguales byte a byte.

**Files:**
- Create: `bench/medir_rapido.py`
- Modify (sólo si una idea pasa el criterio): `src/nesting/engine/raster/search.py`, `src/nesting/engine/raster/scoring.py`, `src/nesting/engine/raster/oracle.py` (idea A); `src/nesting/engine/packer.py`, `src/nesting/engine/cartera.py` (idea B)
- Modify: `docs/superpowers/calibracion.md` (la medición, pase lo que pase)
- Test (sólo si una idea pasa): `tests/engine/raster/test_espectro.py` (A), `tests/engine/test_hilos.py` (B)

**Interfaces:**
- Consumes: `pack`, `RasterOracleFactory`, `prepare_parts`, los lectores.
- Produces: `bench/medir_rapido.py` con `medir(archivos) -> list[Fila]` y un `main` que escribe y compara TSV. Si A pasa: `SheetSpectrum` en `search.py` y `position_scores(..., overlap=overlap_counts)`. Si B pasa: `QUERY_THREADS` y `_query_orientations` en `packer.py`.

- [ ] **Step 1: La herramienta de medición**

Crear `bench/medir_rapido.py`:

```python
"""Tiempo de `rapido` sobre bench/files, y la huella exacta de cada layout.

Es la vara de la fase 2 del plan de pares y cartera: una idea para acelerar
una sola combinación se queda sólo si baja el tiempo total al menos un 30% y
deja TODOS los layouts idénticos. La huella es el `repr` de las colocaciones
en orden -- id, placa, ángulo, espejo, dx, dy --, que es exactamente lo que
termina en el DXF.

    .venv/bin/python bench/medir_rapido.py --salida out/fase2/antes.tsv
    .venv/bin/python bench/medir_rapido.py --salida out/fase2/a.tsv --comparar out/fase2/antes.tsv
"""

import argparse
import hashlib
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import pack
from nesting.engine.raster.oracle import RasterOracleFactory
from nesting.io.ai_reader import read_ai
from nesting.io.dxf_reader import read_dxf
from nesting.model.sheet import Sheet, SheetSupply
from nesting.pipeline import prepare_parts

FILES_DIR = Path(__file__).parent / "files"

# Los valores por omisión de la CLI, sobre mdf18: lo que corre alguien que
# no toca nada.
CONFIG = NestConfig(sep=5.0, margin=10.0, angles=(0.0, 90.0, 180.0, 270.0),
                    mirror=True, resolution=1.0, effort="rapido", workers=1)
PLAN = SheetSupply(stock=Sheet(1830.0, 2600.0, grain_tolerance=180.0), material_name="mdf18")


@dataclass(frozen=True)
class Fila:
    archivo: str
    segundos: float
    huella: str


def archivos() -> list[Path]:
    return sorted(p for p in FILES_DIR.iterdir() if p.suffix.lower() in (".dxf", ".ai"))


def medir(rutas: list[Path]) -> list[Fila]:
    filas = []
    for ruta in rutas:
        dibujo = read_ai(ruta) if ruta.suffix.lower() == ".ai" else read_dxf(ruta)
        piezas, _, _ = prepare_parts(dibujo)
        empezo = time.perf_counter()
        resultado = pack(piezas, PLAN, CONFIG, RasterOracleFactory())
        segundos = time.perf_counter() - empezo
        layout = repr([(p.part_id, p.sheet, p.transform) for p in resultado.placements])
        filas.append(Fila(ruta.name, segundos, hashlib.sha256(layout.encode()).hexdigest()))
    return filas


def escribir(filas: list[Fila], destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        "".join(f"{f.archivo}\t{f.segundos:.3f}\t{f.huella}\n" for f in filas), encoding="utf-8"
    )


def leer(origen: Path) -> list[Fila]:
    filas = []
    for linea in origen.read_text(encoding="utf-8").splitlines():
        archivo, segundos, huella = linea.split("\t")
        filas.append(Fila(archivo, float(segundos), huella))
    return filas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tiempo de rápido y huella de cada layout.")
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument("--comparar", type=Path, default=None,
                        help="un TSV anterior: informa la baja de tiempo y si los layouts son idénticos")
    args = parser.parse_args(argv)

    filas = medir(archivos())
    escribir(filas, args.salida)
    for f in filas:
        print(f"{f.archivo:<28}{f.segundos:>9.1f} s  {f.huella[:16]}")
    total = sum(f.segundos for f in filas)
    print(f"{'total':<28}{total:>9.1f} s")

    if args.comparar is None:
        return 0
    antes = {f.archivo: f for f in leer(args.comparar)}
    distintos = [f.archivo for f in filas if antes[f.archivo].huella != f.huella]
    total_antes = sum(antes[f.archivo].segundos for f in filas)
    baja = 1.0 - total / total_antes
    print(f"baja de tiempo: {baja * 100:.1f}%  (criterio: al menos 30%)")
    print("layouts idénticos" if not distintos else f"LAYOUTS DISTINTOS: {', '.join(distintos)}")
    return 0 if baja >= 0.30 and not distintos else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

Commit la herramienta sola, pase lo que pase después:

```bash
git add bench/medir_rapido.py
git commit -m "Banco: medir rápido y la huella de cada layout, la vara de la fase 2"
```

- [ ] **Step 2: La medición de base**

Run: `.venv/bin/python bench/medir_rapido.py --salida out/fase2/antes.tsv`
Expected: una fila por `.dxf`/`.ai` de `bench/files` y el total. Correrlo dos
veces y quedarse con la segunda (la primera paga cachés del sistema); anotar
el total. (`out/` no se versiona.)

- [ ] **Step 3: Prototipo A, reusar la transformada de la placa**

En una rama aparte (`git switch -c fase2-a`), agregar a `src/nesting/engine/raster/search.py`:

```python
from scipy.fft import irfft2, next_fast_len, rfft2


class SheetSpectrum:
    """La transformada de una placa, para correlacionarla con muchas máscaras.

    `overlap_counts` vuelve a transformar la placa en cada llamada, y entre
    las orientaciones de una pieza la placa no cambia. Acá se transforma una
    vez, a un tamaño de FFT que alcanza para la máscara más grande pedida
    hasta ahora, y cada máscara paga sólo su transformada y la inversa.
    """

    def __init__(self, sheet: np.ndarray, max_mask_shape: tuple[int, int], pad: int) -> None:
        self.sheet_shape = sheet.shape
        self.max_mask_shape = max_mask_shape
        self.pad = pad
        self.fft_shape = tuple(
            next_fast_len(s + m - 1, real=True) for s, m in zip(sheet.shape, max_mask_shape)
        )
        self._spectrum = rfft2(sheet.astype(np.float64), self.fft_shape)

    def covers(self, rows: int, mask_shape: tuple[int, int], pad: int) -> bool:
        return (
            pad == self.pad
            and rows <= self.sheet_shape[0]
            and mask_shape[0] <= self.max_mask_shape[0]
            and mask_shape[1] <= self.max_mask_shape[1]
        )

    def overlap_counts(self, mask: np.ndarray, rows: int) -> np.ndarray:
        """Lo mismo que `overlap_counts(sheet[:rows], mask)`.

        Vale siempre que la placa esté vacía de `rows` para arriba, que es lo
        que garantiza la frontera del oráculo: la ventana de búsqueda nunca
        corta por debajo de la última fila con material.
        """
        hm, wm = mask.shape
        out = (max(rows - hm + 1, 0), max(self.sheet_shape[1] - wm + 1, 0))
        if 0 in out or 0 in mask.shape:
            return np.zeros(out, dtype=float)
        kernel = rfft2(mask[::-1, ::-1].astype(np.float64), self.fft_shape)
        full = irfft2(self._spectrum * kernel, self.fft_shape)
        return full[hm - 1:hm - 1 + out[0], wm - 1:wm - 1 + out[1]]
```

En `src/nesting/engine/raster/scoring.py`, `position_scores` y `best_position` ganan un parámetro final `overlap=overlap_counts`, y la línea `counts = overlap_counts(sheet, band)` pasa a `counts = overlap(sheet, band)`.

En `src/nesting/engine/raster/oracle.py`: importar `COLLISION_THRESHOLD` y `SheetSpectrum` de `search`; en `__init__` y en `reset`, `self._spectrum: SheetSpectrum | None = None`; al final de `place`, `self._spectrum = None`; y reemplazar en `_search` y `_buscar_con` las dos correlaciones contra `padded`:

```python
    def _counts(self, pad: int, padded_rows: int, mask_shape: tuple[int, int]):
        """Una función máscara -> `overlap_counts(padded, máscara)`, con la
        transformada de la placa reusada mientras la placa no cambie."""
        s = self._spectrum
        if s is None or not s.covers(padded_rows, mask_shape, pad):
            rows = max(padded_rows, s.sheet_shape[0] if s is not None and s.pad == pad else 0)
            prev = s.max_mask_shape if s is not None and s.pad == pad else (0, 0)
            body = min(rows - 2 * pad, self._sheet.shape[0])
            s = SheetSpectrum(
                np.pad(self._sheet[:body], pad, mode="constant", constant_values=False),
                (max(mask_shape[0], prev[0]), max(mask_shape[1], prev[1])),
                pad,
            )
            self._spectrum = s
        return lambda _sheet, mask: s.overlap_counts(mask, padded_rows)
```

En `_search`, reemplazar desde `padded = np.pad(...)` hasta el final del
método por:

```python
        padded = np.pad(window, pad, mode="constant", constant_values=False)
        counts = self._counts(pad, padded.shape[0], masks.clearance.shape)

        if self._arbitro is not None:
            optimista = self._buscar_con(
                part, angle, mirror, masks, padded,
                masks.holgura_optimista(self._radio_optimista),
                arbitrar=True, counts=counts,
            )
            if optimista is not None:
                return optimista

        return self._buscar_con(
            part, angle, mirror, masks, padded, masks.clearance,
            arbitrar=False, counts=counts,
        )
```

En `_buscar_con`, agregar el parámetro de palabra clave `counts` después de
`arbitrar`, y reemplazar sus primeras líneas (hasta el cálculo de `score`)
por:

```python
        pad = masks.pad
        feasible = counts(padded, holgura) < COLLISION_THRESHOLD
        if feasible.size == 0 or not feasible.any():
            return None

        score = position_scores(
            feasible, padded, self._banda_de_contacto(masks), self._config.weights,
            overlap=counts,
        )
```

Run: `.venv/bin/pytest tests/engine`
Expected: PASS (si algo falla, el prototipo está mal armado: arreglarlo antes de medir, porque medir algo roto no decide nada).

Run: `.venv/bin/python bench/medir_rapido.py --salida out/fase2/a.tsv --comparar out/fase2/antes.tsv`
Expected: la baja de tiempo y si los layouts son idénticos. Anotar las dos cifras.

- [ ] **Step 4: Prototipo B, repartir las orientaciones en hilos**

Desde `main` (`git switch main && git switch -c fase2-b`), en `src/nesting/engine/packer.py`:

```python
from concurrent.futures import ThreadPoolExecutor

QUERY_THREADS = 4
"""Cuántos hilos consultan las orientaciones de una pieza a la vez (fase 2, idea B)."""

_query_pool: ThreadPoolExecutor | None = None


def _query_orientations(oracle, part, choices):
    """Todas las consultas de una pieza, en hilos, en el orden de `choices`.

    Las máscaras se piden antes, desde este hilo: `MaskCache` no es seguro
    entre hilos para las altas, y `best_placement` es de sólo lectura sobre
    todo lo demás (la grilla, el árbitro).
    """
    global _query_pool
    warm = getattr(oracle, "warm", None)
    if warm is not None:
        warm(part, choices)
    if _query_pool is None:
        _query_pool = ThreadPoolExecutor(max_workers=QUERY_THREADS)
    return list(_query_pool.map(lambda c: oracle.best_placement(part, c[0], c[1]), choices))
```

y reemplazar `_best_over_orientations` entero por esta versión, que hace
las mismas consultas en hilos y elige con la misma lógica (el orden de
`choices` se conserva, así que el resultado es el mismo por construcción):

```python
def _best_over_orientations(
    oracle: Oracle,
    part: Part,
    choices: Sequence[tuple[float, bool]],
    rank: int = 0,
) -> tuple[float, bool, float, float] | None:
    """Ask the oracle about every orientation and keep the best-scoring one.

    Con `rank > 0`, la `rank`-ésima mejor (o la peor que entra). Las
    consultas corren en hilos (`_query_orientations`), pero la elección se
    hace sobre los resultados en el orden de `choices`: en empate gana la
    primera, igual que antes.
    """
    answers = _query_orientations(oracle, part, choices)
    if rank == 0:
        best: tuple[float, bool, float, float] | None = None
        best_score = float("-inf")
        for (angle, mirror), spot in zip(choices, answers):
            if spot is None:
                continue
            x, y, score = spot
            if score > best_score:
                best_score = score
                best = (angle, mirror, x, y)
        return best

    spots = [
        (-spot[2], position, angle, mirror, spot[0], spot[1])
        for position, ((angle, mirror), spot) in enumerate(zip(choices, answers))
        if spot is not None
    ]
    if not spots:
        return None
    spots.sort()
    _, _, angle, mirror, x, y = spots[min(rank, len(spots) - 1)]
    return angle, mirror, x, y
```

En `src/nesting/engine/raster/oracle.py`, agregar a `RasterOracle`:

```python
    def warm(self, part: Part, choices) -> None:
        """Pide todas las máscaras desde el hilo que llama, antes de consultar en hilos."""
        for angle, mirror in choices:
            self._masks(part, angle, mirror)
```

En `src/nesting/engine/cartera.py`, agregar `import threading`, a
`_WatchedOracle`:

```python
    def warm(self, part: Part, choices) -> None:
        warm = getattr(self._inner, "warm", None)
        if warm is not None:
            warm(part, choices)
```

y reemplazar `_QueryCounter.add` por:

```python
    def add(self) -> None:
        # Con las consultas en hilos (fase 2, idea B), `+= 1` desde varios
        # hilos a la vez puede perder cuentas.
        with self._lock:
            self.total += 1
            due = self.total - self._reported >= self._watch.report_every
        if due:
            self.flush()
```

con `self._lock = threading.Lock()` en su `__init__`.

Run: `.venv/bin/pytest tests/engine`
Expected: PASS

Run: `.venv/bin/python bench/medir_rapido.py --salida out/fase2/b.tsv --comparar out/fase2/antes.tsv`
Expected: la baja de tiempo y si los layouts son idénticos. Anotar las dos cifras.

- [ ] **Step 5: Decidir con el criterio, y dejar escrita la medición**

Agregar a `docs/superpowers/calibracion.md` una sección (completar la tabla con lo medido en los Pasos 2 a 4):

```markdown
## Fase 2 de pares y cartera — acelerar una sola combinación

Criterio fijado antes de medir: al menos 30% menos de tiempo total de
`rapido` sobre `bench/files` (mdf18, valores por omisión de la CLI, 1 mm/px),
con todos los layouts idénticos (`bench/medir_rapido.py --comparar`).

| variante | total | baja | layouts idénticos | se queda |
|---|---|---|---|---|
| antes | … s | — | — | — |
| A: transformada de la placa reusada | … s | …% | sí / no | sí / no |
| B: orientaciones en 4 hilos | … s | …% | sí / no | sí / no |

Máquina: … núcleos, … GB, fecha ….
```

Con esa tabla:

- **Si ninguna pasa:** borrar las ramas `fase2-a` y `fase2-b`, commitear sólo la sección nueva en `main` y terminar la tarea.
- **Si pasa una:** mergear su rama a `main`, y escribir sus tests (Paso 6) antes del commit final.
- **Si pasan las dos:** medir las dos juntas (mergear `fase2-a` y `fase2-b` en una tercera rama y correr `medir_rapido.py --comparar out/fase2/antes.tsv`); si la combinación también pasa y baja más que cada una, quedarse con las dos; si no, con la que más bajó. Agregar la fila a la tabla.

- [ ] **Step 6: Tests de lo que se quedó (sólo si algo pasó el criterio)**

Si se quedó A, crear `tests/engine/raster/test_espectro.py`:

```python
"""La transformada reusada da lo mismo que correlacionar de cero."""

import numpy as np
import pytest

from nesting.engine.raster.search import SheetSpectrum, overlap_counts


@pytest.mark.parametrize("semilla", range(5))
def test_da_lo_mismo_que_overlap_counts(semilla):
    rng = np.random.default_rng(semilla)
    placa = np.zeros((300, 400), dtype=bool)
    placa[:120] = rng.random((120, 400)) < 0.3  # material sólo abajo de la frontera
    espectro = SheetSpectrum(placa, (60, 80), pad=0)
    for _ in range(4):
        mascara = rng.random((rng.integers(5, 60), rng.integers(5, 80))) < 0.5
        for filas in (150, 300):
            esperado = overlap_counts(placa[:filas], mascara)
            assert espectro.overlap_counts(mascara, filas) == pytest.approx(esperado, abs=1e-6)


def test_una_mascara_que_no_entra_da_vacio_con_la_forma_de_siempre():
    espectro = SheetSpectrum(np.zeros((50, 50), dtype=bool), (60, 10), pad=0)
    assert espectro.overlap_counts(np.ones((60, 10), dtype=bool), 50).shape == (0, 41)
```

Si se quedó B, crear `tests/engine/test_hilos.py`:

```python
"""Las orientaciones en hilos dan exactamente el mismo layout."""

from nesting.engine import packer
from nesting.engine.oracle import NestConfig
from nesting.engine.packer import _pack_once
from nesting.engine.raster.oracle import RasterOracleFactory
from nesting.model.part import Part
from nesting.model.sheet import Sheet, SheetSupply


def test_uno_o_cuatro_hilos_dan_el_mismo_layout(monkeypatch):
    piezas = [Part(i, ((0, 0), (300 + 7 * i, 0), (300, 90 + 5 * i), (0, 120)), (), (i,))
              for i in range(10)]
    plan = SheetSupply(stock=Sheet(1000.0, 1000.0, grain_tolerance=180.0))
    config = NestConfig(sep=5.0, margin=10.0, resolution=4.0, effort="rapido")

    monkeypatch.setattr(packer, "QUERY_THREADS", 1)
    monkeypatch.setattr(packer, "_query_pool", None)
    uno = _pack_once(piezas, plan, config, RasterOracleFactory())
    monkeypatch.setattr(packer, "QUERY_THREADS", 4)
    monkeypatch.setattr(packer, "_query_pool", None)
    cuatro = _pack_once(piezas, plan, config, RasterOracleFactory())

    assert uno.placements == cuatro.placements
```

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos.

- [ ] **Step 7: Commit**

Si no se quedó nada:

```bash
git add docs/superpowers/calibracion.md
git commit -m "Fase 2 medida: ninguna idea baja rápido un 30% con el mismo layout, no se hace"
```

Si se quedó algo (después del merge del Paso 5):

```bash
git add docs/superpowers/calibracion.md tests/engine/raster/test_espectro.py tests/engine/test_hilos.py
git commit -m "Fase 2: <la idea que quedó> baja rápido un N% con el mismo layout"
```

(con `<la idea que quedó>` y `N` según la tabla, y sin los tests de la idea que no se quedó).

---

## Autorrevisión del plan contra la spec

| Sección de la spec | Dónde |
|---|---|
| 2. Piezas iguales (huella, congruencia, `g`, `Clase`) | Tarea 2 |
| 3.1 Qué clases se emparejan (≥ 2 miembros, 2%, hasta dos) | Tarea 3 (`pairable_classes`) |
| 3.2 Tipos de par (FFT, caja en píxeles, supresión, `sep ≤ g < 2·sep`, entra en el área útil, 6/10, veta, espejo) | Tarea 3; supresión a 200 mm por la Decisión 1 |
| 3.3 La compuesta (puente redondo, agujeros, un solo polígono, tabla de miembros) | Tareas 3 y 4 |
| 3.4 Desarmar (`componer`, antes de verificar) | Tareas 1 y 4; la cartera desarma en `_finish` y en `evaluate` (Tarea 5) |
| 4.1 Variantes en orden fijo | Tarea 5 (`VariantSource`) |
| 4.2 Cuántas se evalúan, monotonía | Tarea 5 (`EFFORT_BATCHES`, `planned_variants`, tests de prefijo) |
| 4.3 Cuándo no se busca | Tarea 5 (`cota_minima`, corte en `run_portfolio`) |
| 4.4 Paralelo (spawn, `freeze_support`, un caché por proceso, cortar, desempate, recuperación y compactación sólo en la ganadora) | Tareas 5 y 6 |
| 4.5 Avance, cancelación, tiempo estimado | Tareas 5 (`_Progress`), 6 (cola, evento, texto) y 7 (Paso 11) |
| 5. La cota y "No se puede con menos placas" | Tareas 5 (`cota_minima`) y 8 |
| 6. Núcleos (omisión, tope por memoria, `validar`, recorte con aviso, pantalla, `/api/sistema`, `--nucleos`, estimado previo) | Tarea 7 |
| 7. Pruebas | Tareas 1 a 9 (la de la banqueta y el caso sintético, en la 9) |
| 8. Fase 2 | Tarea 11 |
