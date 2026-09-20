# Nesting

**Acomoda piezas en placas para que sobre la menor cantidad de material posible.**

Le das un archivo vectorial con las piezas a cortar, elegís sobre qué placa vas a
cortarlas, y te devuelve un DXF listo para la fresadora.

[![Licencia: MIT](https://img.shields.io/badge/Licencia-MIT-informational.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/Python-3.13%2B-informational.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-856-informational.svg)](tests/)

---

## Qué hace

Abrís el archivo, elegís el material y apretás **Acomodar**.

| | |
|---|---|
| **Entra** | `.dxf`, `.ai` o `.3dm` con los contornos de las piezas |
| **Sale** | un `.dxf` con todo acomodado, más una previsualización en PNG |
| **Decide** | cuántas placas, dónde va cada pieza y con qué rotación |
| **Respeta** | la separación entre piezas, el margen contra el borde y la veta del material |

Además te muestra **qué descartó y por qué**, marcado sobre tu propio dibujo: los
tramos sueltos, las curvas que no apoyan en el plano, los contornos que no cierran.
Eso aparece al segundo de abrir el archivo, antes de comprometerte a un acomodo
que puede tardar varios minutos.

---

## Empezar

### La aplicación de escritorio

```bash
git clone git@github.com:rauleoyarzun/nesting-cut.git && cd nesting-cut
python3.13 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/nest-app
```

Abre una ventana. No hay que levantar ningún servidor ni abrir ninguna URL a
mano: el programa arranca uno en `127.0.0.1` con un puerto al azar y lo cierra
cuando cerrás la ventana.

### La línea de comandos

```bash
.venv/bin/nest piezas.ai --material mdf18 -o cortado.dxf
```

Hace exactamente lo mismo sin abrir ninguna ventana. Útil para automatizar o
para correrlo sobre un servidor sin pantalla.

---

## La pantalla

```
┌─────────────────────────────────────────────────────────┐
│ Nesting                                    [Materiales] │
├──────────────────────┬──────────────────────────────────┤
│  Archivo             │  Previsualización │ Revisión     │
│  ▸ robot.ai          │                                  │
│    94 piezas         │                                  │
│    · 2 descartes     │        [ el dibujo ]             │
│                      │                                  │
│  Material  ▾         │                                  │
│  Separación  5 mm    │                                  │
│  Borde      10 mm    │        − 150% +  Ajustar         │
│  Copias      1       │                                  │
│  Esfuerzo  ▾         │                                  │
│                      │                                  │
│  › Opciones avanzadas│                                  │
├──────────────────────┴──────────────────────────────────┤
│ [Acomodar]  1 placa · 47.7% · sobrante 715 mm  [Guardar]│
└─────────────────────────────────────────────────────────┘
```

**Previsualización** muestra cómo quedó el acomodo. **Revisión** marca lo que se
descartó, con una lupa por cada descarte y el motivo escrito al lado. Las dos se
pueden ampliar: rueda del mouse para acercarte donde tengas el cursor, arrastrar
para moverte, doble click para alternar entre 100% y ajustada.

Mientras corre, la barra de abajo dice en qué va (`Intento 2 de 3 · ubicadas 47
de 93 · placa 1`) y podés **cancelar** en cualquier momento. Cancelar no deja un
resultado a medias: el DXF no llega a escribirse.

---

## Materiales

El catálogo se edita desde la pantalla **Materiales**: nombre, ancho, alto y si
hay que respetar la veta.

Viene con cuatro:

| Material | Placa (mm) | Veta |
|---|---|---|
| `mdf18` | 1830 × 2600 | No importa |
| `mdf15` | 1830 × 2600 | No importa |
| `multilam18` | 1220 × 2440 | Respetar |
| `fenolico18` | 1220 × 2440 | Respetar |

Los tuyos se guardan en tu carpeta de usuario, **no adentro del programa**, así
que sobreviven a una actualización:

| | |
|---|---|
| macOS | `~/Library/Application Support/nesting/materials.yaml` |
| Windows | `%APPDATA%\nesting\materials.yaml` |
| Linux | `~/.local/share/nesting/materials.yaml` |

Desde la pantalla de materiales podés volver al catálogo original cuando quieras.

---

## Opciones

Lo que la pantalla muestra como controles, la CLI lo toma como flags. Son los
mismos parámetros.

| Control | Flag | Qué es |
|---|---|---|
| Material | `--material` | Clave del catálogo. Obligatorio. |
| Separación | `--sep` | Milímetros mínimos entre dos piezas. |
| Borde | `--borde` | Margen contra el borde de la placa. |
| Copias | `--copias` | Cuántas veces repetir todo el contenido del archivo. |
| Esfuerzo | `--esfuerzo` | `rapido` (1 pasada), `normal` (3) o `lento` (12). |
| Ángulos | `--angulos` | Rotaciones candidatas, separadas por coma. |
| Permitir espejadas | `--sin-espejo` | Si una pieza se puede dar vuelta como un guante. La pantalla lo trae activado; el flag lo apaga. |
| Tolerancia de cierre | `--tol-cierre` | Cuánto puede separarse un contorno para considerarlo cerrado. |
| Resolución | `--resolucion` | Milímetros por píxel del raster. Más fino acomoda un poco mejor y tarda mucho más. |
| — | `--unidades` | Unidades del archivo, si el archivo no las declara. |
| — | `--preview` | Ruta del PNG de previsualización. |
| — | `--diagnostico` | Ruta del PNG que marca los descartes. Si es lo único que pedís, no acomoda nada y sale en un segundo. |

**Más esfuerzo no siempre da un resultado mejor, pero nunca da uno peor**: se
queda con la mejor de todas las pasadas.

---

## Lo que nunca va a hacer

**No escribe un DXF que no haya verificado.** Antes de tocar el disco comprueba
que ninguna pieza se pise con otra, que ninguna se salga de la placa y que se
respeten la separación y el margen que pediste. Si algo de eso falla, **no se
escribe nada** y te dice qué pasó.

Esa regla no se ablanda. El archivo que sale de acá va a una máquina que corta
madera de verdad.

---

## Formatos

| | |
|---|---|
| `.dxf` | Lo que exporta casi cualquier CAD. |
| `.ai` | Sólo los **AI3 / PostScript**, que son texto plano y arrancan con `%!PS-Adobe`. Es lo que exportan Rhino y CorelDRAW. Si lo abrís con un editor de texto y no empieza así, no sirve: convertilo a DXF. |
| `.3dm` | Rhino. Se leen las curvas que apoyan en el plano XY; el resto se descarta y se te avisa cuáles. |
| `.cdr` | **No.** Es formato binario cerrado de Corel y no hay parser libre confiable. Exportalo desde CorelDRAW a DXF o a AI3. |

---

## Desarrollo

```bash
.venv/bin/pip install -e ".[dev]"    # pytest, httpx y pyinstaller
.venv/bin/pytest                     # la suite entera (856, ~4 min)
.venv/bin/pytest tests/app           # sólo la interfaz (~10 s)
```

### Armar el ejecutable

```bash
./packaging/construir.sh
```

Deja `dist/Nesting/` (~106 MB) y un `.zip` (~56 MB). Va en modo carpeta y no
archivo único a propósito: el modo de archivo único se autodescomprime en cada
arranque, y con scipy y rhino3dm adentro eso son varios segundos de espera cada
vez que alguien abre el programa.

El script **verifica el paquete antes de comprimirlo** (`--autotest`). No es
opcional: a un paquete al que le falta un recurso o un módulo oculto se lo ve
perfecto en la máquina donde se armó y falla en la del que lo recibe.

### Medir si un cambio fue una mejora

```bash
.venv/bin/python bench/run_bench.py
```

Placas, porcentaje de aprovechamiento y segundos sobre archivos reales. Ver
[`bench/README.md`](bench/README.md).

### Diagnosticar la ventana

```bash
.venv/bin/python herramientas/ventana_real.py
```

Hay defectos de esta interfaz que no se ven leyendo el código ni corriendo la
página en un navegador: viven en el hilo principal del sistema de ventanas. Esta
herramienta maneja la ventana de verdad desde afuera y los detecta. Ver
[`herramientas/README.md`](herramientas/README.md).

---

## Cómo está armado

```
src/nesting/       el motor: leer, acomodar, verificar, escribir
src/nesting_app/   la interfaz: servidor local, ventana, pantallas
```

**Al importarse, `nesting` no toca `nesting_app`.** La flecha va en un solo
sentido, y es lo que permite que el motor se use desde la CLI, desde la ventana o
desde un servidor web sin cambiarle una línea. Hay una sola excepción, perezosa y
documentada donde vive (`nesting/model/material.py`): para encontrar el catálogo
que viene con el programa hace falta saber si estamos corriendo desde el repo o
desde un ejecutable empaquetado, y eso lo sabe la interfaz. Si el paquete de la
interfaz no está —una instalación del motor a secas— se cae a la cuenta de
siempre y sigue andando.

Adentro de la interfaz hay otra separación igual de deliberada:
`nesting_app/archivos.py` es **el único archivo que sabe si estamos en escritorio
o en la web**. En escritorio el diálogo nativo devuelve una ruta del disco; en la
web llega el contenido subido. Los dos caminos terminan en lo mismo, y de ahí en
adelante nadie vuelve a preguntar de dónde salió el archivo.

Las decisiones de diseño, con sus razones, están en
[`docs/superpowers/specs/`](docs/superpowers/specs/).

---

## Licencia

[MIT](LICENSE) © Raul Oyarzun
