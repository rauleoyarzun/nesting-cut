# A help bubble on every option

*[Español](2026-09-20-info-opciones-design.es.md)*

Date: 2026-09-20
Status: approved

## 1. What is being built

An information icon next to the label of every option in the panel. Clicking
it opens a bubble with two or three sentences saying what that option is and
what changes if you move it.

The text already exists: it is in the options table of the README. The problem
is where it is. Nobody opens the README standing in front of the machine, and
the options that get misread the most —Esfuerzo, Tolerancia de cierre,
Resolución— are exactly the ones the name does not explain.

### Out of scope, on purpose

- **The Materials screen.** The two grain options already explain themselves
  with a `<small>` under each one. A bubble there would be repetition.
- **A tutorial, a tour or a "getting started".** This is consulted once you
  have the doubt; it does not anticipate it for you.
- **Translating the interface.** The screen is in Spanish, and so are the
  bubbles.

## 2. The decisions, and why

### 2.1 One icon per option, not a single global one

A single question mark at the top that opens the whole list is cheaper to
build and to maintain, but it forces you into a screen, to hunt your option
among ten, and back. The icon next to the label puts the explanation where
the doubt is — the same reasoning that moved the catalogue button into the
Material field.

### 2.2 It opens on click, not on hover

A bubble that appears on hover slips away when the pointer moves, does not
exist for the keyboard, and gets clipped inside a panel that scrolls. On
click the bubble stays still while it is read, and the same button works with
Tab + Enter.

It closes on another click on the icon, on a click outside, on Escape, or if
the panel scrolls. Only one is open at a time.

### 2.3 The bubble floats fixed; it does not live inside the field

`.panel-opciones` has `overflow-y: auto`. A bubble positioned absolutely
inside that panel gets clipped against the edge exactly when the field is
near the bottom — which is where the advanced options are, the ones that need
it most. It is positioned with `position: fixed` and coordinates taken from
the icon's `getBoundingClientRect()`, and it closes on scroll so it never
floats away from its field.

The alternative was unfolding the text under the field, pushing the rest
down. Nothing floats and nothing is clipped, but the panel jumps every time a
bubble opens or closes and you lose sight of what you were looking at.

### 2.4 The text lives in JavaScript, not in the HTML

A `data-info-texto` per field buries ten paragraphs in the middle of the
structure and makes the HTML unreadable. The map kept together —field key to
text— is read at a glance, corrected at a glance, and makes possible the test
that checks there are no buttons without text and no text without a button.

### 2.5 A new file, not more of `app.js`

`app.js` is 724 lines and carries the API client, job polling, zoom and the
screen's state. The bubbles share nothing with that: no state, no network, no
running job. They go in `info.js`, next to `materiales.js`, which already set
that precedent.

## 3. What it looks like

On the same line as the label, to its right, a stroked circle with an "i"
inside, grey like the secondary text:

```
Separación  (i)
┌──────────────────────────┐
│ 5                     mm │
└──────────────────────────┘
```

When the field already has an action on the right, the icon stays next to the
label and the action keeps to the margin:

```
Material  (i)          Agregar o editar
```

The icon is a stroked SVG, like every other one in the interface. No emoji:
`test_no_hay_emojis_en_la_interfaz` forbids it, and in a workshop tool a glyph
that is drawn differently on every system is out of place.

The bubble is a white box of ~280 px with the border and shadow the panels
already use, with no heading: the text is all there is.

## 4. Which option gets a bubble, and what it says

The copy ships in Spanish, which is the language of the interface. The English
column is a gloss for this document only.

| Option | The bubble says | In English |
|---|---|---|
| Archivo | El dibujo con los contornos de las piezas. Acepta `.dxf`, `.ai` (los de texto plano) y `.3dm` de Rhino; `.cdr` no, hay que exportarlo antes. | The drawing with the outlines of the parts. Takes `.dxf`, `.ai` (the plain-text ones) and Rhino's `.3dm`; `.cdr` no, export it first. |
| Material | La placa de la que vas a cortar: de acá salen el ancho, el alto y si hay que respetar la veta. Si te falta una medida, "Agregar o editar" abre el catálogo. | The sheet you are cutting from: the width, the height and whether the grain must be respected all come from here. If a size is missing, "Agregar o editar" opens the catalogue. |
| Separación | Los milímetros mínimos que quedan entre una pieza y la de al lado. Poné al menos el diámetro de la fresa, o el corte de una se come el borde de la otra. | The minimum millimetres between one part and the next. Use at least the diameter of the bit, or cutting one eats into the edge of the other. |
| Borde | El margen que se deja libre contra el filo de la placa. Sirve para las grampas y para que una placa astillada no arruine una pieza. | The margin left free against the edge of the sheet. It is for the clamps, and so a chipped edge does not ruin a part. |
| Copias | Cuántas veces se repite el contenido entero del archivo. Si el archivo trae 12 piezas y ponés 3, acomoda 36. | How many times the entire contents of the file are repeated. If the file has 12 parts and you put 3, it lays out 36. |
| Esfuerzo | Cuántas veces intenta acomodar antes de quedarse con la mejor. Más esfuerzo nunca da un resultado peor, pero tarda más: Normal alcanza casi siempre. | How many times it tries before keeping the best. More effort never gives a worse result, but it takes longer: Normal is almost always enough. |
| Ángulos | Las rotaciones que puede probar en cada pieza, separadas por comas. Menos ángulos es más rápido; sumar 45 suele ganar lugar en piezas largas. Si el material respeta la veta, sólo se usan 0 y 180. | The rotations it may try on each part, comma separated. Fewer angles is faster; adding 45 often gains room on long parts. If the material respects the grain, only 0 and 180 are used. |
| Tolerancia de cierre | Cuánto puede separarse la punta de un contorno de su principio y todavía contar como cerrado. Si te descarta piezas que a ojo están cerradas, subila. | How far the end of an outline may sit from its start and still count as closed. If it discards parts that look closed to the eye, raise it. |
| Resolución | Cuántos milímetros mide cada píxel con el que el programa "ve" la placa. Más fino acomoda apenas mejor y tarda mucho más; 2 mm es buen punto. | How many millimetres each pixel measures in the raster the program "sees" the sheet with. Finer lays out slightly better and takes much longer; 2 mm is a good spot. |
| Permitir espejadas | Deja dar vuelta la pieza como un guante, no sólo rotarla. Gana lugar, pero si el material tiene una cara buena o el dibujo es asimétrico, apagalo. | Lets a part be flipped over like a glove, not only rotated. It gains room, but if the material has a good face or the drawing is asymmetric, turn it off. |

