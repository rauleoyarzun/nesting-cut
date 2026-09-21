# Sheet offcuts, and four interface adjustments

*[Español](2026-09-21-recortes-y-ajustes-design.es.md)*

Date: 2026-09-21
Status: approved

## 1. What is being built

Five things: one large, four small.

**The large one: offcuts.** Being able to say "I have two leftover pieces of
600x800" and have the layout use them before opening a new sheet. An offcut is
not a material: it is not saved to the catalogue, it has no name, and it lives
only while the program is open. It is what was left over from an earlier job
and is leaning against the wall.

**The four small ones**, all interface:

- Resolution now starts at 1 mm/px instead of 2.
- Angles are chosen by number of positions (4, 8 or 16) instead of typed one
  by one.
- The `Revisión` tab moves to the left, and `Previsualización` is renamed
  `Resultado`.
- The mouse wheel stops jumping through a fixed ladder: zoom becomes
  continuous and proportional to the gesture.

### Out of scope, on purpose

- **Saving offcuts.** They are lost when the program closes, and that is
  correct: an offcut still listed three weeks later has already been cut,
  lost or misplaced, and a catalogue that lies about the stock on hand is
  worse than no catalogue.
- **A scrap inventory.** This work does not deduct, does not keep a balance
  and does not record what was left after cutting. It only accepts a list for
  the run about to happen.
- **Choosing by hand which sheet each part goes on.** The engine still
  decides.
- **Offcuts from the CLI.** They are entered while looking at the pieces
  leaning against the wall, and that happens in front of the screen. The CLI
  stays as it is.
- **Irregularly shaped offcuts.** An offcut is a rectangle. An L-shaped piece
  is entered as the largest rectangle that fits inside it.

## 2. The decisions, and why

### 2.1 An offcut is not a material

The catalogue describes what gets bought: a sheet size that repeats
identically every time it is ordered. An offcut is the opposite -- one unit,
one size, and once it is cut it stops existing. Putting both in the same place
would force a "quantity" field onto the catalogue that means nothing for a
real material, and would leave dead entries to clean up by hand.

So offcuts are a parameter of the run, next to `copias` and `separación`, not
a catalogue entry.

### 2.2 When the offcuts run out, it continues with Material sheets

The chosen Material still matters: it defines the grain, and its sheet is what
gets opened when the offcuts are not enough. The sheet plan is therefore
"these offcuts first, then new sheets until everything fits".

The alternative -- restrict to the offcuts and fail if something does not fit
-- was rejected. The real case is "use what is left over and take the rest
from a new sheet", not "tell me whether I have enough".

### 2.3 The objective is fewer **new** sheets, not fewer sheets

This is the decision that changes engine behaviour the most, and the one with
the easiest trap to step in.

`CostoLayout` today orders by sheet count before anything else. If an offcut
counted as a sheet, the engine would prefer to skip a 600x800 offcut and put
everything on one new sheet -- one sheet against two -- which is exactly the
opposite of what is being asked for. An offcut is material already paid for:
filling it costs nothing.

So the first field of the cost now counts **only Material sheets**. With no
offcuts, that number is identical to today's, so no existing run changes its
result.

### 2.4 Offcuts are consumed largest first

The engine sorts them by area, largest first, regardless of the order they
were entered in. If the small offcut came first, a medium part that only fits
in the large one could be stranded because the large one filled up with parts
that also fitted in the small one.

There is no on-screen control for this order. It would be one more control for
a decision the engine makes better.

An offcut larger than the Material sheet is accepted without complaint: it is
unusual but not an error, and rejecting it would mean explaining a rule that
protects against nothing.

### 2.5 An offcut that received nothing does not exist

Today, a sheet ending up empty is fatal: it means some part fits nowhere. With
offcuts that stops being true -- a 200x300 offcut may not accept even the
smallest part, and that is normal.

An empty offcut is skipped and disappears from the result: it does not show up
as "Placa 3 -- 0%" in the preview, it does not occupy an empty rectangle in
the DXF, and it does not enter the utilisation average. An empty **Material**
sheet is still the same hard error as always, and it is the one that produces
the "this part does not fit on an empty sheet" message.

The loop still terminates: offcuts are finite, so skipping them leads sooner
or later to a Material sheet, where either something is placed or the error is
raised.

