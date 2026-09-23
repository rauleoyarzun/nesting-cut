# Estimated time, before and during the layout

*[Español](2026-09-22-tiempo-estimado-design.es.md)*

Date: 2026-09-22
Status: approved

## 1. What is being built

A layout can take from seconds to over ten minutes: `BANQUETA ALTA
NESTING.ai` with 8 positions and free rotation took 651 s; with grain, 126 s.
Today the bar says how many parts are placed, but not how much is left, and
before starting it says nothing. Whoever picks 8 positions does not know they
just multiplied the wait by five.

Two figures:

1. **While running:** "Faltan aprox. 9 min · termina ~17:42", refined as it
   goes.
2. **Before starting:** "Tarda aprox. 10 min" next to Acomodar, recomputed
   when the options that matter change.

### Out of scope

- A history of runs to learn the machine's speed. The live probe (3.2) is
  enough and leaves no files in the user folder.
- Estimation in the CLI.

## 2. The unit of work is the query

A **query** is one call to `Oracle.best_placement(part, angle, mirror)`: where
does this part fit, in this orientation, on this sheet. Nearly all of `pack`'s
time goes there, and each query costs about the same on a given sheet and
resolution.

Counting placed parts, as the bar does today, misleads: a part that does not
fit on sheet 1 spends its queries anyway and spends them again on sheet 2; and
the final phases (recovery, compaction) place no new parts but are a large
share of the time.

### 2.1 What the engine reports

`Avance` gains two fields:

- `consultas_hechas: int` -- accumulated since `pack` started, never reset
  between attempts or phases.
- `consultas_previstas: int` -- the best forecast of the total at that moment.

The forecast is built per phase and corrected as more becomes known:

- **At start:** per attempt, `parts × orientations` on the first sheet, plus
  the pending parts queried again on later sheets, with the sheet count
  estimated by area (part area over usable area, divided by a typical
  utilisation of 0.4). Plus one pass per sheet before the last for recovery,
  and one pass over the last sheet for compaction.
- **When the first attempt ends:** the real query cost of one attempt is
  known; remaining attempts are forecast the same, and the real sheet count
  replaces the estimated one.
- **With the portfolio, as each variant ends:** the remaining ones are
  forecast as the average of those already finished (cut ones included), not
  as the base: cut and pair variants cost much less, and with the base alone
  "Faltan aprox." came out almost three times too high. The final phase is
  forecast from the sheets of the best finished variant.
- **On entering recovery and compaction:** the sheets and their parts are
  known, so those phases' forecast becomes exact as an upper bound.

`consultas_previstas` never drops below `consultas_hechas`.

The format is phase-agnostic: the new engine (interlocked pairs, diverse
orientations) adds its own forecast queries and the estimator does not need to
know which phase it is.

### 2.2 The final phases report

Today `_recuperar_de_la_ultima_placa` reports per part, and
`_compact_last_sheet` does not report. Both now emit `Avance` with the
queries, like the greedy pass. Compaction also becomes cancellable.

## 3. The two figures

### 3.1 While running

Computed by the server (`nesting_app.jobs`), which has the clock:

    seconds_per_query = elapsed / consultas_hechas
    remaining = seconds_per_query × (consultas_previstas - consultas_hechas)

with an exponential moving average over `seconds_per_query`, so a single slow
query does not move the number.

The job status gains `restante_s: float | None`. It is `None` during the first
5 seconds or the first 20 queries, whichever comes last: before that there is
no data.

The screen shows:

- with `None`: "Calculando el tiempo…"
- otherwise: "Faltan aprox. 9 min · termina ~17:42"

Rounding, so as not to fake a precision that is not there:

| remaining | shown |
|---|---|
| over 10 min | in steps of 5 min |
| 2 to 10 min | in steps of 1 min |
| under 2 min | "menos de 2 min" |

Stability: the displayed number drops freely, but only rises if the new value
holds for 5 seconds. A number that jumps from 8 to 12 and back to 8 is worse
than one that stays at 8.

The finish time is computed on the screen with the local clock, from the
already rounded remaining time.

### 3.2 Before starting

New route `POST /api/estimar`, with the source and the parameters. Returns
`{"segundos": float}` or `{"segundos": null}` if it cannot estimate (file not
read, or parameters do not validate).

    seconds = measured_seconds_per_query × forecast_queries_at_start × FACTOR_LLENO

- `measured_seconds_per_query` comes from a real probe with the file's
  largest part, on an empty sheet of the chosen material, at the chosen
  resolution, so the number holds on any machine. Since phase 2 of the pairs
  plan (2026-09-23) it is measured two ways: with the query threads (all of the
  part's orientations, divided by their count), which is what the base pass and
  final phase cost, and with a single thread, which is what each batch variant
  costs in the portfolio's processes. In both, the masks are built before the
  clock starts: timing the rasterization made the factor jump from 0.5 to 2
  depending on the file.
- `forecast_queries_at_start` is the same forecast as 2.1.
- `FACTOR_LLENO` corrects for a query on a sheet with parts costing more than
  on an empty one (the exact search walks more candidates). It is a constant,
  calibrated on the bench files and documented with its measurements where it
  lives.

The screen shows "Tarda aprox. 10 min" next to Acomodar, with the same rounding
as 3.1, and recomputes it 400 ms after the last change to Positions, Angles,
mirror, Effort, Resolution, Material, Grain, Copies, Cores, Separation, Border
or Offcuts. While computing
it keeps the previous value; if the route returns `null`, it shows nothing.

## 4. Tests

- Engine: `consultas_hechas` is monotonic and ends equal to the real number of
  `best_placement` calls (counted with a spy oracle);
  `consultas_previstas >= consultas_hechas` on every report; compaction
  reports and cancels.
- Forecast: after the first attempt, the forecast's error against the real
  total is under 25% on the bench files.
- `jobs` estimator: `None` before 5 s / 20 queries; the arithmetic with fake
  queries and clock; the moving average.
- Rounding and stability: a table of cases in JavaScript (the `tests/app`
  tests).
- `/api/estimar`: returns a number for a read source, `null` without a source
  or with invalid parameters.
- Calibration: `bench/calibrate.py` gains the `FACTOR_LLENO` measurement, and
  a test checks that the pre-run estimate lands within ×2 of the real time on a
  small file.