## 5. Architecture

### 5.1 The HTML

Each field in the list gets its label wrapped in a row:

```html
<div class="renglon-etiqueta">
  <span class="titulo-campo">
    <label class="etiqueta" for="sep">Separación</label>
    <button type="button" class="boton-info" data-info="sep"
            aria-label="Qué es Separación" aria-expanded="false">
      <svg viewBox="0 0 16 16" class="icono" aria-hidden="true">...</svg>
    </button>
  </span>
</div>
```

`.renglon-etiqueta` already exists and spreads with `space-between`. With a
single child —the `.titulo-campo`— that does nothing, and in Material the
second child is still the catalogue button, which keeps to the margin as it
does today.

The bubble is a single node at the end of the `<body>`:

```html
<div id="globo-info" class="globo-info oculto" role="tooltip"></div>
```

One and not ten: `info.js` fills in the text when it opens, so there are no
ten hidden nodes to keep in sync with the map.

`Permitir piezas espejadas` is a checkbox with no `.etiqueta`: its button goes
after the checkbox text and outside the `<label>`, so clicking the icon does
not toggle the box.

### 5.2 `info.js`

A new file, on the order of forty lines, in three parts:

1. `TEXTOS`: the map from field key to the text in the table above.
2. `abrir(boton)`: fills the bubble, shows it, places it from the button's
   rect, and sets `aria-expanded="true"` and `aria-describedby` on the button.
3. `cerrar()`: hides it, undoes both attributes and, if focus was inside the
   bubble, returns it to the button.

Listeners are attached once on `document`: `click` (the button toggles,
anywhere else closes), `keydown` for Escape, and `scroll` in the capture phase
plus `resize` on the window to close.

It is placed to the right of the icon if it fits in the window, otherwise to
the left; vertically aligned to the icon and shifted up if it would run past
the bottom edge.

### 5.3 The CSS

Three new rules in `app.css`, with the tokens that are already there:

- `.titulo-campo`: flex, `align-items: baseline`, `gap: 6px`.
- `.boton-info`: a button with no background or frame, 20 px, colour
  `--texto-2`, going to `--texto` on focus or hover.
- `.globo-info`: `position: fixed`, max width 280 px, background `--panel`,
  border `--borde`, radius `--radio`, shadow `--sombra`, `z-index` above the
  panel and below the modals.

No colour token is added.

## 6. Accessibility

- The trigger is a real `<button>`: reachable with Tab, activated with Enter
  or Space.
- It carries an `aria-label` with the name of the option, because all it holds
  is an `aria-hidden` SVG.
- While the bubble is open the button carries `aria-expanded="true"` and
  `aria-describedby="globo-info"`, so a screen reader reads the text as the
  button's description.
- Escape closes it and focus returns to the button.
- The bubble is `role="tooltip"`: it does not trap focus and does not behave
  like a dialog, which is what a help text should be.

## 7. Tests

In `tests/app/test_web_estatico.py`:

- `globo-info` joins `IDS_OBLIGATORIOS`.
- Parametrised over each of the ten keys: a `data-info="<key>"` exists in the
  HTML.
- Every `data-info` in the HTML is a `<button>` and has an `aria-label`.
- The mirroring checkbox's button is outside the `<label>`, so clicking it
  does not flip the box.

In `tests/app/test_web_javascript.py` (or a `test_web_info.py` beside it):

- Every key with text in `info.js` has its button in the HTML, and every
  button in the HTML has text: the two sets are equal. This is the test that
  matters — an orphan button opens an empty bubble and fails nowhere else.
- No text runs past 300 characters. These are bubbles, not paragraphs.
- No text is empty or only whitespace.
- `info.js` handles `Escape`, the outside click and `scroll`.
- `index.html` loads `info.js`.

The emoji test that already exists covers the icon being an SVG and not a
glyph.

## 8. Changes to the code that already exists

| File | What happens to it |
|---|---|
| `src/nesting_app/web/index.html` | Ten labels get wrapped in `.titulo-campo` with their button; the bubble node and the `<script>` for `info.js` are added. |
| `src/nesting_app/web/info.js` | New. |
| `src/nesting_app/web/app.css` | Three new rules at the end of the fields section. |
| `src/nesting_app/web/app.js` | Untouched. |
| `packaging/` | Nothing: the `.spec` declares the whole `web` folder. |

The README does not change: the options table stays the long reference, and
the bubbles are the short version of the same thing.