### 2.6 Cross grain is per offcut

A 600x800 piece of plywood may have its grain along the 600 or along the 800,
depending on how it came off the parent sheet. That information is held only
by whoever is looking at the piece.

Each offcut therefore carries a `veta cruzada` checkbox. When ticked, that
sheet's grain axis runs across rather than up, and the permitted orientations
are computed against that axis. Orientations stop being computed once per run
and become computed **per sheet**.

On a free-grain material (MDF) the checkbox would change nothing, so it is
disabled when the chosen Material has free grain. A checkbox that can be
ticked and does nothing teaches that the interface lies.

### 2.7 `discard_plate_outline` still looks only at the Material sheet

That function drops rectangles someone drew at the exact sheet size to preview
in their CAD. Extending it to offcut sizes looks consistent and is a trap: a
real 600x800 part would silently vanish the day a 600x800 offcut is entered.
At 1830x2600 the collision is improbable; at offcut sizes, which are part
sizes, it is likely.

It stays as it is, and the spec says so, so it does not get "fixed" later.

### 2.8 Recovery now compares costs instead of reasoning about them

`_recuperar_de_la_ultima_placa` accepts its result without comparing it,
resting on an argument written in its docstring: if the last sheet empties,
the sheet count drops, and that is the first field of the cost, so the layout
can never get worse.

With `placas_nuevas` that argument stops holding. If the last sheet is an
**offcut** and it empties, `placas_nuevas` does not drop -- it never counted
that offcut -- and the "last sheet" becomes a different one, possibly with
more material on it: `material_ultima` rises and a worse layout is accepted.

The fix is an explicit guard at the end of the function: return the recovered
layout only if its `CostoLayout` is no worse than the incoming one. It is a
cheap comparison, and it trades a reasoned guarantee for a verified one.

### 2.9 Wheel zoom becomes continuous; the buttons do not

Zoom jumps through nine fixed steps and **each wheel event advances a whole
step**. A trackpad gesture sends dozens of events, so one flick goes from 25%
to 600% with nothing in between.

The wheel now multiplies zoom by a factor exponential in `deltaY`, clamped
between 0.1 and 6: a nudge moves a little, a long gesture moves a lot, and the
gesture is reversible. The `+` and `-` buttons and the double click keep the
existing ladder, which is where round numbers are useful.

`deltaY` is normalised by `deltaMode`: Firefox reports lines rather than
pixels, and without normalising, the same gesture would jump differently in
each browser.

### 2.10 Resolution 1 mm/px by default, with its cost written down

Explicitly requested. It quadruples the raster's pixels, so runs will take
considerably longer and use more memory.

The timings documented in `packer.py` -- 48 s on the reference file, 450 s on
`banqueta final raulo.ai` at 5 copies -- were measured at 2.0 mm/px. That note
is updated to say which resolution it was measured at and that the default is
no longer that value. The sweep is not re-run: measuring it again is separate
work, and leaving the note silently lying is worse than leaving it saying what
it does not cover.

## 3. Architecture

### 3.1 `Sheet` and `SheetSupply`

New file, `src/nesting/model/sheet.py`:

```python
@dataclass(frozen=True)
class Sheet:
    width: float
    height: float
    grain_tolerance: float
    cross_grain: bool = False
    scrap: bool = False

    @property
    def area(self) -> float: ...


@dataclass(frozen=True)
class SheetSupply:
    """Which sheet is which, in order. Offcuts run out; the Material's does
    not."""
    stock: Sheet
    scraps: tuple[Sheet, ...] = ()

    def sheet(self, index: int) -> Sheet:
        return self.scraps[index] if index < len(self.scraps) else self.stock
```

`allowed_angles` moves from `material.py` to `sheet.py` and now takes a
`Sheet`. With `cross_grain=True` the distance is measured against the axis at
90 degrees: `_distance_to_grain_axis(angle - 90.0)`, which the inner `% 180`
already normalises.

`Material` does not change -- it is still the catalogue entry -- and gains
`stock_sheet()`, returning its `Sheet` with `scrap=False` and
`cross_grain=False`.

### 3.2 The packer

`_pack_once` and `pack` take a `SheetSupply` where they take a `Material`
today.

