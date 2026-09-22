# Interlocked pairs and a parallel portfolio of combinations

*[Español](2026-09-22-pares-y-cartera-design.es.md)*

Date: 2026-09-22
Status: approved

## 1. What is being built

`BANQUETA ALTA NESTING.ai` (57 parts: six identical 1055×450 frames plus
slats; 1220×2440 sheet with free grain, sep 8, margin 5, 8 positions) comes
out in **2 sheets**. Diego laid it out by hand in **1**, verified.

### 1.1 Why today's engine fails

- It places part by part in the best spot of the moment (bottom-left plus
  contact) and never backtracks. When it places the first frame it does not
  know it should leave room for the second in one exact position.
- The `normal` and `lento` restarts only permute the insertion order. Six
  identical copies permuted give the same layout: those restarts explore
  nothing.
- Measured: forcing Diego's orientations, or picking the orientation at
  random among the four best (10 seeds), still gives 2 sheets.

### 1.2 What did work (experiment of 2026-09-22)

1. Search for the best ways to interlock **two copies** of a frame: every
   relative position at once by FFT, 2.5 s for 16 orientations.
2. Fuse each **pair** into a single composite part.
3. Offer today's engine, untouched, those composites instead of the loose
   frames.

Results, each one greedy pass of ~150 s at 1 mm/px:

| pair types for the three pairs | sheets |
|---|---|
| no pairs (today) | 2 |
| minimum-box one (1812×450) ×3 | 2 |
| diagonal (1511×560) ×3 | 2 |
| stacked (1055×879) ×3 | 2 |
| diagonal ×1 + stacked ×2 | 2 |
| **diagonal ×2 + stacked ×1** | **1** |
| **diagonal ×2 + alternative stacked (1055×886) ×1** | **1** |

Two lessons that shape the design:

- **No single pair type wins on its own.** The winning combination mixes two
  types, which is exactly what Diego did. Combinations have to be tried.
- **Trying them in parallel is nearly free.** Five simultaneous passes took
  as long as one: today's engine uses one core out of fourteen.

### 1.3 What is built

- **Equal parts**: the engine recognises copies of the same shape, even when
  drawn translated, rotated or mirrored.
- **Pairs**: for the largest repeated shapes, it searches several ways of
  interlocking two copies.
- **Portfolio**: it builds variants (no pairs, different combinations of pair
  types, different orientations) and lays them out in parallel, one per
  core. The lowest `CostoLayout` wins, the usual criterion.
- **Cores**: a new control to pick how many to use.
- **"No se puede con menos placas"**: when the result equals the area lower
  bound, it says so.

### 1.4 Out of scope

- Groups of three or more interlocked copies. Pairs cover the failing case;
  if one shows up that needs triples, it gets measured first.
- Pairs of two different parts (a frame with a slat). The portfolio with
  loose parts already handles them well: the slat goes into the hole.
- Geometric lower bounds (like the grain-respecting frame column). The only
  bound reported is the area one.
- Speeding up a single combination with several cores. That is phase 2
  (section 8), subject to measurement.

## 2. Equal parts

New module `nesting/engine/iguales.py`.

Two parts are **equal** when one maps onto the other by a translation plus an
orientation **allowed by the run**: the angles the grain permits, and mirror
only if enabled. The rule depends on the run on purpose: with the grain
respected, a frame drawn rotated 90° is not equal to one drawn lying down,
because mapping it onto the other would break the grain.

- A quick **fingerprint** rules out almost everything: net area, perimeter,
  hole count and each hole's area, rounded to 0.01 mm.
- Among parts sharing a fingerprint, exact geometry confirms: each allowed
  orientation is tried, aligned by the bottom-left vertex of the box. If the
  symmetric difference area stays under 1 mm², they are equal, and the
  transform `g` taking each part onto its class representative is kept.
- Result: `list[Clase]`, each with its representative part and, per member,
  `(part_id, g)`.

