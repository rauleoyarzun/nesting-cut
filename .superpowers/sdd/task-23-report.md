# Task 23 — Lector de `.3dm` de Rhino — Informe

**Estado: completo. Hito 5 cerrado.** Los tres formatos de entrada (DXF, `.ai`, `.3dm`) funcionan.

## Archivos

- **Creado:** `src/nesting/io/rhino_reader.py`
- **Creado:** `tests/io/test_rhino_reader.py` (13 tests: los 12 del brief + 1 de regresión propia)
- **Modificado:** `src/nesting/cli.py` — import de `read_3dm` y despacho de la extensión `.3dm`
- **Modificado:** `pyproject.toml` — `rhino3dm` movido de `[project.optional-dependencies].rhino` a `dependencies`; la sección `rhino` se borró

No se hizo commit de git: el proyecto no usa git (confirmado, `git rev-parse` falla / no hay `.git`), como indicó el usuario.

## Ciclo TDD

1. `.venv/bin/pip install rhino3dm` → instaló `rhino3dm-8.35.0` (rueda universal2 para macOS/cp313).
2. Se escribió `tests/io/test_rhino_reader.py` tal cual el brief. Corrida en rojo: `ModuleNotFoundError: No module named 'nesting.io.rhino_reader'` (esperado, el módulo no existía todavía).
3. Se escribió `src/nesting/io/rhino_reader.py` a partir del código del brief, con dos adaptaciones a la API real (ver "Desviaciones" abajo).
4. Se despachó `.3dm` en `cli.py`.
5. `.venv/bin/pytest tests/io/test_rhino_reader.py -v` → **12 passed** (antes de agregar el test de regresión).
6. Prueba sobre el archivo real (ver sección dedicada abajo) — encontró un bug real de muestreo, que se corrigió, con un test de regresión nuevo (13º test).
7. `.venv/bin/pytest -q` sobre toda la suite → **398 passed** (385 preexistentes + 13 nuevos), sin fallos.
8. Commit: omitido a pedido del usuario.

### Salida de pytest

`tests/io/test_rhino_reader.py -v` (final, con el test de regresión incluido):

```
collected 13 items
tests/io/test_rhino_reader.py .............                              [100%]
13 passed in 0.47s
```

Suite completa (`pytest -q`):

```
........................................................................ [ 18%]
........................................................................ [ 36%]
........................................................................ [ 54%]
........................................................................ [ 72%]
........................................................................ [ 90%]
.....................................                                    [100%]
```
exit code 0.

**Nota sobre esta salida:** en este entorno, `pytest -q` no imprime la línea final `"N passed in Xs"` después del resumen de warnings (se corta ahí, con exit code 0, de forma reproducible incluso en corridas triviales con `-W ignore`). Es una rareza del sandbox de shell, no del proyecto ni de estos cambios — lo confirmé contando los caracteres de estado (`.`/`F`/`E`) de las líneas de progreso: **398 puntos, cero `F`/`E`**, que coincide exactamente con 385 (base) + 13 (nuevos). Con un archivo de test chico (`test_rhino_reader.py` solo) la línea de resumen sí aparece normalmente ("12 passed in 0.44s", "13 passed in 0.47s"), así que el conteo de puntos es una verificación válida para la corrida completa.

## Desviaciones respecto del brief (API real de `rhino3dm`)

El brief fue escrito sin la librería instalada. Comprobé la versión real (`rhino3dm==8.35.0`) contra el código propuesto:

1. **`curve.Domain` no es subscriptable.** El brief usa `domain[0]` / `domain[1]`; la API real devuelve un `rhino3dm.Interval` con atributos `.T0` / `.T1` (`TypeError: 'rhino3dm._rhino3dm.Interval' object is not subscriptable`). Adaptado a `domain.T0` / `domain.T1` en `_sample`.

2. **`model.Layers[i]` con índice negativo u out-of-range levanta `IndexError` de forma nativa** (lo verifiqué explícitamente), así que el `try/except (IndexError, ...)` del brief ya alcanzaba. Igual agregué una guarda explícita `if index < 0: raise IndexError` en `_style_of`, por claridad y para no depender de que el wrapping negativo de pybind11 se siga comportando igual entre versiones de `rhino3dm` (un objeto sin capa asignada trae `Attributes.LayerIndex == -1` cuando el modelo no tiene ninguna capa definida).