The sheet loop carries two counters, and that is the subtle part: the index
into the plan and the index into the result **stop coinciding** as soon as an
offcut is skipped.

```
siguiente = 0             # next sheet in the plan
usadas: list[Sheet] = []  # the ones that actually received something

while remaining:
    hoja = supply.sheet(siguiente); siguiente += 1
    oracle.reset(hoja.width, hoja.height, config)
    choices = orientations(hoja, config)      # per sheet, not per run

    # placements are built against len(usadas), the index this sheet WILL
    # have if it ends up receiving anything
    ...

    if placed_count == 0:
        if hoja.scrap:
            continue                          # this offcut is no use, skip it
        _raise_too_large(still_pending[0], hoja, config, choices)

    result.placements.extend(las_de_esta_placa)
    usadas.append(hoja)
```

`PackResult` gains `sheets: list[Sheet]`. That is the change that stops
everything downstream from having to guess each sheet's size, and
`sheets_used` becomes `len(sheets)`. `utilization[i]` is computed against
`sheets[i].area`, not against one shared area.

`orientations(sheet, config)` replaces `orientations(material, config)`.

`_raise_too_large` now takes the `Sheet` plus, separately, the material's
name: a `Sheet` has no name, and the message the user reads -- "el área útil
de la placa mdf18 es ..." -- needs it. It is always raised against the
Material sheet, never against an offcut, so the name always matches.

### 3.3 Layout cost

```python
@dataclass(frozen=True, order=True)
class CostoLayout:
    placas_nuevas: int      # how many Material sheets were opened
    material_ultima: float  # part area on the last sheet used, in mm²
    alto_ultima: float      # how high the material reaches there, in mm
```

`placas_nuevas = sum(1 for s in result.sheets if not s.scrap)`. The "last
sheet" is still literally the last one in the result.

With no offcuts, `placas_nuevas == sheets_used` and the other two fields keep
their definitions: the cost is identical to today's, field by field.

`_compact_last_sheet` re-packs the last sheet against
`SheetSupply(stock=esa_hoja)`. It still compares only `.alto_ultima`, the one
thing that pass can improve.

`_recuperar_de_la_ultima_placa` re-packs each earlier sheet against
`SheetSupply(stock=result.sheets[placa])`, uses that sheet's area for
utilisation, and ends with the guard from section 2.8.

`corredor.py`'s `Resultado` gains `recortes_usados: int` -- how many of
`resultado.sheets` were offcuts. Without that field the screen cannot write
"2 recortes + 1 nueva" without recounting something the engine already
knows.

### 3.4 `verify`, DXF and preview

`verify()` is the engine's hardest rule: if it fails, nothing is written. It
now takes `sheets: Sequence[Sheet]` and checks each placement against **its
own** sheet, not against a global size. This is the most important of the
three: a part that runs off a 600x800 offcut must report a violation even
though it would sit comfortably on an 1830x2600 sheet.

`write_dxf` and `write_preview` today place sheet `i` at
`i * (sheet_w + gap)`. They now accumulate the offset: `sum(previous widths) +
(i + 1) * gap`. The preview additionally sizes the canvas height from the
tallest sheet, and draws each rectangle at its own size.

### 3.5 Parameters, API and CLI

In `nesting/params.py`:

```python
@dataclass(frozen=True)
class Recorte:
    ancho: float
    alto: float
    cantidad: int = 1
    veta_cruzada: bool = False

NestParams.recortes: tuple[Recorte, ...] = ()
NestParams.resolucion: float = 1.0      # was 2.0
```

`validar()` gains three rules in the shape it already uses (`ReglaRota` with
`campo`, `regla`, `valor`): `ancho > 0`, `alto > 0`, `cantidad >= 1`. The
field is named with its position -- `recorte 2: ancho` -- so the error says
which one in the list.

A new function in the same file builds the plan:

```python
def a_supply(p: NestParams, material: Material) -> SheetSupply
```

It expands each offcut into `cantidad` copies, gives them the material's
`grain_tolerance` and their own `cross_grain`, marks `scrap=True`, sorts by
area largest first, and puts them ahead of `material.stock_sheet()`.

