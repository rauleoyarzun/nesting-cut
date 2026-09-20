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