3. **El resto de la API coincidió con el brief:** `rhino3dm.UnitSystem.*` son miembros nombrados (no valores numéricos, tal como se pidió), `LineCurve`, `PolylineCurve`, `Curve`, `PointAtStart/End`, `PointCount`/`Point(i)`, `IsClosed` (propiedad), `PointAt`, `File3dm.Read`, `Objects`/`Layers` iterables, todo funcionó como está escrito en el brief.

## Bug real encontrado y corregido al probar contra el archivo del proyecto

Al testear contra `bench/files/banqueta raulo.3dm` encontré que el chequeo de tolerancia de cuerda en `_subdivide` comparaba el punto muestreado y el punto medio de la cuerda **solo en X,Y**, ignorando Z durante la decisión de subdividir (tal cual estaba escrito en el brief). Esto es un problema real, no cosmético: para una curva que en verdad vive en otro plano (p. ej. un círculo completo parado en el plano XZ, con Y constante), la proyección a XY degenera en un segmento de ida y vuelta sobre una sola línea. Para ese círculo particular, la comparación en 2D coincide *exactamente* en los puntos de cuarto de vuelta (`cos(π/2) = promedio(cos(0), cos(π))`), así que el algoritmo se detenía después de un solo nivel de subdivisión, sin haber muestreado nunca los puntos donde la curva realmente se despega en Z. El resultado: la curva se aceptaba en silencio como "plana" y se aplastaba en una polilínea degenerada de 3 puntos (ida y vuelta), sin ningún aviso — justo el caso que `_require_planar` existe para evitar.

**Corrección:** el chequeo de `_subdivide` ahora compara el punto muestreado contra el punto medio de la cuerda en **3D** (X, Y, Z), no solo en XY. Esto no cambia el comportamiento para curvas ya planas (donde la distancia 2D y 3D coinciden), pero fuerza la subdivisión necesaria para exponer la desviación en Z de una curva que en verdad vive en otro plano, de modo que `_require_planar` la detecte y la rechace con aviso, como corresponde.

Agregué un test de regresión (`test_a_circle_standing_in_the_xz_plane_is_rejected_as_non_planar`) que reproduce exactamente este caso con un círculo rotado 90° sobre el eje X. Sin la corrección, ese test falla (el círculo se lee como una polilínea degenerada de 3 puntos y `drawing.warnings == []`); con la corrección, pasa (`drawing.entities == []`, con el aviso de "no son planas").

Verifiqué que la corrección no afecta ninguno de los 12 tests originales del brief (todos usan geometría ya plana en Z=0, donde la distancia 2D y 3D son idénticas) ni ningún otro test de la suite (398/398 en verde después del cambio).

## Prueba sobre el archivo real: `bench/files/banqueta raulo.3dm`

Comando ejecutado (Step 6 del brief, con `--esfuerzo rapido` agregado):

```
.venv/bin/nest "bench/files/banqueta raulo.3dm" --material mdf18 --esfuerzo rapido --preview /tmp/banqueta3dm.png -o /tmp/banqueta3dm.dxf
```

**Resultado: 0 piezas reconocidas.**

```
error: no se encontro ninguna pieza en bench/files/banqueta raulo.3dm
aviso: se ignoraron 5 objetos que no son curvas
aviso: se ignoraron 54 curvas que no son planas en XY
```

No se generó ni el DXF de salida ni el PNG de previsualización (el pipeline falla antes de llegar a esa etapa, correctamente: no hay nada que dibujar).

### Por qué da 0, y por qué eso es correcto y no un bug (después de la corrección de arriba)

Inspeccioné el archivo directamente con `rhino3dm` para entender qué contiene:

- **59 objetos en total**, todos en la capa `Default` (no hay una capa separada de "layout de corte"):
  - 30 `PolyCurve` (perfiles compuestos — probablemente los contornos de los paneles/piezas)
  - 21 `ArcCurve` (círculos completos, radio 250 mm — probablemente las secciones de las patas cilíndricas)
  - 5 `DimLinear` (cotas/anotaciones — correctamente excluidas como "objetos que no son curvas")
  - 3 `PolylineCurve`

