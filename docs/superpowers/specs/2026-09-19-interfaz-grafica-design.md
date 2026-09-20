# Graphical interface for the nesting system

*[Español](2026-09-19-interfaz-grafica-design.es.md)*

Date: 2026-09-19
Status: approved

## 1. What is being built

A graphical interface on top of the engine that already exists, distributed as a
desktop program for Windows and Mac, and which on the day it is to be published
on the web gets deployed **without redoing the interface**.

The scope of this first version is **what the CLI already does, well
presented**. It adds no capabilities to the engine except the two the interface
needs in order not to lie (progress and cancellation).

### Out of scope, on purpose

- **Quantities per part.** Today `--copias` repeats the whole file. Being able
  to ask for 4 of one part and 2 of another is the feature most missed in real
  life, but it touches the engine as well as the interface and is left for
  later.
- **Laying out by hand.** Dragging a part and having the engine respect where it
  ended up. That is what eCut does and it demands live collision checking.
- **Installer (.msi / setup.exe).** Added later without touching the program.
- **Automated tests of the interface.** A manual checklist on this first pass;
  setting up Playwright now would be more infrastructure than product.
- **The web version itself.** This spec leaves it reachable, it does not build
  it.

## 2. The decisions, and why

### 2.1 The engine stays in Python. What gets shared is the interface.

`numpy`, `scipy`, `shapely` and `rhino3dm` are compiled libraries. Running the
engine in the browser is not viable. Therefore what travels between desktop and
web is not the engine: it is the interface, and only if it is made in
HTML/CSS/JS talking to an HTTP API.

A native interface (Qt, wxPython) would make a better desktop program and would
**close the web path completely**. It is discarded for that reason, not for any
other.

### 2.2 The API is job-based, not request-response.

Measured over `files/robot.ai`: `rapido` 34 s, `lento` 3 min 54 s, `lento` with
8 angles 9 min 5 s. That does not fit in an HTTP request.

On the desktop with a single user it could be solved with a thread and be done
with it. The "send the job, ask how it is going, take the result" shape is
chosen anyway because it is the one the web needs, and retrofitting it later
means rewriting. Today it costs nothing.

### 2.3 Native window with webview, not the system browser.

Starting the server and opening Chrome on `localhost` was considered: zero new
dependencies and identical on both platforms.

It is discarded because it loses **the native file dialogs**. In a browser you
can only upload content and download to Downloads; there is no "Save as". For a
cutting tool, where the DXF goes to a working folder alongside the rest of the
project, that difference is felt on every use. Besides, the address bar gives
away that it is not a program, and if the tab is closed the server stays running
invisibly.

Tauri was considered (much smaller executables, automatic updates) and is
discarded for now: it adds Rust and a whole build chain to a project that today
is pure Python, and the packaged Python has to be built anyway.

### 2.4 Visual direction: D · Modern.

Chosen among four directions mocked up and compared at the time.

It is the most approachable for somebody who does not come from CAD, and the
only one of the four that on the day it is published on the web will not look
like a desktop app shoved into a browser.

**Tokens:**

| | |
|---|---|
| Background | `#F4F6F8` |
| Panel | `#FFFFFF` |
| Drawing background | `#EDF0F4` |
| Text | `#111827` |
| Secondary text | `#606B7B` |
| Borders | `#E2E6EC`, 1 px |
| Accent | `#047857` |
| Text on accent | `#FFFFFF` |
| Radius | 10 px (buttons 8 px) |
| Control height | 44 px |
| Panel shadow | `0 1px 2px rgba(17,24,39,.06), 0 4px 12px rgba(17,24,39,.05)` |
| Typeface | Plus Jakarta Sans |
| Sheet / parts | fill `#FFFFFF` / `#E7EDF3`, stroke `#A9B4C2` / `#3F5468` |

The accent is `#047857` and not `#059669` because the second gives 3.4:1
against white and is not enough for small text.

**Tabular figures.** Every measurement on screen carries
`font-variant-numeric: tabular-nums`. The interface is a grid of measurements
compared against each other, and in proportional figures `1830` and `1220` do
not line up. Plus Jakarta Sans includes them, so there is no need to change
family.

### 2.5 Packaging: compressed folder, not single file.

PyInstaller in folder mode, distributed as a zip. Single-file mode unpacks
itself **on every start**, and with 300 MB that is several seconds every time
the program is opened.

The Windows `.exe` **cannot be compiled from Mac**: PyInstaller does not cross
platforms. GitHub Actions builds it.

## 3. Architecture

```
src/nesting/          today's engine. A single change: the progress callback.
src/nesting/cli.py    keeps working the same. It is not a path being abandoned.
src/nesting/params.py the parameters of a run, with their validation
src/nesting_app/      new
    api.py            the HTTP routes
    jobs.py           the job registry and the thread that runs them
    materials_store.py  the catalogue, editable, in the user's folder
    archivos.py       the platform door: desktop versus web
    rutas.py          where the data is, frozen or not
    desktop.py        starts the server and opens the window
    web/              index.html, app.js, app.css
```