## 3. Pairs

New module `nesting/engine/pares.py`.

### 3.1 Which classes get paired

Classes with **two or more** members whose part covers at least **2% of the
usable area** of the sheet, up to **two classes**, largest part first. A
paired slat barely gains room and does multiply combinations.

### 3.2 Pair types

Copy A is fixed at identity. For each allowed orientation of copy B:

- `A.occupied` is correlated with `B.clearance` by FFT, using the same masks
  from the run's `MaskCache`. Offsets with zero overlap are the possible
  interlocks.
- For each offset the pair's box area is computed from the pixel boxes,
  without rasterizing anything else.
- The best by box area are taken, **with neighbour suppression**: two
  candidates of the same orientation within 200 mm of each other are the same
  interlock, and a type whose composite has the same shape as one already kept
  does not count as new either. The experiment showed that without
  suppression the top two hundred are all the same one and the diagonal pair
  never shows up; while writing the plan it was measured that at 60 mm all six
  of normal's types came from one family sliding 60 mm at a time and the
  stacked one only showed up seventh.

Each candidate is confirmed with exact geometry: the real separation between
A and B must be at least `sep` and **less than `2·sep`**. The cap guarantees
the bridge in 3.3 takes room from nobody: no part fits in a gap under two
separations. The pair must also fit the sheet's usable area in some allowed
orientation.

Up to `TIPOS_POR_CLASE` types are kept: **6 in normal, 10 in lento**.

**When the run respects the grain:** B's orientation relative to A must be 0°
or 180°, and the whole pair's is also restricted to what the grain allows. So
every member ends at an allowed angle. The same holds for cross-grain
offcuts: composing two angles on the grain axis stays on the axis.

**Without mirror:** B cannot be mirrored, and the class cannot have used a
mirror in `g`, by the rule in 2.

### 3.3 The composite part

A pair becomes an ordinary `Part`, so the oracle, the masks and the packer
notice nothing:

- `outer` = A ∪ B ∪ a **bridge**: the segment between A's and B's closest
  points, thickened to 1 mm. The experiment showed morphological closing
  (dilate then erode) does not work: two frames touching at a corner split
  apart again on erosion.
- `holes` = A's and B's holes, still available for the slats.
- The result must be a single polygon. If it is not, the candidate is
  dropped.
- The composite carries a member table `(part_id, t)`, where `t` is that
  member's transform inside the pair (`g` composed with identity for A, and
  with the relative one for B).

### 3.4 Taking apart

Each placement of a composite with transform `T` becomes one placement per
member, with `T ∘ t`. Composition lives in `nesting/geometry/transform.py`
(`componer`), next to `apply_point`, the single definition of what a
transform does. The resulting angle is `T.angle + (−t.angle if T.mirror else
t.angle)`, mirror is `T.mirror xor t.mirror`, and the translation is
`apply_point(T, (t.dx, t.dy))`.

Pairs are taken apart **before** verifying, and the usual verifier checks the
real parts. A composite never reaches `verify`, the DXF or the preview.

## 4. The portfolio

New module `nesting/engine/cartera.py`. `pack()` delegates to it.

### 4.1 Variants

A **variant** is a list of parts (loose and composite), an insertion order
and, optionally, an orientation perturbation. They are generated **in a fixed
order** that depends only on the parts, the config and the seed:

1. **Base**: today's pass, no pairs, by area.
2. **Pair combinations**: for each pairable class with `n` members, each
   pair count `p` from `⌊n/2⌋` down to 1 is tried, with each multiset of `p`
   types. Leftover members go loose. With two classes they are combined. The
   order is by total box area, ascending, ties by type index.
3. **Order perturbations**: today's (`_perturb` over `by_area`).
4. **Orientation perturbations** (lento): for the parts in the top area
   decile, pick at random, with the seed, among the three best-scoring
   orientations instead of the best. Also applied on top of the best pair
   combination found.

### 4.2 How many are evaluated

