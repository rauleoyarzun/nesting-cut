# Grain per run, and positions that respect it

*[Español](2026-09-22-veta-por-corrida-design.es.md)*

Date: 2026-09-22
Status: approved

## 1. What is being built

Today grain lives only in the catalogue. Picking multilam18 sets "respect the
grain" without the screen saying so, and the engine silently drops every angle
other than 0° and 180°: whoever picks "8 positions" believes eight are tried,
and two are.

A real job found it (`BANQUETA ALTA NESTING.ai`, multilam18, sep 8, margin 5,
8 positions): the program gave 2 sheets, and a hand layout fit in 1 by turning
four frames 90°. That layout breaks the grain; with the grain respected, 1
sheet is impossible (the tightest column of six frames at 0° and 180° measures
2530 mm against 2430 usable). The program was not wrong: it did not say.

Two changes:

1. **Grain is visible and changeable per run.** A new control on the main
   screen, starting from the material's value and changeable without touching
   the catalogue.
2. **Positions obey the grain.** With the grain respected, Positions is fixed
   at 0° and 180°; if the user had something else picked, a dialog says so at
   the moment of the conflict and lets them choose.

### Out of scope

- Intermediate grain tolerances (e.g. 15°). The interface keeps speaking in
  two words, "respect" and "does not matter", like the catalogue.
- Remembering the per-run choice. It is lost on changing material, on purpose
  (see 2.2).

## 2. The decisions, and why

### 2.1 Grain is a run parameter with a default

The catalogue says what the material *usually* needs. A given job may not
need it: hidden parts, a phenolic board used as a base. So grain behaves like
the offcuts: it belongs to this run, not to the catalogue. The catalogue only
provides the starting value.

### 2.2 Changing material resets the grain

Picking another material returns the control to that material's value.
Carrying a "does not matter" from an MDF over to a multilam would be exactly
the silent error this work fixes.

### 2.3 The dialog appears as soon as there is a conflict, not on Acomodar

There is a conflict when grain is "respect" and the chosen positions include
some angle the grain does not allow. Three paths lead there: picking a
material with grain, switching the control to "respect", or typing custom
angles. In all three the dialog shows at that moment: finding out on pressing
Acomodar, after loading everything, is finding out late.

The dialog offers two ways out and neither is "cancel", because there is no
neutral state to go back to:

> **Este material respeta la veta**
> Sólo se puede girar a 0° y 180°. Tenías elegidas 8 posiciones.
> [Usar 0° y 180°]   [No me importa la veta]

- **Usar 0° y 180°** keeps grain at "respect" and fixes Positions.
- **No me importa la veta** switches the control to "does not matter" and
  keeps the positions that were there.

Four positions (0, 90, 180, 270) is also a conflict: 90 and 270 would be
dropped. The dialog says how many positions there were, whatever the number.

### 2.4 With grain respected, Positions locks and remembers

The dropdown shows "2 — 0° y 180°", disabled, with a line underneath: "El
material respeta la veta". What the user had before is kept, and on switching
grain to "does not matter" the dropdown returns to it. The custom Angles list
is kept and restored as well.

### 2.5 Offcut cross-grain looks at the control, not the material

The "Veta cruzada" checkbox already turns off on free materials. It now turns
off whenever the *control* says "does not matter", whether from the material
or by choice.

## 3. Engine, API and CLI

- `NestParams` gains `veta: Literal["respetar", "libre"] | None = None`.
  `None` means "the material's".
- A new function in `nesting.params`, `tolerancia_de_veta(p, material)`,
  returns the degrees that apply to the run: the material's if `veta` is
  `None`, `VETA_RESPETAR` or `VETA_LIBRE` otherwise. Both constants move from
  `nesting_app.materials_store` to `nesting.model.material`, because the
  engine cannot import the interface.
- `a_supply` uses that tolerance for the material sheet and for every offcut.
- `validar` rejects a run whose angle set is empty after filtering by grain,
  with a message naming the requested angles and the ones the grain allows.
  Today that ends in a `PartTooLargeError` that talks about sizes, not
  angles. `validar` needs the tolerance for this, so it takes the material as
  an optional argument; without a material it skips that check.
- `ParamsEntrada` gains `veta: Literal["respetar", "libre"] | None = None`.
- The CLI gains `--veta {respetar,libre}`, defaulting to the material's, and
  builds its sheet plan with `a_supply` instead of by hand, so the rule lives
  in one place.
- The materials route already returns `veta` per material; the JavaScript
  uses it as the control's starting value.

## 4. Screen

- New control under Material, with its info button:
  **Veta** · ( ) Respetar — sólo 0° y 180° · ( ) No importa.
- The info text for Positions and Angles loses the sentence "si el material
  respeta la veta, sólo se usan 0° y 180°": the screen now shows it instead of
  explaining it.
- The dialog uses the same component as `cartel-unidades` and `cartel-error`.

## 5. Tests

- `tolerancia_de_veta`: `None` returns the material's; `respetar` and `libre`
  override either.
- `a_supply`: the tolerance reaches the material sheet and the offcuts alike.
- `validar` with material: rejects `angulos=(90,)` with grain respected and
  accepts it with grain free; without a material it does not check.
- CLI: `--veta libre` on multilam18 allows turning 90° (a part that only fits
  lying down fits); `--veta respetar` on mdf18 does not.
- API: `veta` travels through to `NestParams`; omitting it gives `None`.
- Interface (the `tests/app` tests that already read the JavaScript):
  changing material resets the control; the conflict shows the dialog on all
  three paths; each dialog button leaves the state 2.3 describes; switching
  back to "does not matter" restores Positions and Angles.