In `nesting_app/api.py`, `ParamsEntrada` gains `recortes: list[RecorteEntrada]`
(empty by default) and its `resolucion` default becomes 1.0. Pydantic still
checks only types; the ranges come from `validar()`, the same code the CLI
runs.

The CLI does **not** gain a flag for offcuts. They are a workshop convenience
entered while looking at the pieces leaning against the wall, and that happens
in front of the screen, not in a terminal. `NestParams.recortes` stays empty
when the run comes from the CLI, and `a_supply()` then returns a plan of one
infinite sheet -- exactly today's behaviour.

The CLI still changes: it builds the `SheetSupply` to call `pack()`, passes
`result.sheets` to `verify`, `write_dxf` and `write_preview`, and its
`--resolucion` default becomes 1.0.

### 3.6 The screen

**`index.html`:**

- Below the Material selector, a `Recortes` block with its info button and an
  `Agregar` link. The link opens an inline row with four controls: width,
  height, quantity, and the `veta cruzada` checkbox. Below it, the list of
  entered offcuts, each with its size and a `✕`.
- In Advanced options, before the angles field, a `Posiciones` dropdown:
  `4 — 0, 90, 180, 270`, `8 — cada 45°`, `16 — cada 22,5°`, `Personalizado`.
  It starts at 4. The angles text field stays, hidden, and appears only with
  `Personalizado`.
- `value="1"` on the resolution field.
- The two tabs swap in the DOM: `Revisión` first, then the one that now reads
  `Resultado`. The ids (`tab-revision`, `tab-preview`) and the server's file
  name (`preview.png`) are **left alone**: renaming them is churn across five
  files for nothing.

**`app.js`:**

- `estado.recortes`, a list of `{ancho, alto, cantidad, veta_cruzada}`. It is
  session state: it survives changing files (`registrar()` does not touch it)
  and is lost on close. `parametros()` sends it as `recortes`.
- A small function renders the list from `estado.recortes`; adding and
  removing mutate it and re-render. No framework, like the rest of the file.
- On a Material change, its grain is consulted and the `veta cruzada`
  checkbox is disabled when the grain is free. The data already arrives in
  `/api/materiales`.
- `angulosDelCampo()` becomes `angulosElegidos()`: when `Posiciones` is a
  number it returns `[i * 360/n for i in range(n)]`; when it is
  `Personalizado` it parses the text as today, with the same validation and
  the same error under the field.
- The `wheel` handler stops calling `acercar()` and becomes
  `zoom = clamp(previous * Math.exp(-normalised * SENSIBILIDAD), 0.1, 6)`,
  keeping the same scroll adjustment that holds the point under the cursor.
  `acercar()` remains for the buttons.
  `normalised` is `deltaY` brought to pixels: times 16 when `deltaMode` is 1
  (lines, Firefox), times 100 when it is 2 (pages), as-is when 0.
  `SENSIBILIDAD = 0.0015` is the starting point -- with it a typical wheel
  notch (100 px) moves zoom by 16%, and a full trackpad gesture crosses the
  range without overshooting. It is a feel number: tuned by trying it, and
  the test only checks that the wheel does not use `PASOS_ZOOM`.
- `terminar()` writes the split: `3 placas (2 recortes + 1 nueva)`, or
  `2 placas` when there were no offcuts.

**`info.js`:** a new bubble for `Recortes` and one for `Posiciones`. The
Resolution one is reworded: it currently names 2 mm/px as the default.

## 4. What it looks like

```
Material                        Agregar o editar
[ mdf18                              v ]

Recortes                                Agregar
  600 x 800 mm  x2                            ✕
  450 x 1200 mm  x1  · veta cruzada           ✕
```

With the entry row open:

```
Recortes
  [ ancho ] x [ alto ] mm   x [ 2 ]
  [ ] veta cruzada          Agregar   Cancelar
```

On completion, in the bottom bar:

```
3 placas (2 recortes + 1 nueva) · 78,4% aprovechado · sobrante 412 mm ...
```

## 5. Tests

**Engine** (`tests/engine/`, `tests/model/`):

- An offcut that fits is filled before the Material sheet.
- An offcut where no part fits is skipped and does **not** appear in
  `result.sheets` or in `utilization`.
- A part that fits on no sheet still raises `PartTooLargeError`, and the
  message names the Material sheet, not the last offcut.