**`nesting_app` knows `nesting`, never the other way round.** The engine does
not know an interface exists, just as today it does not know a CLI exists.

New libraries: `fastapi`, `uvicorn`, `pywebview`.

## 4. The API

```
POST   /api/archivos            uploads a file (web) → {fuente_id}
POST   /api/archivos/local      registers a local path (desktop) → {fuente_id}
POST   /api/analizar            {fuente_id} → parts, discards, units
POST   /api/trabajos            {fuente_id, parameters} → {id}
GET    /api/trabajos/{id}       status, progress, warnings, result
POST   /api/trabajos/{id}/cancelar
GET    /api/trabajos/{id}/salida.dxf
GET    /api/trabajos/{id}/preview.png
GET    /api/trabajos/{id}/diagnostico.png
GET    /api/materiales          plus POST, PUT, DELETE
POST   /api/materiales/restaurar
```

### 4.1 States of a job

`pendiente` → `corriendo` → `listo` | `cancelado` | `error`
(pending → running → done | cancelled | error)

### 4.2 Progress is measured in parts, within an attempt

How many sheets will be needed **is not known in advance**: the engine discovers
them as it works. "Sheet 2 of 3" would be made up.

How many parts there are *is* known from the start. But `pack()` runs several
complete passes and keeps the best —1 in `rapido`, 3 in `normal`, 12 in `lento`,
according to `EFFORT_RESTARTS`— and **each pass restarts the count**. A
percentage that goes backwards is worse than having none.

Honest progress carries both things, and the number of attempts is known from
the start because it comes from `EFFORT_RESTARTS[esfuerzo]`:

> *intento 2 de 3 · ubicadas 61 de 93 · placa 1*
> (attempt 2 of 3 · 61 of 93 placed · sheet 1)

The bar fills with `parts_placed / total_parts` and visibly restarts on each
attempt, which is what is really happening.

After the attempts there is one more step, `_compact_last_sheet`, reported as
*"compactando la última placa"* (compacting the last sheet) with no bar: it is a
single short pass and faking a percentage there would be making things up again.

### 4.3 Cancelling is cooperative

A flag is raised and the engine exits cleanly at the next cut point, which is
the same progress callback. The thread is not killed.

### 4.4 The platform door

| | Desktop | Web |
|---|---|---|
| Open | native dialog, returns a path | `<input type=file>`, uploads |
| Save | native "Save as" | download |

Both paths end up in a `fuente_id` that the rest of the system uses without
asking where it came from. **It is the only place in the code that knows where
it is running.**

### 4.5 One job at a time

On the desktop a single worker thread runs. A job sent while another is running
stays `pendiente`; the interface also disables "Acomodar" while one is in
progress, so in practice the queue is not used — but the API respects it anyway,
because on the web it will be.

For the web the single thread is swapped for a queue with several processes
**without touching the API**, which is the point of having designed it this way.

### 4.6 Temporary files

Every `fuente_id` and every job has its folder under the system's temporary
directory. They are deleted when the program closes, and on startup whatever was
left over from a previous run that ended badly is cleaned up.

An output DXF lives there until the user presses "Guardar DXF", which copies it
to the destination they chose. **Closing the program without saving loses the
result**, and the interface warns before closing if there is an unsaved one.

## 5. The screens

A 1100 × 720 window, resizable, minimum 960 × 640.

### 5.1 Main

A single window, **not a step-by-step wizard**: the real work is iterative —run,
look, change the spacing, run again— and a wizard forces you through the whole
thing to touch one number.

```
┌─────────────────────────────┬──────────────────────────────────┐
│  Archivo                    │                                  │
│  robot.ai   Cambiar  │                                  │
│  93 piezas · 3 descartes ›  │        el dibujo, grande         │
│                             │                                  │
│  Material        [mdf18  ▾] │  ( Previsualización | Revisión ) │
│  Separación      [3     ]mm │                                  │
│  Borde           [10    ]mm │                                  │
│  Copias          [1     ]   │                                  │
│  Esfuerzo        [Normal ▾] │                                  │
│                             │                                  │
│  › Opciones avanzadas       │                                  │
├─────────────────────────────┴──────────────────────────────────┤
│  [ Acomodar ]   1 placa · 47,7% · sobrante 1830×708  [Guardar] │
└────────────────────────────────────────────────────────────────┘
```

At the top, the five options you actually touch. Folded into "Opciones
avanzadas" (advanced options), the seven you do not: angles, mirroring, units,
closing tolerance, resolution, alternative material catalogue.

**The file is analysed as soon as it is chosen.** Before you touch a parameter
it already says "93 piezas · 3 descartes" (93 parts · 3 discards), and that
"3 descartes" is a link that switches the right panel to the review image.
`/api/analizar` runs in ~1 s.

**The right panel has two tabs**, Previsualización and Revisión (preview and
review). At first only Revisión is there, because nothing has been laid out yet.

**During the run**, the bottom bar shows the progress and a cancel button
instead of the result.