Let `N` be the chosen number of cores (section 6).

| effort | variants evaluated | pairs |
|---|---|---|
| rapido | 1 (base) | no |
| normal | base + one batch | 6 types per class |
| lento | base + three batches | 10 types per class, plus orientation perturbations |

A **batch** is `max(N, 12)` variants: never fewer than 12, even with fewer
cores, in which case they are evaluated in several rounds of `N`. The user's
decision: the result must not depend on the machine. On the bench job the
winning combination comes out eighth, and with batches of `N` a 4-core
computer did not find it even in lento. With the minimum, every machine with
up to 12 cores tries exactly the same variants; a 4-core one takes about three
times longer in normal, and the estimated time says so before starting.

Batches are filled in the order of 4.1: pair combinations first, then order
perturbations and, in lento, orientation ones. With no pairable classes,
batches are filled with perturbations.

**Monotonicity guarantee**: with the same `N` and seed, normal's variants are
a prefix of lento's, and rapido is a prefix of normal. So `lento ≤ normal ≤
rapido` still holds by construction, as today. With different `N` the
guarantee does not apply, and it is documented as such: more cores explore
more.

### 4.3 When not to search

If the base already gives `placas_nuevas == cota_minima` (5.1), nothing else
is evaluated: there is nothing to gain in sheets, and the rest of the
criterion (material on the last) is only improved by the usual recovery and
compaction. So a job that fits comfortably in one sheet does not pay a second
more.

### 4.4 Parallel

- `concurrent.futures.ProcessPoolExecutor` with the `spawn` context on every
  platform, so macOS, Windows and Linux behave the same.
  `multiprocessing.freeze_support()` goes at the start of `desktop.main` and
  `cli.main`, because PyInstaller requires it.
- Each process builds its own `MaskCache` and oracle. It receives the parts,
  the config, the sheet plan and the variant, and returns `PackResult` plus
  `CostoLayout`.
- **Cutting what already lost**: a shared value holds the lowest
  `placas_nuevas` among finished variants. A variant that opens one sheet
  more than that number is abandoned, because it could never win. The result
  does not depend on when each process finishes: only strictly worse
  variants are cut.
- **Deterministic tie-break**: among equal costs the lowest variant index
  wins. The result does not depend on arrival order.
- Recovery (`_recuperar_de_la_ultima_placa`) and compaction
  (`_compact_last_sheet`) run only on the winner, in the main process and
  still with composites. Taking apart happens at the end.

### 4.5 Progress, cancelling and estimated time

- Each process sends its done queries over a `multiprocessing.Queue`. The
  main one adds them up and emits `Avance` with `consultas_hechas` and
  `consultas_previstas` (estimated-time spec, 2.1). A batch's forecast is the
  sum of its variants, and since they run in parallel the estimator divides
  by the measured joint throughput, not by one core's.
- The progress text becomes "Probando combinaciones 5 de 12 · placa mínima
  hasta ahora: 1", instead of the attempt's part count, which stops making
  sense in parallel.
- **Cancel**: a shared `multiprocessing.Event`; each process checks it in its
  report and raises `Cancelado`. The main one shuts the pool down with
  `cancel_futures=True` and raises `Cancelado`. No process is left alive.

## 5. Trust: the lower bound

### 5.1 The bound

`cota_minima = ⌈net part area / usable area of the Material sheet⌉`, with
usable area `(width − 2·margin) × (height − 2·margin)`. Computed only without
offcuts; with offcuts it is not reported, because the honest count with
sheets of different sizes is not that.

### 5.2 What is shown

- If `sheets == cota_minima`: "**No se puede con menos placas.**" in the
  result, and the same line in the CLI output.
- Otherwise, nothing. The area allowing fewer sheets does not mean they fit:
  the bench with grain has bound 1 and the real minimum is 2.

## 6. Cores

- `NestParams.nucleos: int | None = None`; `None` means the default.
- **Default**: `max(1, os.cpu_count() − 2)`, capped by memory:
  `⌊total memory × 0.5 / 400 MB⌋`. The 400 MB are the `MaskCache` budget
  (256 MB) plus the sheet grids and the process itself, measured during
  implementation and documented where the constant lives.
- Total memory is read with `os.sysconf` on macOS and Linux, and with
  `GlobalMemoryStatusEx` via `ctypes` on Windows. No dependencies are added.
- `validar` requires `nucleos >= 1`. A value above the cap is accepted and
  trimmed to the cap, with a warning.
- **Screen**: new control under Effort: **Núcleos** · [ 12 ▾ ] de 14, with
  the info button: "Más núcleos prueban más combinaciones en el mismo
  tiempo. Dejá alguno libre si vas a usar la computadora mientras acomoda."
  The dropdown goes from 1 to the cap. A new status route `GET /api/sistema`
  returns `{"nucleos": 14, "tope": 12, "omision": 12}`.
- **CLI**: `--nucleos N`.
- The pre-run estimated time (estimated-time spec, 3.2) multiplies the
  forecast queries of one pass by each batch's rounds,
  `⌈max(N, 12) / N⌉`.

## 7. Tests

- `iguales`: a part and its translated, 90°-rotated and mirrored copies are
  one class with a free config; with grain respected the 90° one is not; with
  no mirror the mirrored one is not; `g` takes each member onto the
  representative (symmetric difference < 1 mm²).
- `pares`: on the bench frame the diagonal type (box 1511×560 ± 5 mm) and the
  stacked one (1055×879 ± 5 mm) show up; every candidate satisfies
  `sep ≤ separation < 2·sep`; with grain respected no candidate has B at 90°;
  the composite is a single polygon and keeps the holes.
- `componer`: for random transforms, applying `componer(T, t)` equals
  applying `t` then `T`.
- Taking apart: `verify` over the taken-apart real parts finds nothing, with
  and without mirror.
- Portfolio: variants come out in the same order for the same seed; the
  result is the same with 1 and 4 processes for the same variant list
  (determinism); normal is a prefix of lento; a variant with more sheets than
  the best gets cut; cancelling leaves no process alive.
- Bound: "No se puede con menos placas" is reported when it applies, and
  never with offcuts.
- **The test that matters**: `BANQUETA ALTA NESTING.ai` is copied to
  `bench/files/banqueta-alta.ai`, which is **not versioned** (`bench/files/`
  is already in `.gitignore`: design files are the user's work). With a free
  1220×2440 sheet, sep 8, margin 5, 8 positions, normal effort, 1 mm/px:
  **1 sheet**, verified. With multilam18 (grain): 2 sheets, and no minimum
  line (bound 1). It is a slow test, marked as such, that **skips with a
  clear reason if the file is missing**, and also a bench row. So the suite
  does not depend on that file alone, a fast test builds a synthetic case
  with the same trap: six copies of an L-shaped part that only fit one sheet
  when interlocked in pairs of two different types.
- Packaging: the `--autotest` in `packaging/construir.sh` does a run with 2
  processes, because a `spawn` without `freeze_support` works from the repo
  and hangs in the executable.

## 8. Phase 2: speeding up a single combination (subject to measurement)

When the batch fills every core, splitting one combination adds nothing. It
does help in rapido and in jobs without repeated parts. Two ideas, measured
before deciding:

- **Not repeating work**: today, for each of a part's 16 orientations,
  `fftconvolve` transforms the sheet again, and the sheet did not change. If
  the sheet's transform is reused across orientations (at a common FFT size),
  it helps on any machine.
- **Splitting orientations**: a part's 16 queries are independent and can be
  split across threads, if scipy releases the GIL in the FFTs.

Criterion: whatever cuts rapido's time by at least 30% over `bench/files`,
with byte-identical results, gets implemented. If neither does, the
measurement is documented and nothing is done.
