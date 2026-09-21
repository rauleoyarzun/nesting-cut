# Diagnostic tools

*[Español](README.es.md)*

Things you run by hand, not in the suite.

## `ventana_real.py`

Drives the real desktop window from the outside and checks two things that
cannot be seen any other way.

```bash
.venv/bin/python herramientas/ventana_real.py            # both checks
.venv/bin/python herramientas/ventana_real.py layout
.venv/bin/python herramientas/ventana_real.py cierre
```

It opens a window, it needs a screen and it takes about ten seconds. It exits
with 1 if it finds any problem, and lists them in Spanish.

### Why it exists

This interface has a class of defect that you cannot see by reading the code or
by running the page in a browser. It lives in Cocoa's main thread: that is
where WKWebView draws, and where pywebview runs the handlers that need to
return a value. Three real bugs came out of here, and all three had already
been through code review and through the browser:

- **The action bar stretched to the full height.** Without an explicit
  `grid-row`, the row each child lands on depends on how many siblings are
  hidden, and the materials screen hides exactly the middle one. It ends up
  covered and invisible; on the way back, WKWebView does not relocate it and
  the main screen stays at 0 px until a resize forces the recalculation.
- **Closing with an unsaved layout hung the program forever.** The `closing`
  handler runs on the main thread, and the dialog it opened queued its drawing
  on that same thread and then waited for it.
- **The enlarged review stretched the grid column** instead of scrolling.

### When to reach for it

When something looks or behaves differently in the window than in the browser,
when a hang appears on closing or on opening a dialog, or after touching
`desktop.py`, the layout in `app.css` or the switch between screens.

### How it checks the close

The real dialog would wait for a person, so it replaces it with one that
imitates its exact shape —`AppHelper.callAfter` to draw, plus a semaphore to
wait for the answer— and answers it itself. That shape is precisely the one
that used to hang. The close is triggered with `AppHelper.callAfter`, that is,
on the main thread: calling it from the script's thread would reproduce
nothing, because the bug is exactly that the handler runs on the main one.

The close check is macOS only; on another platform it is skipped and says so.

### Its own judgement is tested

A diagnostic tool that has stopped detecting things looks just like one that
finds no problems. The part that makes the judgement (`problemas_de_medida`) is
pure arithmetic and lives in `tests/test_herramienta_ventana_real.py`, with the
numbers it measured on the real window before and after each fix.

## `globos_reales.py`

Exercises the options' help bubbles (`src/nesting_app/web/info.js`) in the
real desktop window, driving them from the outside.

```bash
.venv/bin/python herramientas/globos_reales.py
```

It opens a window, it needs a screen and it takes about fifteen seconds. It
exits with 1 if it finds any problem, and lists them in Spanish.

### Why it exists

Nothing in the suite executes the interface's JavaScript: the tests in
`tests/app/` read `info.js` as text and check its shape, never run it. That
covers a lot, but not whether the help bubble actually shows up on screen,
next to its icon, without being clipped against the window's edge. The
feature went through four rounds of hardening those text-level tests and
none of them could prove the bubble ever appeared for real: someone had to
open the window by hand and look. This tool automates that look with
`evaluate_js`, which is the only thing in this project able to run that
code.

It checks that the ten icons exist, measure 16x16 and are reachable with
Tab; that a bubble opens to the right of its icon with the right text; that
opening another one closes the previous one and clears its ARIA; that the
same icon, a click outside, Escape or scrolling the panel close it; that
Escape also returns focus; that the Resolución bubble is not clipped by the
bottom edge with the panel scrolled all the way down, nor the Material one
by the right edge in the 960x640 minimum window; and that the mirrored-parts
icon opens its bubble without toggling the checkbox.

### When to reach for it

After touching `info.js`, the `.boton-info` markup in the HTML, or the
`.globo-info` CSS.

### WKWebView's late `scroll` event

Assigning `scrollTop` from script makes WKWebView dispatch the `scroll`
event asynchronously, with a delay that has been measured at close to a
second. A check that scrolls the panel and clicks right away can receive
that `scroll` only after the click, and since any scroll closes the bubble
according to `info.js`, the click that had just opened it sees it closed: a
race in the tool, not a bug in the interface. `esperar_quietud` waits for
the count of `scroll`/`resize` events to stop moving instead of sleeping a
fixed amount of time, so it does not depend on guessing how long that delay
will be.

### Its own judgement is tested

The part that makes the judgement (`problemas_de_inventario`,
`problemas_de_apertura`, `problemas_de_cierre`, `problemas_de_escape`,
`problemas_de_encuadre`, `problemas_de_contenido` and `problemas_de_casilla`)
is pure and lives in `tests/test_herramienta_globos_reales.py`, with numbers
measured in real runs of the tool.

## `icono.py`

Draws the program's icon and generates everything made from it.

```bash
.venv/bin/python herramientas/icono.py            # regenerates every file
.venv/bin/python herramientas/icono.py comparar   # shows it over several backgrounds
```

It leaves `packaging/icono.ico` (Windows), `packaging/icono.icns` (macOS),
`src/nesting_app/web/icono.png` (the browser tab) and
`docs/imagenes/icono.png` (the 1024 master).

The icon is drawn with code and not just stored as a binary: an `.ico` cannot
be corrected or understood by looking at it, and this one has three colours and
a composition that somebody is going to want to adjust some day.

**They are two drawings, not one.** At 16 and 32 px the five parts of the large
version turn into blocks of two or three pixels separated by grooves narrower
than one: mush. For those sizes there is a three-part composition, with the
same idea and the same palette. Every size in the `.ico` is **drawn**, not
rescaled from the large one, which is the only way for the small ones to use
the simplified version.

`icono.icns` needs `iconutil`, which is macOS only; on another platform it is
skipped and says so.
