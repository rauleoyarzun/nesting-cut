# Nesting

*[English](README.md)*

**Acomoda piezas en placas usando la menor cantidad de material posible, para que
lo que sobra quede libre y entero.**

Le das un archivo vectorial con las piezas a cortar, elegís sobre qué placa vas a
cortarlas, y te devuelve un DXF listo para la fresadora.

No se trata sólo de gastar menos. El motor busca primero la menor cantidad de
placas; después, dejar en la última **la menor cantidad de material posible**,
que es lo que acerca a no necesitar esa placa; y recién ahí, con la misma
cantidad de material arriba, dejarla **lo más compactada posible**, para que la
franja que queda libre siga entera para el próximo trabajo.

[![Licencia: MIT](https://img.shields.io/badge/Licencia-MIT-informational.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/Python-3.13%2B-informational.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-1028-informational.svg)](tests/)

---

## Qué hace

Abrís el archivo, elegís el material y apretás **Acomodar**.

| | |
|---|---|
| **Entra** | `.dxf`, `.ai` o `.3dm` con los contornos de las piezas |
| **Sale** | un `.dxf` con todo acomodado, más una previsualización en PNG |
| **Decide** | cuántas placas, dónde va cada pieza y con qué rotación |
| **Respeta** | la separación entre piezas, el margen contra el borde y la veta del material |
| **Busca** | la menor cantidad de placas; después, dejar la menor cantidad de material posible en la última; después, con la misma cantidad, dejarla lo más compactada posible |

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

![La pantalla principal: el archivo elegido, los parámetros y el acomodo terminado](docs/imagenes/pantalla.png)

Un acomodo de verdad: las 12 piezas de una banqueta —asientos redondos y patas
cóncavas—, tres copias de cada una, sobre una placa de MDF de 1830 × 2600.
Entraron todas en **una sola placa**, ocupando el 40.7% de la superficie, y
—esto es lo que importa— la franja de **694 mm** que se ve libre arriba queda
entera para el próximo trabajo.

El archivo de la captura lo genera `bench/make_sample.py`, así que podés
reproducirla.

El resultado dice cuatro cosas: **cuántas placas** hicieron falta, **qué
porcentaje** de esa superficie quedó ocupado por piezas, el **sobrante** —los
milímetros de franja libre en la última placa, medidos desde donde termina la
pieza más alta hasta el borde— y el **material en la última placa**, en m².

Las dos últimas se muestran juntas a propósito, porque compiten: el motor
elige el acomodo que deja menos material en la última placa, y eso a veces
acorta la franja libre a cambio. Ver las dos es lo que te deja decidir si el
canje conviene para este trabajo: la franja te dice qué recorte te llevás, los
m² te dicen qué tan cerca estuviste de no necesitar esa placa.

Mientras corre, la barra de abajo dice en qué va (`Intento 2 de 3 · ubicadas 47
de 93 · placa 1`) y podés **cancelar** en cualquier momento. Cancelar no deja un
resultado a medias: el DXF no llega a escribirse.

### Revisión: qué se descartó y por qué

![La solapa Revisión: los descartes marcados sobre el dibujo original, con una lupa y el motivo de cada uno](docs/imagenes/revision.png)

Los descartes marcados **sobre tu propio dibujo**, con un círculo de color en el
lugar exacto, una lupa por cada uno y el motivo escrito al lado. Acá son dos
tramos sueltos de 10 y 12 mm que no encierran área, así que no pueden ser el
contorno de ninguna pieza; la lupa muestra dónde están y a qué escala. Abajo,
cuántos hubo de cada clase.

Esto aparece **al segundo de abrir el archivo**, sin acomodar nada. Es cuando
sirve: todavía estás a tiempo de volver al original y corregirlo.

Las dos imágenes se pueden ampliar: rueda del mouse para acercarte donde tengas
el cursor, arrastrar para moverte, doble click para alternar entre 100% y
ajustada.

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
| Veta | `--veta` | `respetar` (sólo 0° y 180°) o `libre`. Arranca con la del material y se cambia para esta corrida sin tocar el catálogo. Con la veta respetada, Posiciones queda fija en 0° y 180°. |
| Recortes | — | Pedazos sueltos que ya tenés y querés usar antes de abrir una placa nueva. Se cargan con medida y cantidad, se llenan del más grande al más chico, y valen sólo mientras el programa está abierto: no van al catálogo. **Sólo en la interfaz; la CLI no los acepta.** |
| Separación | `--sep` | Milímetros mínimos entre dos piezas. |
| Borde | `--borde` | Margen contra el borde de la placa. |
| Copias | `--copias` | Cuántas veces repetir todo el contenido del archivo. |
| Esfuerzo | `--esfuerzo` | `rapido` (una pasada), `normal` (la pasada más una tanda de al menos 12 variantes -- tantas como núcleos si hay más de 12 -- probando las piezas repetidas grandes encastradas de a pares con distintos tipos de encastre, y si no hay, otros órdenes) o `lento` (tres tandas: más tipos de par y orientaciones perturbadas). |
| Núcleos | `--nucleos` | Cuántos núcleos usa para probar en paralelo las variantes de cada tanda. Arranca en todos menos dos, con un tope por memoria (cada proceso usa unos 2300 MB). Cada tanda prueba como mínimo 12 variantes: con menos de 12 núcleos corren las mismas 12 en varias vueltas y sólo cambia el tiempo; con 12 o más puede probar variantes de más, y ahí sí el resultado puede cambiar. |
| Posiciones | — | En cuántas posiciones puede girar cada pieza, repartidas en la vuelta entera: 4, 8 o 16. `Personalizado` revela el campo Ángulos para escribir la lista a mano. **Sólo en la interfaz.** Con la veta respetada queda fija en 0° y 180°. |
| Ángulos | `--angulos` | Rotaciones candidatas, separadas por coma. En la pantalla vive detrás de `Posiciones → Personalizado`. |
| Permitir espejadas | `--sin-espejo` | Si una pieza se puede dar vuelta como un guante. La pantalla lo trae activado; el flag lo apaga. |
| Tolerancia de cierre | `--tol-cierre` | Cuánto puede separarse un contorno para considerarlo cerrado. |
| Resolución | `--resolucion` | Milímetros por píxel del raster. Bajar de 2 a 1 cuadruplica el trabajo. Arranca en 1. |
| — | `--unidades` | Unidades del archivo, si el archivo no las declara. |
| — | `--preview` | Ruta del PNG de previsualización. |
| — | `--diagnostico` | Ruta del PNG que marca los descartes. Si es lo único que pedís, no acomoda nada y sale en un segundo. |

**Más esfuerzo no siempre da un resultado mejor, pero nunca da uno peor**:
con la misma cantidad de núcleos, lo que prueba Normal es el principio de lo
que prueba Lento, y se queda con la mejor de todas.

Cuando el resultado usa tantas placas como el mínimo que permite el área de
las piezas, lo dice: **No se puede con menos placas.** Si no lo dice, no
quiere decir que se pueda: el área es una cota, no una promesa. Con recortes
no se informa.

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
.venv/bin/pytest                     # la suite entera (1028, ~7 min)
.venv/bin/pytest tests/app           # sólo la interfaz (~10 s)
```

### Armar el ejecutable

```bash
./packaging/construir.sh          # macOS
```

Deja `dist/Nesting/` (~106 MB) y un `.zip` (~56 MB). Va en modo carpeta y no
archivo único a propósito: el modo de archivo único se autodescomprime en cada
arranque, y con scipy y rhino3dm adentro eso son varios segundos de espera cada
vez que alguien abre el programa.

El script **verifica el paquete antes de comprimirlo** (`--autotest`). No es
opcional: a un paquete al que le falta un recurso o un módulo oculto se lo ve
perfecto en la máquina donde se armó y falla en la del que lo recibe.

**Windows** va por `packaging/construir.ps1`, que hace lo mismo pero espera el
autotest de otra forma (ver el comentario del script). PyInstaller no compila
cruzado: el `.exe` sólo se puede armar en Windows. El workflow
[`.github/workflows/windows.yml`](.github/workflows/windows.yml) lo arma en un
runner de GitHub, corre la suite ahí y deja el `.zip` para bajar.

### Medir si un cambio fue una mejora

```bash
.venv/bin/python bench/run_bench.py
```

Placas, porcentaje de aprovechamiento y segundos sobre archivos reales. Ver
[`bench/README.es.md`](bench/README.es.md).

### Regenerar el ícono

```bash
.venv/bin/python herramientas/icono.py
```

Se dibuja con código, no se guarda sólo como binario. Deja el `.ico`, el
`.icns` y el favicon. Ver [`herramientas/README.es.md`](herramientas/README.es.md).

### Diagnosticar la ventana

```bash
.venv/bin/python herramientas/ventana_real.py
```

Hay defectos de esta interfaz que no se ven leyendo el código ni corriendo la
página en un navegador: viven en el hilo principal del sistema de ventanas. Esta
herramienta maneja la ventana de verdad desde afuera y los detecta. Ver
[`herramientas/README.es.md`](herramientas/README.es.md).

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
