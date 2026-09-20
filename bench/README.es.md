# Banco de pruebas

*[English](README.md)*

Mide tres números sobre archivos reales: **cantidad de placas**, **% de aprovechamiento**
y **segundos**. Son los que deciden si un cambio en el motor fue una mejora.

## Uso

```bash
.venv/bin/python bench/make_sample.py  # genera bench/files/muestra.dxf
.venv/bin/python bench/run_bench.py    # corre sobre todo bench/files/*.dxf
```

Usá siempre `.venv/bin/python`: el `python`/`python3` del sistema no tiene
`ezdxf` instalado.

El banco hoy solo lee archivos `.dxf` (`bench/files/*.dxf`); cualquier otro
formato en esa carpeta se ignora.

Si un archivo de la carpeta falla (unidades sin declarar, contornos abiertos,
piezas que no entran en la placa, DXF corrupto), la corrida no se aborta: esa
fila se informa como `ERROR` con el motivo, y sigue midiendo el resto. El
código de salida distingue esa situación (no cero) para que un script que
llame al banco se entere de que faltó medir algo.

## Cargar los archivos reales del proyecto

Los archivos de la banqueta están en `.cdr`, `.ai` y `.3dm`. El `.cdr` **no se lee
directamente** (formato binario cerrado, spec §2): hay que exportarlo.

**Desde CorelDRAW:** Archivo → Exportar → elegir `AutoCAD (DXF)` → guardar en
`bench/files/`. Verificar que en el diálogo de exportación las unidades queden en
**milímetros**; si Corel exporta sin declarar unidades, corré el banco con
`--unidades mm` (mismas opciones que la CLI principal: `mm`, `cm`, `m`, `in`, `ft`).

**Desde Rhino:** Archivo → Exportar selección → `DXF`.

Los `.ai` y `.3dm` ya están copiados en `bench/files/` y, desde la Tarea 24,
`run_one` los lee directo (por extensión, igual que la CLI): `.ai` con
`read_ai`, `.3dm` con `read_3dm`, y cualquier otra extensión con `read_dxf`.
El `main()` de `run_bench.py` (el reporte por consola) sigue barriendo solo
`bench/files/*.dxf`; `bench/calibrate.py` es el que además suma `*.ai` a la
corrida. El `banqueta.3dm` da 0 piezas (es el modelo 3D del ensamblaje
armado, no un layout de corte plano -- ver el Task 23 report), así que no
sirve para calibrar ni para medir aprovechamiento.