- With no offcuts, `layout_cost` gives exactly what it gave before the change
  (field by field) on a fixed scenario.
- `placas_nuevas` does not count offcuts: a layout of three offcuts and zero
  new sheets costs less than one with a single new sheet.
- `cross_grain` rotates the axis: on a 5-degree grain material, a crossed
  offcut permits 90/270 and forbids 0/180.
- The guard from 2.8: a constructed case where emptying the last offcut raises
  `material_ultima`, and recovery **returns the incoming layout**.
- `SheetSupply.sheet(i)` returns offcuts until they run out and the Material's
  sheet forever after.

**Geometry and IO:**

- `verify()` reports a violation when a part runs off **its own** offcut even
  though it would fit on the Material sheet. This is the test that matters:
  without it, a bad DXF reaches the router.
- `write_dxf` and `write_preview` with sheets of different widths: the
  rectangles do not overlap and each has its own size.
- `discard_plate_outline` does **not** discard a part the size of an offcut.

**Parameters and API** (`tests/test_params.py`, `tests/app/`):

- `validar()` rejects width 0, negative height and quantity 0, naming which
  one in the list.
- `a_supply()` expands the quantity, sorts by area and inherits the material's
  grain.
- The `resolucion` default is 1.0 in `NestParams` and in `ParamsEntrada`.
- A CLI run with no offcuts produces the same layout as before the change on
  a fixed scenario: this is the proof that `a_supply()` with an empty list
  changes nothing.

**Interface** (`tests/app/test_web_javascript.py`, in its style of asserting
on the file's text):

- `Revisión` appears before `Resultado` in the HTML, and the word
  `Previsualización` is gone.
- The resolution field has `value="1"`.
- The positions dropdown exists with 4, 8 and 16, and `Personalizado` reveals
  the text field.
- The wheel handler does not use `PASOS_ZOOM`, and does normalise
  `deltaMode`.
- `registrar()` does not clear `estado.recortes`.
- `parametros()` sends `recortes`.
- Each new `info.js` bubble has its button in the HTML and vice versa (the
  existing equal-sets test covers this on its own).

## 6. Changes to code that already exists

| File | What happens to it |
|---|---|
| `src/nesting/model/sheet.py` | New. `Sheet`, `SheetSupply`, `allowed_angles`. |
| `src/nesting/model/material.py` | Loses `allowed_angles`, gains `stock_sheet()`. |
| `src/nesting/engine/packer.py` | `SheetSupply` instead of `Material`; loop with two counters; `PackResult.sheets`; `CostoLayout.placas_nuevas`; guard in recovery; timing note updated. |
| `src/nesting/geometry/verify.py` | Takes `sheets` and checks each placement against its own. |
| `src/nesting/io/dxf_writer.py` | Accumulated offsets, per-sheet size. |
| `src/nesting/io/preview.py` | Accumulated offsets, canvas height from the tallest sheet. |
| `src/nesting/params.py` | `Recorte`, `NestParams.recortes`, `a_supply()`, three new rules, `resolucion = 1.0`. |
| `src/nesting/cli.py` | `--resolucion` default, builds the `SheetSupply` (no offcuts) and passes `sheets` to verify/DXF/preview. No new flag. |
| `src/nesting_app/api.py` | `RecorteEntrada`, `ParamsEntrada.recortes`, resolution default. |
| `src/nesting_app/corredor.py` | Builds the `SheetSupply`, passes `sheets` to `verify`/`write_dxf`/`write_preview`, `sobrante_mm` against the last sheet, offcut/new split in `Resultado`. |
| `src/nesting_app/web/index.html` | Offcuts block, positions dropdown, `value="1"`, tabs swapped. |
| `src/nesting_app/web/app.js` | `estado.recortes`, the list, `angulosElegidos()`, continuous wheel, split in `terminar()`. |
| `src/nesting_app/web/app.css` | Rules for the offcut list and the entry row. |
| `src/nesting_app/web/info.js` | Two new bubbles, one reworded. |
| `README.md` / `README.es.md` | Offcuts row in the options table (marked interface-only), new resolution default. |
| `packaging/` | Nothing: the `.spec` declares the whole `web` folder. |