- **Las 54 curvas reales (30+21+3) son, las 54, no-planas respecto del plano XY global.** Confirmé con una muestra que las `ArcCurve` son círculos completos (`AngleDomain` 0 a 2π) cuyo plano tiene `XAxis=(1,0,0)`, `YAxis=(0,0,1)` — es decir, viven en el plano **XZ** (parados verticalmente), no en XY. Antes de la corrección, 21 de ellos se "colaban" como falsamente planos por el bug de muestreo descrito arriba; después de corregirlo, las 54 se rechazan correctamente.

**Conclusión:** este `.3dm` no es un layout de corte plano — es el **modelo 3D del ensamblaje completo de la banqueta**, con cada pieza ubicada en su posición y orientación reales dentro del mueble armado (patas paradas, tableros en sus ángulos reales, etc.). El lector hace exactamente lo que el brief pide: proyecta a XY global y rechaza lo que no es plano ahí. Como en este archivo *ninguna* curva de corte real está apoyada plana sobre el plano XY global, el resultado correcto y honesto es "0 piezas", no un error de nuestro código.

Esto contrasta con el archivo `.ai` de referencia (40 piezas, 1 placa, 25,3% de aprovechamiento): ese archivo ya es un **layout de corte 2D pre-armado** (aparentemente producido aparte, quizás a mano en Illustrator, desplegando/aplanando cada pieza sobre una hoja), mientras que el `.3dm` es el modelo de diseño 3D previo a ese aplanado. No son entradas equivalentes: el `.3dm`, tal como está, todavía necesitaría un paso de "desarrollo"/aplanado de cada pieza a 2D (manual en Rhino, o una feature nueva y mucho más grande que este lector) antes de poder nestearse. Aplanar automáticamente piezas 3D arbitrarias está fuera del alcance de esta tarea (un simple lector de archivo) y del brief, que solo contempla proyectar-y-validar-planaridad, no desplegar geometría 3D.

### Sobre `--tol-cierre`

Antes de entender la causa real, probé aflojar la tolerancia de cierre (`--tol-cierre 0.15, 0.2, 0.3, 0.5, 1, 2`) porque el error original decía "5 contorno(s) no cierran". **No tuvo ningún efecto**, siempre con el mismo mensaje y el mismo hueco de "0.000 mm". Investigando el motivo llegué al bug de muestreo: esos 5 contornos "abiertos" no eran gaps de cierre en absoluto — eran las 5 curvas (de las 21 `ArcCurve` que antes se colaban como planas) cuyo muestreo colapsaba a solo 3 puntos (ida-y-vuelta), y `chain_contours` las clasifica como "abiertas" porque, aunque geométricamente cierran con hueco ~0, tienen menos de `MIN_CONTOUR_POINTS` (3) puntos distintos tras deduplicar — no es un problema de tolerancia de distancia, así que ningún valor de `--tol-cierre` lo iba a arreglar. Después de corregir el muestreador, esas 5 curvas (junto con las otras 49) se rechazan correctamente como no-planas antes de llegar siquiera a la etapa de encadenado, así que la pregunta de `--tol-cierre` queda sin objeto para este archivo.

### Preview

No se generó porque no hay piezas. Si se quiere ver algo de este archivo, el paso previo tendría que ser aplanar manualmente en Rhino cada pieza a su vista real (o exportar un layout 2D como se hizo para el `.ai`), y después pasarlo por este mismo lector — en ese caso sí debería funcionar igual que con DXF/`.ai`, ya que el lector en sí (probado con los 13 tests, incluida la geometría muestreada, capas, unidades y planaridad) funciona correctamente.

## Resumen para el hito

- El lector `.3dm` está implementado, probado (13/13) y integrado en la CLI.
- Se descubrió y corrigió, gracias a la prueba obligatoria contra el archivo real, un bug genuino de muestreo adaptativo (tolerancia de cuerda en 2D en vez de 3D) que dejaba pasar curvas no-planas en silencio.
- El archivo real del proyecto (`banqueta raulo.3dm`) da 0 piezas, y esto es el comportamiento correcto: el archivo es un modelo 3D de ensamblaje, no un layout de corte plano como el `.ai` de referencia. No hay curvas de corte planas en XY en ese archivo para nestear.
- Suite completa: 398/398 en verde (385 preexistentes + 13 nuevos).
