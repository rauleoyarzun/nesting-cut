# Nesting system for optimising cuts on sheet material

*[Español](2026-09-17-nesting-placas-design.es.md)*

**Date:** 2026-09-17
**Status:** Design approved, implementation plan pending

---

## 1. Problem

Laying out the parts of a piece of furniture by hand (in CorelDRAW) onto wood sheets is slow and
wastes material. Tools that solve it exist (eCut, SigmaNest, AutoCAD's nesting), but they are
closed and/or paid.

**Goal:** given a vector file with the shapes to cut, produce an output file with those shapes
laid out inside one or more sheets, using as little sheet as possible, respecting a configurable
minimum spacing between shapes and against the edge of the sheet.

### Reference scale

Real files from the project (a bench): 40-80 outlines per file, standard sheet 1830 × 2600 mm,
organic parts with curves that interlock.

---

## 2. Scope

### In scope

- Reading `.dxf` (canonical), `.ai` and `.3dm`
- Writing `.dxf` with the parts laid out + `.png` preview
- Nesting of irregular shapes with rotation and mirroring
- Use of through holes as free area
- Configurable spacing between parts and against the sheet edge
- Multiple sheets with automatic overflow
- Material catalogue (sheet size + grain constraint)
- Command line interface
- Exact geometric verification of the result

### Out of scope (v1)

| Topic | Reason |
|---|---|
| Reading `.cdr` directly | Closed proprietary binary format. Solved by exporting to DXF from Corel |
| Colour → machine operation mapping | Every cut is treated the same. Colour is carried along as a passive attribute |
| Bridges / tabs | Parts come loose when cut. Known limitation |
| Cutting path optimisation | That is the CAM's job, not the nesting's |
| Non-standard sheets / offcuts | Natural later extension. Not v1 |
| Splitting parts larger than the sheet | Reported as an error |
| Graphical interface | It can be mounted later on top of the same engine |

---

## 3. Design decisions

### 3.1 DXF as the canonical format

**Decision:** the engine works on DXF. The other formats come in through importers that normalise
to the same internal model.

**Reason:** `.cdr` is proprietary binary RIFF with no reliable free parser; implementing it would
be most of the total effort of the project without contributing anything to the core. Corel and
Rhino export DXF, which is also the de facto CNC standard and survives with layers and colours
intact.

`.ai` and `.3dm` are read too because they are cheap: the `.ai` exported from Corel is
AI3/PostScript in plain text, and `rhino3dm` is McNeel's official library.

### 3.2 Raster nesting, with the interface ready for NFP

**Decision:** the collision oracle is implemented with bitmasks (raster). The interface is
designed so that a No-Fit Polygon (NFP) implementation can replace it without touching the rest.

**Reasons in favour of raster:**

1. The spacing between parts reduces to a morphological dilation of the mask, instead of a polygon
   offset (numerically fragile).
2. The use of holes comes out without dedicated code (see §5.2).
3. It handles concavity and interlocking without fragile computational geometry.
4. The raster's precision does not contaminate the output: it only decides *positions*; the final
   file carries the exact curves.

**For the door to NFP to stay genuinely open, three mandatory constraints:**

1. **The exact polygon is always the source of truth.** The raster mask is a derived cache.
   Re-vectorising the result of morphological operations is forbidden.
2. **The spacing offset is the oracle's responsibility**, not a shared preprocessing step.
   The raster dilates masks; NFP would offset polygons.
3. **The benchmark exists from the start**, so that the comparison between engines is made with
   measured numbers (% utilisation and seconds).

Roughly 85% of the code is engine-agnostic: I/O, part extraction, flattening, search strategy,
reporting and verification.

### 3.3 Part model

- One **closed outer outline** = the cutting perimeter of one part.
- Everything contained inside travels **rigidly** with it (same translation, rotation and mirror).
- Two separate outer outlines do **not** travel together: they are independent parts.
- **Even/odd containment rule by depth:**
  - level 0 → outer outline of a part
  - level 1 → hole (frees material)
  - level ≥ 2 → **independent part**, relocated elsewhere (it does not stay nested where it was
    drawn)

  This rule describes how the **input drawing is interpreted**. It does not constrain
  **placement**: the engine can indeed end up putting a part inside another's hole (§5.2), it
  simply does not assume that the nesting drawn by the user has to be preserved.

### 3.4 Colour is a passive attribute

Every outline is a through cut as far as geometry is concerned. The engine **never** interprets
colour or layer.

However, the output file **must preserve the original colours and layers** of each entity. That
comes for free from the decision in §3.5.

### 3.5 Flatten to decide, transform the originals to write

**This is the guiding principle of the architecture.**

The engine flattens curves into polylines and rasterises in order to work out *where* each part
goes. The result of that whole process is one tuple per part: `(sheet, x, y, angle, mirrored)`.
That rigid transformation is applied at the end to the **original entities** — splines, arcs,
colours, layers.

Consequences:
- There is no loss of geometric fidelity in the output.
- Preserving colour and layer requires no dedicated code.
- The flattening can be as coarse as convenient without degrading the result.

### 3.6 Rotation governed by the material

A single parameter unifies the cases: **`tolerancia_veta`** (in degrees). The allowed angles are
the ones falling within ±`tolerancia_veta` of 0° or 180°.

| Value | Effect | Use case |
|---|---|---|
| `180` | Free rotation | MDF (grain is irrelevant) |
| `5` | 0° / 180° only, cross cutting blocked | Plywood, phenolic |

It lives in the material catalogue alongside the sheet size.

**Mirroring:** enabled by default. Since everything is a through cut and the material is
homogeneous, a mirrored part turned over is the original part. It is extra density at no cost.
Flag `--sin-espejo` turns it off.

Mirroring is **always compatible with the grain constraint**: reflecting a part does not change
the direction of its grain axis, only its sense. Therefore `--sin-espejo` and `tolerancia_veta`
are independent of each other.

### 3.7 Input contract: one shape = one part

The input file **is** the bill of materials: every outer outline is a part to cut. There is no
quantity table and no need to name parts.

A global multiplier `--copias N` nests the entire contents of the file N times. That is how you
draw one bench and ask for five.

### 3.8 Multi-sheet optimisation criterion

1. **Minimise the number of sheets.**
2. Once that minimum is reached, **compact the last sheet** as much as possible, so that the
   leftover is one large usable piece instead of scattered offcuts.

---

## 4. Architecture

### 4.1 Data flow

```
file (.dxf/.ai/.3dm)
  │
  ├─ reading ─────────►  raw entities  (geometry + colour + layer)
  │                              │
  │                    flattening (Bézier/arc/spline → polyline)
  │                              │
  │                    chaining (join loose segments into closed outlines)
  │                              │
  │                    containment tree (what is a part, what is a hole?)
  │                              ▼
  │                           Parts  ──── × copies
  │                              │
  │                    ┌─────────▼─────────┐
  │                    │      PACKER       │ ◄── material + configuration
  │                    │   (multi-sheet)   │
  │                    └─────────┬─────────┘
  │                              ▼
  │                         Placements
  │                   (sheet, x, y, angle, mirror)
  │                              │
  │                  exact geometric verification
  │                              │
  └──── original entities ───────┤
                                 ▼
                    ┌────────────┴────────────┐
                    ▼                         ▼
              resultado.dxf             preview.png
```

### 4.2 Modules

```
io/          dxf_reader · ai_reader · rhino_reader · dxf_writer · preview
geometry/    flatten · chaining · nesting_tree · transform · verify
model/       Part · Sheet · Placement · Material
engine/      oracle (INTERFACE) · raster_oracle · strategy · packer
config/      materials.yaml
cli.py
bench/       benchmark over real files
```

### 4.3 Main boundaries

**`engine/oracle.py` — the seam of the engine.** Two operations:

```
feasible_positions(part, angle, sheet_state) → candidates
mark(part, angle, position)                  → sheet_state'
```

`raster_oracle` implements it with bitmaps and returns candidates as a bitmap. A future
`nfp_oracle` would implement it with polygons and return polygonal regions. Same signature,
different internal representation. The spacing offset lives inside the oracle.

**`io/` ↔ the rest.** Every reader returns the same structure. Adding a format is a new file, with
no changes to the engine.

### 4.4 Intermediate entity model

Every reader normalises to the same primitives, shaped like DXF so that the writer is trivial:

`Line` · `Arc` · `Circle` · `Ellipse` · `Cubic Bézier` · `Polyline`

Each with its **colour and layer of origin**.

### 4.5 Two `geometry/` modules that look like a detail and are not

- **`chaining`** — DXF files exported from Corel bring the outlines broken into dozens of loose
  `LINE`/`ARC`/`SPLINE` entities, not as closed polylines. The cycles have to be reconstructed by
  joining endpoints within a tolerance. **This is the normal case, not the exceptional one.**
- **`nesting_tree`** — containment analysis with the even/odd rule from §3.3.

They are the most boring code in the project and where the bugs hide that later look like
"the nesting is broken".

---

## 5. The nesting engine

### 5.1 Two masks per part, per angle

| Mask | Definition | Use |
|---|---|---|
| `ocupada` | Real material: outer outline **minus** holes | Stamped onto the sheet when placing |
| `holgura` | `ocupada` dilated by the spacing `sep` | Used to test collision |

**Collision rule:**

```
placa_ocupada  =  union of the `ocupada` of the parts already placed   (NOT dilated)

part fits  ⟺  part.holgura  ∩  placa_ocupada  =  ∅
```

Dilating **only the part that moves** and testing against **undilated** material makes the spacing
count exactly once. Dilating both would give `2 × sep` of real spacing and invisible waste: that
is the classic bug of this approach.

**Sheet edge:** independent parameter. `part.ocupada` must fit inside the sheet rectangle
**eroded** by `borde`.

**Rotation:** the masks are re-rasterised from the exact polygon at every angle. The bitmap is
**not** rotated (that introduces cumulative artefacts).

### 5.2 Holes come out without dedicated code

The three desired properties follow from the definition in §5.1:

1. **The hole is free area** → its region never enters `placa_ocupada`.
2. **The spacing against the hole's wall is respected** → the material at the hole's edge *is* in
   `placa_ocupada`, so the small part's `holgura` collides with it.
3. **Recursive nesting** → a part inside the hole of a part that is inside another hole works with
   no special case.

This property is the main reason raster beats NFP in this project: with NFP you would need to
implement *inner-fit polygons* for every hole.

### 5.3 Position search

Evaluating position by position is not viable (millions of candidates per part). **All positions
are evaluated at once** through FFT correlation:

```
correlation( placa_ocupada , part.holgura )  →  overlap at EVERY position
```

The positions with overlap `0` are exactly the feasible ones.

**Resolution:** 1 mm/px by default, configurable with `--resolucion`. On a 1830 × 2600 sheet that
is ~4.8 M points. The discretisation error is absorbed by the spacing margin and **always on the
conservative side**.

**Optimisation:** the correlation is computed only over the **active region** of the sheet (used
area + size of the part), not over the whole sheet. With the sheet mostly empty, the correlations
are small.

### 5.4 Position score

A part fitting is not enough; you have to choose well among the feasible positions:

```
score  =  w₁ · (bottom-left)  +  w₂ · (contact)
```

- **bottom-left** — pushes everything towards one corner; concentrates the leftover into one large
  block.
- **contact** — measures how much of the part's perimeter ends up resting against already placed
  material. It is obtained with a second correlation using the `holgura` widened by an extra band:
  where that band overlaps a lot, the part is wedged in.

**The contact term is what produces the interlocking** between curved parts. Without it,
bottom-left stacks and leaves gaps.

### 5.5 Order, angles and multi-sheet

- **Insertion order:** descending area. The large parts define the structure; the small ones fill
  interstices and holes.
- **Angles:** for each part every angle allowed by the material is tried, plus the mirrored
  versions where applicable. The best `(angle, position)` is chosen.
- **Multi-sheet:** sheet 1 is filled until nothing else fits, then sheet 2 is opened, and so on.
  Then the criterion from §3.8 is applied.

### 5.6 Effort levels

What the extra time buys is retries with a different insertion order, keeping the best result.

| `--esfuerzo` | Behaviour |
|---|---|
| `rapido` | 1 greedy, deterministic pass |
| `normal` *(default)* | ~10 retries with perturbed orders, keeps the best |
| `lento` | Directed search (simulated annealing) over order + angles |

**The concrete times of each level are calibrated with measurements from the benchmark (§7.3),
they are not fixed by estimation.** The initial reference estimate is ~15-30 s per pass, but it
depends heavily on the number and size of the parts.

### 5.7 Exact geometric verification

After packing, and **before writing the file**, the exact polygons are verified (not the bitmaps):

- No pair of placed parts overlaps.
- No distance between parts is smaller than `sep`.
- No part exceeds the usable area of its sheet.

If any verification fails, the program **reports the problem and fails**, instead of silently
writing an incorrect DXF.

This verification serves three functions: safety net in production, oracle for the tests (§7), and
referee for the comparison between engines the day an NFP implementation exists.

### 5.8 Memory management

The masks are cached by `(part, angle, mirrored)`. With many allowed angles the cache grows
linearly; they are stored bit-packed and discarded by LRU if necessary.

---

## 6. Input, output and errors

### 6.1 Readers

| Format | Library | Notes |
|---|---|---|
| **DXF** | `ezdxf` | Explodes blocks (`INSERT`). Reads units from `$INSUNITS` |
| **AI** | own (~200 lines) | AI3/PostScript: operators `m` `L` `C` `v` `y` `s` `f`. Colour from `K`/`G`. Units in points → mm (× 25.4/72) |
| **3DM** | `rhino3dm` | Nurbs/Arc/Polyline curves. Colour from the layer. Projects to XY and validates planarity |

**Units: everything is normalised to millimetres on reading.** If a DXF does not declare units,
the program **does not guess**: it demands `--unidades mm|cm|in`. A wrongly inferred unit ruins a
whole sheet.

### 6.2 Output

**DXF:** a single file, sheets in a horizontal row separated by a margin, each with its outline
rectangle on a `_PLACA` layer. On each sheet, the original entities with the rigid transformation
applied, colour and layer intact.

**PNG preview:** the sheets rendered with their utilisation percentage.

**Console summary** (the program prints in Spanish):

```
Placa 1/3   aprovechamiento 87,4%
Placa 2/3   aprovechamiento 85,1%
Placa 3/3   aprovechamiento 41,9%   ← sobrante útil ~1830×1080
─────────────────────────────────
60 piezas · 3 placas · 71,5% total · 4m 12s
```

### 6.3 Error handling

General rule: **warn and carry on** when the problem is cosmetic; **fail hard** when it can ruin
material.

| Situation | Response |
|---|---|
| Outlines broken into loose segments | Chained by tolerance. Normal case |
| Outline that does not close | **Error** with the coordinates of the gap and the missing distance. Flag `--tol-cierre` |
| Duplicate overlapping lines | Deduplicated, with a warning and a count |
| `TEXT`, `DIMENSION`, `HATCH` | Ignored, with a warning and a count |
| Self-intersecting outline | **Error** with the location |
| Part larger than the usable area | **Error** with identification and measurements |
| Zero-area or degenerate outline | Skipped, with a warning |
| DXF with no declared units | **Error**: demands `--unidades` |

### 6.4 Configuration

```yaml
# materials.yaml
mdf18:
  placa: [1830, 2600]
  tolerancia_veta: 180      # free rotation
multilam18:
  placa: [1220, 2440]
  tolerancia_veta: 5        # no cross cutting
```

### 6.5 Command line interface

```bash
nest banqueta.dxf --material mdf18 --copias 5 \
     --sep 6 --borde 10 --angulos 0,90,180,270 \
     --esfuerzo normal -o resultado.dxf
```

| Flag | Default | Description |
|---|---|---|
| `--material` | *(required)* | Key from the material catalogue |
| `--copias` | `1` | Global multiplier of the file's contents |
| `--sep` | `5` | Minimum spacing between parts, in mm |
| `--borde` | `10` | Margin against the sheet edge, in mm |
| `--angulos` | `0,90,180,270` | Candidate angles, filtered by `tolerancia_veta` |
| `--esfuerzo` | `normal` | `rapido` \| `normal` \| `lento` |
| `--sin-espejo` | *(off)* | Disables mirroring of parts |
| `--resolucion` | `1` | Raster resolution, in mm/px |
| `--unidades` | *(auto)* | `mm` \| `cm` \| `in`. Required if the file does not declare them |
| `--tol-cierre` | `0.1` | Outline chaining tolerance, in mm |
| `-o` | *(required)* | Output DXF file |

---

## 7. Testing

**The exact geometric verifier from §5.7 is the oracle of the whole test strategy.**
Any output, from any engine, with any configuration, has to pass it.

### 7.1 Unit tests

Coverage of `geometry/`: `flatten` (bounded chord error), `chaining`, `nesting_tree` (even/odd
containment), `transform`.

With property-based tests:
- The area of a polygon is invariant under rotation and translation.
- Mirroring twice is the identity.
- Chaining an already closed outline does not modify it.
- Rotating a `tolerancia_veta = 180` part by any allowed angle preserves its occupied area.

### 7.2 Integration tests

Full pipeline over synthetic cases with a known answer. Example: four 100 mm squares on a 220 mm
sheet with `sep = 10` and `borde = 0` → exactly 4 fit.

### 7.3 Benchmark

Runs over the project's real files (`.ai`, DXF exported from the `.cdr`, `.3dm`) and measures
**% utilisation, number of sheets and seconds**.

It serves three functions:
- Calibrating the effort levels of §5.6 with measured data.
- Detecting quality regressions.
- Refereeing the raster vs NFP comparison if the second engine is implemented.

### 7.4 Regression

With a fixed seed, `--esfuerzo rapido` is deterministic. Any change that moves the utilisation
becomes visible.

### 7.5 TDD focus

`chaining` and `nesting_tree`. That is the code with the most edge cases and the one that produces
the failures later misread as "the nesting is broken".

---

## 8. Build order

| # | Milestone | Justification |
|---|---|---|
| **1** | Model + `geometry/` + **exact verifier** | Nothing is trustworthy until the referee exists |
| **2** | DXF reading/writing + trivial packing (bounding box) + **benchmark** | Full end-to-end pipeline as early as possible: there is already an output DXF with real files, even if it nests badly. And it is already being measured |
| **3** | `raster_oracle`: masks, FFT, contact score | The real engine. It goes in behind the interface; the benchmark quantifies the improvement over milestone 2 |
| **4** | Multi-sheet, effort levels, CLI, preview | The product |
| **5** | `.ai` and `.3dm` readers | Independent of the engine; they can be done in parallel |
| **6** | Effort calibration with measurements | Closing with numbers |

**Milestone 2 goes before 3 deliberately:** having the whole circuit working with bad nesting is
worth more than having excellent nesting you cannot open the file from.

---

## 9. Dependencies

| Library | Use | Milestone |
|---|---|---|
| `numpy` | Raster masks, algebra | 1 |
| `scipy` | FFT (`fftconvolve`), morphology (`binary_dilation`) | 3 |
| `ezdxf` | DXF reading and writing | 2 |
| `shapely` | Exact geometric verification, containment analysis | 1 |
| `Pillow` | Polygon rasterising, PNG preview | 1 |
| `rhino3dm` | `.3dm` reading | 5 |
| `PyYAML` | Material catalogue | 4 |

The `.ai` reader requires no dependencies: it is an in-house AI3/PostScript parser.

**Note:** `shapely` is used and not `pyclipper` for the verification. `shapely` directly exposes
the queries that are needed (`intersects`, `distance`, `contains`), whereas `pyclipper` is
lower-level. `pyclipper` would only come in if an NFP engine is implemented, for its
`MinkowskiDiff` operation.

---

## 10. Known risks

| Risk | Mitigation |
|---|---|
| Corel's DXF files come in dirty (broken outlines, duplicates, spurious entities) | Robust `chaining` with tolerance + deduplication + explicit filtering with a warning. It is the TDD focus |
| The performance of the FFT search does not reach the target times | Correlation restricted to the active region; configurable resolution; the effort levels are calibrated with measurements instead of being promised in advance |
| The contact score needs weight tuning | The benchmark measures the impact of each combination of weights over real files |
| Parts nested inside holes move when cut | Declared limitation. Bridge generation is out of scope for v1 |