**"Guardar DXF" is explicit.** The file is built in a working folder and goes
nowhere until save is pressed. Nothing appears on its own in Downloads or next
to the input file.

### 5.2 Materials

You get there from the material dropdown ("Administrar materiales…") and from
the top bar. A table with name, width, height and grain; add, edit, delete; and
a form panel to the side.

The grain is **not shown as a number between 0 and 180**, because nobody knows
what 5 means:

- **La veta no importa** (grain does not matter) — the part rotates freely
  *(MDF)* → `tolerancia_veta: 180`
- **Respetar la veta** (respect the grain) — 0 and 180 degrees only *(plywood,
  phenolic)* → `5`

They are saved in the user's data folder:

- Windows: `%APPDATA%\nesting\materials.yaml`
- macOS: `~/Library/Application Support/nesting/materials.yaml`

The first time, the catalogue that ships with the program is copied there. A
button remains for restoring that original.

### 5.3 Units stop being an error

Today, a file that does not declare units aborts the run with
`UnknownUnitsError` and a message telling you to use `--unidades`. In an
interface that cannot be an error: it is a question. A panel appears with the
five buttons (mm, cm, m, in, ft) and things carry on.

## 6. Packaging and distribution

- **PyInstaller in folder mode**, distributed in a zip.
- **GitHub Actions** with `windows-latest` and `macos-latest`, triggered by tag.
- **The port is requested free from the system** (`port 0`), never a fixed one.
- **The server listens only on `127.0.0.1`** and demands a token that the window
  already carries in the URL. Without that, any page open in the user's browser
  could send jobs to the program.
- **WebView2 is checked at startup.** If it is missing, a panel with the
  download link. Without that the window opens blank and there is no way to
  guess what happened. Windows 11 always ships it; Windows 10 almost always.
- An unsigned `.exe` triggers the SmartScreen warning. Accepted in this version;
  signing it costs money and paperwork.
- Measured size (macOS arm64, PyInstaller 6.22.3): 106 MB on disk
  (`dist/Nesting/`), 56 MB compressed (`dist/Nesting-darwin-arm64.zip`). Quite a
  bit less than the original estimate of 250-400 MB / 100-150 MB, which assumed
  a universal2 binary (x86_64 + arm64); this one is pure arm64. The size on
  Windows, which carries its own runtime and DLLs, is still to be measured.

## 7. Errors

| Situation | In the window |
|---|---|
| Units not declared | the question with the five buttons (5.3) |
| Open outline | a panel with the gap in mm and where it is, and the closing tolerance field one click away |
| Part larger than the sheet | names the part, its measurement and that of the usable area |
| Verification failed (exit code 2) | in red, with **no file was written** and the list of problems |
| Invalid parameter | below the field that has it wrong |
| Corrupt material catalogue | the error is named and restoring the original is offered |

**`ChainingInvariantError` is not a user error, it is a bug in the program.**
Today it blows up on purpose, uncaught, because it means the chainer lost
geometry. In the window it cannot be disguised as "check your drawing": it says
the problem is the program's and gives a copyable detail. The same goes for any
unexpected exception, which additionally goes to `<data folder>/log.txt`.

## 8. Changes to the code that already exists

1. **`pack()` takes an optional progress callback**, called when each part is
   placed with `(parts_placed, total_parts, current_sheet)` and whose return
   value asks it to give up. It is the only change to the engine. The CLI does
   not use it and its behaviour does not change.
2. **`_validate_numeric_args` moves out of `cli.py` into `params.py`**, so that
   the CLI and the API validate with the same code and not with two copies that
   drift apart.
3. **`DEFAULT_MATERIALS_PATH` stops being computed as
   `Path(__file__).parents[3]`**, which does not work inside a frozen
   executable. It goes through `rutas.py`, which distinguishes frozen from not
   frozen.

None of the three changes the observable behaviour of the CLI.

## 9. Tests

**The engine's 495 tests are not touched.** That is the proof that the cut
between engine and interface is in the right place: if an engine test had to
change in order to add an interface, the cut would be wrong.

Added:

- **The API**, with FastAPI's test client: the full cycle of a job, cancelling
  mid-run, invalid parameters rejected at the boundary, `/api/analizar`, and a
  non-existent `fuente_id` not blowing up.
- **The material catalogue**: saving and re-reading, a corrupt file, restoring
  the original, and path resolution frozen and not frozen.
- **The parameters**, moved out of `cli.py` and now shared.
- **A test over the frozen executable.** The program accepts `--autotest`: it
  starts the server, requests `/api/materiales`, and exits with zero. GitHub
  Actions runs it after building.

That last one catches the class of error that hurts most: paths that do not
resolve, a module PyInstaller did not find, a `materials.yaml` that is not where
the code looks for it. **Those bugs never show up in the normal tests**, they
show up when the user opens the program. We already know
`DEFAULT_MATERIALS_PATH` is one of them.

## 10. What this spec leaves ready for the web

The day it is to be published, the work left is: deploy the server, add users
and isolation, swap the single thread for a process queue, and absorb the CPU
cost (each job occupies a core for minutes).

**None of that touches the interface.**
