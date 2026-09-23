# Benchmark

*[Español](README.es.md)*

Measures three numbers over real files: **number of sheets**, **% utilisation**
and **seconds**. They are the ones that decide whether a change in the engine
was an improvement.

## Usage

```bash
.venv/bin/python bench/make_sample.py  # generates bench/files/muestra.dxf
.venv/bin/python bench/run_bench.py    # runs over every bench/files/*.dxf
```

Always use `.venv/bin/python`: the system `python`/`python3` does not have
`ezdxf` installed.

Today the benchmark only reads `.dxf` files (`bench/files/*.dxf`); any other
format in that folder is ignored.

If a file in the folder fails (units not declared, open outlines, parts that do
not fit on the sheet, corrupt DXF), the run is not aborted: that row is reported
as `ERROR` with the reason, and it keeps measuring the rest. The exit code
distinguishes that situation (non-zero) so that a script calling the benchmark
finds out that something went unmeasured.

## Loading the project's real files

The bench files are in `.cdr`, `.ai` and `.3dm`. The `.cdr` **is not read
directly** (closed binary format, spec §2): it has to be exported.

**From CorelDRAW:** File → Export → choose `AutoCAD (DXF)` → save into
`bench/files/`. Check that the units in the export dialog are set to
**millimetres**; if Corel exports without declaring units, run the benchmark
with `--unidades mm` (same options as the main CLI: `mm`, `cm`, `m`, `in`,
`ft`).

**From Rhino:** File → Export selected → `DXF`.

The `.ai` and `.3dm` files are already copied into `bench/files/` and, since
Task 24, `run_one` reads them directly (by extension, just like the CLI): `.ai`
with `read_ai`, `.3dm` with `read_3dm`, and any other extension with
`read_dxf`. The `main()` of `run_bench.py` (the console report) still sweeps
only `bench/files/*.dxf`; `bench/calibrate.py` is the one that also adds `*.ai`
to the run. The `banqueta.3dm` yields 0 parts (it is the 3D model of the
assembled bench, not a flat cutting layout -- see the Task 23 report), so it is
no good for calibrating or for measuring utilisation.

## Fixed cases

Besides sweeping `*.dxf`, `run_bench.py` measures the jobs in `CASOS_FIJOS`,
each one with its own sheet and configuration, and flags a result that is not
the expected one. Today there is one: `banqueta-alta.ai` (57 parts, free
1220 × 2440 sheet, sep 8, border 5, 8 positions, normal, 1 mm/px, with as many
cores as the machine it runs on allows -- the result does not depend on how
many, only the time, as long as they stay under twelve), which has to give
**1 sheet**. If the file is not in `bench/files/` (it is not versioned), the
row says it is skipped.

The same bench is a slow test of the suite, which a plain `pytest` does not
run:

    .venv/bin/pytest -m lento
