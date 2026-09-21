# Un globo de ayuda por cada opción — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que cada opción del panel tenga al lado un ícono de información que abre un globo con dos o tres oraciones diciendo qué es y qué cambia si la movés.

**Architecture:** Diez botones en el HTML, cada uno con un `data-info`; un archivo nuevo `info.js` con el mapa de textos y el abrir/cerrar; un único nodo de globo que se posiciona con `position: fixed` desde el rect del botón. `app.js` no se toca.

**Tech Stack:** HTML, CSS y JavaScript a mano, sin framework. Tests en pytest que leen los archivos estáticos como texto (no corre navegador).

**Spec:** `docs/superpowers/specs/2026-09-20-info-opciones-design.es.md`

## Global Constraints

- **`app.js` no se toca.** Ni una línea. Si hace falta tocarlo, el corte está mal puesto.
- **Todo texto de cara al usuario va en español**, con tildes y eñes.
- **Nada de emojis.** El ícono es un SVG en línea con trazo. El test `test_no_hay_emojis_en_la_interfaz` ya lo prohíbe y no se relaja.
- **Ningún token de color nuevo en `app.css`.** Se usan los que ya están: `--panel`, `--borde`, `--radio`, `--sombra`, `--texto`, `--texto-2`.
- **`info.js` va entero adentro de una IIFE.** Un `<script>` clásico comparte el ámbito global: un `const` repetido es un SyntaxError que mata el archivo entero antes de registrar un handler. Ya pasó con `materiales.js` y hay un test que lo cuida.
- **Los tests que ya existen no se tocan**, salvo `test_los_dos_scripts_no_declaran_el_mismo_nombre_global`, que se generaliza a tres archivos en la Tarea 1.
- **TDD sin excepciones:** test que falla, correrlo para verlo fallar, implementación mínima, test que pasa, commit.
- **Las diez claves son exactamente estas**, y son las mismas en el HTML (`data-info`) y en `info.js`: `archivo`, `material`, `sep`, `borde`, `copias`, `esfuerzo`, `angulos`, `tol-cierre`, `resolucion`, `espejo`.

## Estado del árbol al empezar

Hay cambios sin commitear que mueven el botón del catálogo a la etiqueta del
campo Material y agregan la clase `.renglon-etiqueta`. **Este plan construye
encima de eso.** Si al empezar `git status` está limpio y el botón
`btn-materiales` está en `<header class="barra-superior">`, la Tarea 2 no
aplica como está escrita: pará y avisá antes de tocar nada.

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `src/nesting_app/web/info.js` | **Nuevo.** El mapa de textos y el comportamiento del globo. Nada de red, nada de estado de la pantalla. |
| `src/nesting_app/web/index.html` | **Modificar.** Diez botones de info, el nodo del globo, el `<script>`. |
| `src/nesting_app/web/app.css` | **Modificar.** Tres reglas nuevas: `.titulo-campo`, `.boton-info`, `.globo-info`. |
| `tests/app/test_web_estatico.py` | **Modificar.** Que los diez botones estén, sean botones de verdad y tengan `aria-label`. |
| `tests/app/test_web_javascript.py` | **Modificar.** Que las claves del HTML y las de `info.js` sean el mismo conjunto, que los textos sean sanos, y el choque de globales ahora entre tres archivos. |
| `src/nesting_app/web/app.js` | **No se toca.** |
| `packaging/` | **No se toca.** El `.spec` de PyInstaller declara la carpeta `web` entera. |

## Una decisión que refina el spec

El spec dice envolver cada etiqueta en `.renglon-etiqueta`. Al implementarlo
resultó más simple así, y es lo que este plan hace:

- Los campos **sin** acción a la derecha usan directamente
  `<div class="titulo-campo">` como hijo del `.campo`. `.campo` ya es una
  columna flex, así que un div es un renglón y no hace falta nada más.
- **Sólo Material**, que sí tiene acción a la derecha, mantiene su
  `.renglon-etiqueta` con `space-between` y le mete adentro un
  `<span class="titulo-campo">` con la etiqueta y el ícono.

Y el globo va **antes** de `<div id="cartel-unidades">` en el documento, no al
final del `<body>`. `app.css` no usa `z-index` en ninguna regla: entre
elementos posicionados el orden del documento es el que decide, así que
ponerlo ahí lo deja arriba del panel y abajo de los carteles sin agregar un
`z-index` que después haya que mantener.

---

### Task 1: El mapa de textos en `info.js`

Los diez textos, verificados, cargados por la página. Todavía no se ve nada:
no hay botones ni globo. Esta tarea entrega la copia y su red de seguridad.

**Files:**
- Create: `src/nesting_app/web/info.js`
- Modify: `src/nesting_app/web/index.html:230-231` (agregar el `<script>`)
- Test: `tests/app/test_web_javascript.py`

**Interfaces:**
- Consumes: nada.
- Produces: `src/nesting_app/web/info.js` con un objeto `const TEXTOS` en el
  ámbito de la IIFE, con las diez claves **entre comillas dobles** y los
  valores en cadena doble con las comillas internas escapadas (`\"`). Las
  tareas 2 y 3 dependen de que ese literal se pueda leer con la expresión
  regular del helper `claves_y_textos`, que esta tarea deja escrito.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/app/test_web_javascript.py`:

```python
# --- los globos de ayuda ---------------------------------------------------

CLAVES_CON_GLOBO = [
    "archivo", "material", "sep", "borde", "copias", "esfuerzo",
    "angulos", "tol-cierre", "resolucion", "espejo",
]


@pytest.fixture(scope="module")
def js_info():
    return (rutas.recurso("web") / "info.js").read_text(encoding="utf-8")


def claves_y_textos(js_info: str) -> dict[str, str]:
    """El literal `TEXTOS` de `info.js`, leído como diccionario.

    Leerlo con una expresión regular y no evaluarlo es a propósito: el test
    no necesita un intérprete de JavaScript, necesita saber qué claves hay y
    qué dice cada una. Por eso el literal tiene todas las claves entre
    comillas y un par clave/valor por línea -- es un formato que se parsea
    en cuatro líneas, y el test que sigue lo obliga a seguir siéndolo.
    """
    cuerpo = js_info[js_info.index("const TEXTOS = {"):]
    cuerpo = cuerpo[:cuerpo.index("\n};")]
    return {
        m.group(1): m.group(2).replace('\\"', '"')
        for m in re.finditer(r'^\s*"([^"]+)":\s*"((?:[^"\\]|\\.)*)"', cuerpo, re.M)
    }


def test_estan_las_diez_claves_y_ninguna_de_mas(js_info):
    assert sorted(claves_y_textos(js_info)) == sorted(CLAVES_CON_GLOBO)


@pytest.mark.parametrize("clave", CLAVES_CON_GLOBO)
def test_el_texto_del_globo_dice_algo(js_info, clave):
    assert claves_y_textos(js_info)[clave].strip()


@pytest.mark.parametrize("clave", CLAVES_CON_GLOBO)
def test_el_texto_del_globo_entra_en_un_globo(js_info, clave):
    """Son dos o tres oraciones al costado de un campo, no un párrafo. A
    partir de acá el globo empieza a taparle la pantalla al que lo abrió."""
    texto = claves_y_textos(js_info)[clave]
    assert len(texto) <= 300, f"{clave}: {len(texto)} caracteres"


def test_la_pagina_carga_info_js(html):
    assert '<script src="info.js">' in html


def test_info_js_va_entero_adentro_de_una_iife(js_info):
    """Ver el test de nombres globales de más abajo: sin la IIFE, cualquier
    nombre que `app.js` ya haya declarado mata este archivo entero."""
    assert "(() => {" in js_info and "})();" in js_info
```

- [ ] **Step 2: Correr los tests para verlos fallar**

```bash
.venv/bin/python -m pytest tests/app/test_web_javascript.py -q -k globo
```

Esperado: FAIL. Todos rompen en la fixture `js_info`, con un
`FileNotFoundError` sobre `info.js`: el archivo todavía no existe.

- [ ] **Step 3: Escribir `info.js` con el mapa**

Crear `src/nesting_app/web/info.js`:

```javascript
"use strict";

/* Los globos de ayuda de cada opción.
 *
 * El texto de estas diez opciones ya estaba en el README, que es donde nadie
 * lo lee: la duda aparece parado frente a la máquina, con el archivo abierto
 * y la placa cargada. Acá está al lado de la etiqueta.
 *
 * No comparte nada con `app.js` -- ni estado, ni red, ni el trabajo en
 * curso -- así que vive aparte. */

// Todo el archivo va adentro de una IIFE. Un <script> clásico comparte el
// ámbito global con los demás, así que declarar acá un `const` que app.js ya
// declaró es un SyntaxError que mata este archivo ENTERO antes de registrar
// un solo handler. Pasó con materiales.js.
(() => {

/* Una clave por opción, igual al `data-info` de su botón en el HTML. Los
   tests verifican que los dos conjuntos sean el mismo: un botón sin texto
   abre un globo vacío y no falla en ningún otro lado. */
const TEXTOS = {
  "archivo": "El dibujo con los contornos de las piezas. Acepta .dxf, .ai (los de texto plano) y .3dm de Rhino; .cdr no, hay que exportarlo antes.",
  "material": "La placa de la que vas a cortar: de acá salen el ancho, el alto y si hay que respetar la veta. Si te falta una medida, \"Agregar o editar\" abre el catálogo.",
  "sep": "Los milímetros mínimos que quedan entre una pieza y la de al lado. Poné al menos el diámetro de la fresa, o el corte de una se come el borde de la otra.",
  "borde": "El margen que se deja libre contra el filo de la placa. Sirve para las grampas y para que una placa astillada no arruine una pieza.",
  "copias": "Cuántas veces se repite el contenido entero del archivo. Si el archivo trae 12 piezas y ponés 3, acomoda 36.",
  "esfuerzo": "Cuántas veces intenta acomodar antes de quedarse con la mejor. Más esfuerzo nunca da un resultado peor, pero tarda más: Normal alcanza casi siempre.",
  "angulos": "Las rotaciones que puede probar en cada pieza, separadas por comas. Menos ángulos es más rápido; sumar 45 suele ganar lugar en piezas largas. Si el material respeta la veta, sólo se usan 0 y 180.",
  "tol-cierre": "Cuánto puede separarse la punta de un contorno de su principio y todavía contar como cerrado. Si te descarta piezas que a ojo están cerradas, subila.",
  "resolucion": "Cuántos milímetros mide cada píxel con el que el programa \"ve\" la placa. Más fino acomoda apenas mejor y tarda mucho más; 2 mm es buen punto.",
  "espejo": "Deja dar vuelta la pieza como un guante, no sólo rotarla. Gana lugar, pero si el material tiene una cara buena o el dibujo es asimétrico, apagalo.",
};

})();
```

- [ ] **Step 4: Cargar el archivo desde la página**

En `src/nesting_app/web/index.html`, donde hoy dice:

```html
<script src="app.js"></script>
<script src="materiales.js"></script>
```

dejar:

```html
<script src="app.js"></script>
<script src="materiales.js"></script>
<script src="info.js"></script>
```

- [ ] **Step 5: Generalizar el test de nombres globales a tres archivos**

En `tests/app/test_web_javascript.py`, reemplazar la función
`test_los_dos_scripts_no_declaran_el_mismo_nombre_global` entera por esta,
conservando el docstring que explica el bug que le dio origen:

```python
@pytest.mark.parametrize("a,b", [
    ("app", "materiales"), ("app", "info"), ("materiales", "info"),
])
def test_ningun_script_declara_un_nombre_que_otro_ya_declaro(a, b):
    """Los `<script>` clásicos comparten el ámbito global.

    Declarar en `materiales.js` un `const` que `app.js` ya declaró es un
    SyntaxError, y no falla la línea: **falla el archivo entero** antes de
    registrar un solo handler. Pasó de verdad la primera vez que se abrió la
    pantalla: `materiales.js` hacía `const { apiJson, ... } = window.__nesting`
    y `app.js` ya tenía `const apiJson`. La pantalla abría --ese botón lo
    registra app.js-- pero no andaban ni "Volver" ni "Cancelar" ni aparecía
    ningún material, y la consola de una ventana de pywebview no se puede
    abrir para ver el error.

    El arreglo fue envolver los archivos de más en una IIFE. Este test existe
    para que nadie la saque sin enterarse, y se parametriza para que sumar un
    cuarto archivo sea agregar un par acá.
    """
    leer = lambda n: (rutas.recurso("web") / f"{n}.js").read_text(encoding="utf-8")
    chocan = _declaraciones_globales(leer(a)) & _declaraciones_globales(leer(b))

    assert not chocan, (
        f"{a}.js y {b}.js declaran los mismos nombres globales: {sorted(chocan)}. "
        "Dos <script> clásicos comparten ámbito, así que eso es un SyntaxError "
        "que mata el segundo archivo entero."
    )
```

- [ ] **Step 6: Correr los tests para verlos pasar**

```bash
.venv/bin/python -m pytest tests/app/test_web_javascript.py -q
```

Esperado: PASS, sin ninguno saltado.

- [ ] **Step 7: Commit**

```bash
git add src/nesting_app/web/info.js src/nesting_app/web/index.html tests/app/test_web_javascript.py
git commit -m "Los diez textos de ayuda, en un archivo aparte"
```

---

### Task 2: Los diez íconos y el nodo del globo

Después de esta tarea los íconos se ven, se llegan con Tab y no hacen nada
todavía. El globo existe en el documento pero está oculto.

**Files:**
- Modify: `src/nesting_app/web/index.html` (diez campos, más el nodo del globo)
- Modify: `src/nesting_app/web/app.css` (dos reglas: `.titulo-campo` y `.boton-info`)
- Test: `tests/app/test_web_estatico.py`, `tests/app/test_web_javascript.py`

**Interfaces:**
- Consumes: las diez claves de la Tarea 1 (`CLAVES_CON_GLOBO`).
- Produces: en el HTML, un `<button type="button" class="boton-info" data-info="<clave>" aria-label="Qué es <Nombre>" aria-expanded="false">` por opción, y un `<div id="globo-info" class="globo-info oculto" role="tooltip"></div>` ubicado antes de `<div id="cartel-unidades">`. La Tarea 3 depende de esos nombres exactos: la clase `.boton-info`, el atributo `data-info` y el id `globo-info`.

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/app/test_web_estatico.py`, agregar `"globo-info"` al final de la
lista `IDS_OBLIGATORIOS`, y agregar al final del archivo:

```python
# --- los globos de ayuda ---------------------------------------------------

CLAVES_CON_GLOBO = [
    "archivo", "material", "sep", "borde", "copias", "esfuerzo",
    "angulos", "tol-cierre", "resolucion", "espejo",
]


@pytest.mark.parametrize("clave", CLAVES_CON_GLOBO)
def test_cada_opcion_tiene_su_boton_de_ayuda(html, clave):
    assert f'data-info="{clave}"' in html


@pytest.mark.parametrize("clave", CLAVES_CON_GLOBO)
def test_el_boton_de_ayuda_es_un_boton_y_se_anuncia(html, clave):
    """Adentro sólo hay un SVG con `aria-hidden`: sin `aria-label` un lector
    de pantalla anuncia un botón sin nombre. Y un `<span>` con onclick no
    recibe foco con Tab ni se activa con Enter."""
    etiqueta = re.search(rf'<button[^>]*data-info="{re.escape(clave)}"[^>]*>', html)
    assert etiqueta, f"el botón de {clave} no es un <button>"
    assert "aria-label=" in etiqueta.group(0), f"el botón de {clave} no tiene aria-label"
    assert 'aria-expanded="false"' in etiqueta.group(0), (
        f"el botón de {clave} arranca sin aria-expanded"
    )


def test_el_boton_de_espejadas_esta_afuera_de_su_casilla(html):
    """Un `<button>` adentro de un `<label>` hereda su clic: abrir la ayuda
    daría vuelta la casilla, que es justo lo contrario de lo que el usuario
    pidió al apretarla."""
    inicio = html.index('<label class="casilla">')
    cierre = html.index("</label>", inicio)
    assert 'data-info="espejo"' not in html[inicio:cierre], (
        "el botón de ayuda de las espejadas quedó adentro del <label>"
    )


def test_el_globo_se_dibuja_abajo_de_los_carteles(html):
    """`app.css` no usa `z-index` en ninguna regla: entre posicionados
    manda el orden del documento. Con el globo después de los carteles, uno
    abierto quedaría flotando por encima del cartel de error."""
    assert html.index('id="globo-info"') < html.index('id="cartel-unidades"')


def test_el_globo_no_atrapa_el_foco(html):
    """Es un texto de ayuda, no un diálogo: `role="tooltip"` y nada más."""
    globo = re.search(r'<div[^>]*id="globo-info"[^>]*>', html).group(0)
    assert 'role="tooltip"' in globo
```

Y en `tests/app/test_web_javascript.py`, el test que el spec llama el que
importa -- que los dos conjuntos sean el mismo. Los de arriba encuentran un
texto sin botón; éste encuentra además un botón sin texto, que abre un globo
vacío y no falla en ningún otro lado:

```python
def test_cada_boton_del_html_tiene_su_texto_y_al_reves(html, js_info):
    del_html = set(re.findall(r'data-info="([^"]+)"', html))
    del_js = set(claves_y_textos(js_info))

    assert del_html == del_js, (
        f"sólo en el HTML: {sorted(del_html - del_js)}; "
        f"sólo en info.js: {sorted(del_js - del_html)}"
    )
```

- [ ] **Step 2: Correr los tests para verlos fallar**

```bash
.venv/bin/python -m pytest tests/app/test_web_estatico.py tests/app/test_web_javascript.py -q
```

Esperado: FAIL, 23 tests rotos (los 10 + 10 parametrizados, más los tres
sueltos), todos por no encontrar el `data-info` o el `id="globo-info"`.

- [ ] **Step 3: Poner los íconos en el HTML**

El ícono es siempre el mismo marcado. En los ocho campos que tienen una
`<label class="etiqueta">` suelta —`sep`, `borde`, `copias`, `esfuerzo`,
`angulos`, `tol-cierre`, `resolucion`— y en el `<span class="etiqueta">` de
Archivo, la etiqueta pasa a ir envuelta. Así queda Separación, y los demás
son iguales cambiando la clave, el `for` y el nombre:

```html
      <div class="titulo-campo">
        <label class="etiqueta" for="sep">Separación</label>
        <button type="button" class="boton-info" data-info="sep" aria-label="Qué es Separación" aria-expanded="false"><svg viewBox="0 0 16 16" class="icono" stroke-linecap="round" aria-hidden="true"><circle cx="8" cy="8" r="6.25"></circle><path d="M8 7.5v3.5"></path><path d="M8 5v.01"></path></svg></button>
      </div>
```

Archivo, que no tiene `for` porque no hay un control único al que apuntar:

```html
      <div class="titulo-campo">
        <span class="etiqueta">Archivo</span>
        <button type="button" class="boton-info" data-info="archivo" aria-label="Qué es Archivo" aria-expanded="false"><svg viewBox="0 0 16 16" class="icono" stroke-linecap="round" aria-hidden="true"><circle cx="8" cy="8" r="6.25"></circle><path d="M8 7.5v3.5"></path><path d="M8 5v.01"></path></svg></button>
      </div>
```

Material es el único que ya tiene acción a la derecha: se le mete un
`<span class="titulo-campo">` adentro del `.renglon-etiqueta` que ya está, y
el botón del catálogo queda como segundo hijo, contra el margen:

```html
      <div class="renglon-etiqueta">
        <span class="titulo-campo">
          <label class="etiqueta" for="material">Material</label>
          <button type="button" class="boton-info" data-info="material" aria-label="Qué es Material" aria-expanded="false"><svg viewBox="0 0 16 16" class="icono" stroke-linecap="round" aria-hidden="true"><circle cx="8" cy="8" r="6.25"></circle><path d="M8 7.5v3.5"></path><path d="M8 5v.01"></path></svg></button>
        </span>
        <button type="button" id="btn-materiales" class="enlace">Agregar o editar</button>
      </div>
```

Y las espejadas, con el botón **afuera** del `<label>`:

```html
      <div class="titulo-campo">
        <label class="casilla"><input id="espejo" type="checkbox" checked> Permitir piezas espejadas</label>
        <button type="button" class="boton-info" data-info="espejo" aria-label="Qué es Permitir piezas espejadas" aria-expanded="false"><svg viewBox="0 0 16 16" class="icono" stroke-linecap="round" aria-hidden="true"><circle cx="8" cy="8" r="6.25"></circle><path d="M8 7.5v3.5"></path><path d="M8 5v.01"></path></svg></button>
      </div>
```

Los nombres de los `aria-label`, uno por uno: `Qué es Archivo`,
`Qué es Material`, `Qué es Separación`, `Qué es Borde`, `Qué es Copias`,
`Qué es Esfuerzo`, `Qué es Ángulos`, `Qué es Tolerancia de cierre`,
`Qué es Resolución`, `Qué es Permitir piezas espejadas`.

- [ ] **Step 4: Poner el nodo del globo**

Justo antes de `<div id="cartel-unidades" class="cartel oculto">`:

```html
<!-- Antes de los carteles y no al final del body: `app.css` no usa z-index
     en ninguna regla, así que entre posicionados manda el orden del
     documento. Acá el globo queda arriba del panel y abajo de los carteles,
     sin un z-index que después haya que mantener en dos lados. -->
<div id="globo-info" class="globo-info oculto" role="tooltip"></div>
```

- [ ] **Step 5: Las dos reglas de CSS**

En `src/nesting_app/web/app.css`, después de la regla `.renglon-etiqueta`
(línea 127):

```css
/* La etiqueta y su ícono de ayuda, pegados. Va como hijo directo del
   `.campo` --que ya es una columna flex-- salvo en Material, donde entra
   adentro del `.renglon-etiqueta` para que el botón del catálogo siga
   yéndose al margen. `baseline` por lo mismo que arriba: son dos cosas de
   alturas distintas y centrarlas por caja las deja corridas. */
.titulo-campo { display: flex; align-items: baseline; gap: 6px; }

/* `line-height: 0` para que la caja del botón sea la del SVG y no le sume
   el interlineado de un texto que no tiene. */
.boton-info {
  border: 0; background: none; padding: 0; line-height: 0; cursor: pointer;
}
.boton-info:hover .icono, .boton-info:focus-visible .icono { stroke: var(--texto); }
```

- [ ] **Step 6: Correr los tests para verlos pasar**

```bash
.venv/bin/python -m pytest tests/app/test_web_estatico.py tests/app/test_web_javascript.py -q
```

Esperado: PASS, incluido `test_no_hay_emojis_en_la_interfaz` y
`test_ningun_id_esta_repetido`.

- [ ] **Step 7: Commit**

```bash
git add src/nesting_app/web/index.html src/nesting_app/web/app.css tests/app/test_web_estatico.py tests/app/test_web_javascript.py
git commit -m "El ícono de ayuda al lado de cada etiqueta"
```

---

### Task 3: Abrir, ubicar y cerrar el globo

La tarea que hace que la función exista.

**Files:**
- Modify: `src/nesting_app/web/info.js`
- Modify: `src/nesting_app/web/app.css` (la regla `.globo-info`)
- Test: `tests/app/test_web_javascript.py`

**Interfaces:**
- Consumes: `.boton-info[data-info]` y `#globo-info` de la Tarea 2; `TEXTOS` de la Tarea 1.
- Produces: nada que otra tarea consuma.

- [ ] **Step 1: Escribir los tests que fallan**

Al final de `tests/app/test_web_javascript.py`, en la sección de los globos:

```python
def test_el_globo_se_cierra_de_las_cuatro_formas(js_info):
    """Un globo que sólo cierra con el mismo botón queda tapando el panel en
    cuanto el usuario sigue trabajando. Escape y el clic afuera son lo que
    todo el mundo prueba; el scroll y el resize son los que lo dejarían
    flotando lejos del campo que explica, porque está posicionado en fijo
    contra coordenadas de pantalla."""
    for señal in ('"Escape"', '"scroll"', '"resize"', '"click"'):
        assert señal in js_info, f"info.js no contempla {señal}"


def test_el_scroll_se_escucha_en_captura(js_info):
    """El que scrollea es `.panel-opciones`, no la ventana, y un evento de
    scroll de un elemento no burbujea hasta document. En captura sí pasa por
    ahí. Sin el `true` el globo se queda flotando mientras el campo se va."""
    assert re.search(r'addEventListener\(\s*"scroll".*,\s*true\s*\)', js_info), (
        "el scroll no se escucha en la fase de captura"
    )


def test_el_globo_se_ubica_contra_el_boton(js_info):
    """Si no lee el rect del botón, el globo sale siempre en el mismo lado
    de la pantalla y no se sabe de qué campo habla."""
    assert "getBoundingClientRect" in js_info


def test_el_globo_no_se_sale_de_la_ventana(js_info):
    """El panel mide 336 px y la ventana no siempre es ancha: si no se mide
    contra `innerWidth` / `innerHeight`, el globo de las opciones avanzadas
    --que están abajo de todo-- sale cortado por el borde."""
    assert "innerWidth" in js_info and "innerHeight" in js_info


def test_el_boton_anuncia_si_esta_abierto(js_info):
    """`aria-expanded` es lo único que le dice a un lector de pantalla que
    ese botón abrió algo, y `aria-describedby` es lo que hace que le lea el
    texto sin tener que ir a buscarlo."""
    assert "aria-expanded" in js_info
    assert "aria-describedby" in js_info


def test_escape_devuelve_el_foco_al_boton(js_info):
    """Si el foco se pierde, el siguiente Tab arranca del principio de la
    página y el que navega con teclado tiene que recorrer todo de nuevo."""
    assert ".focus()" in js_info
```

Y en `tests/app/test_web_estatico.py`:

```python
def test_el_globo_flota_y_no_se_recorta(css):
    """`.panel-opciones` tiene `overflow-y: auto`: un globo posicionado en
    absoluto adentro de ese panel se recorta contra el borde justo cuando el
    campo está abajo de todo -- que es donde están las avanzadas, las que más
    falta hacen."""
    globo = next(c for s, c in _reglas(css) if s == ".globo-info")
    assert "position: fixed" in globo
```

- [ ] **Step 2: Correr los tests para verlos fallar**

```bash
.venv/bin/python -m pytest tests/app -q -k "globo or scroll_se_escucha or foco"
```

Esperado: FAIL. Los de `info.js` porque el archivo sólo tiene el mapa, y el
de CSS con `StopIteration` porque la regla `.globo-info` no existe.

- [ ] **Step 3: La regla del globo en `app.css`**

Al final de `app.css`, después de la última regla:

```css
/* --- el globo de ayuda --- */
/* `fixed` y no `absolute`: `.panel-opciones` tiene `overflow-y: auto`, y un
   globo absoluto adentro se recorta contra su borde justo cuando el campo
   está abajo de todo. Las coordenadas las pone `info.js` con el rect del
   botón. */
.globo-info {
  position: fixed; max-width: 280px; padding: 12px 14px;
  background: var(--panel); border: 1px solid var(--borde);
  border-radius: var(--radio); box-shadow: var(--sombra);
  font-size: 13px; line-height: 1.45; color: var(--texto-2);
}
```

- [ ] **Step 4: El comportamiento en `info.js`**

Adentro de la IIFE, después del literal `TEXTOS` y antes del `})();`:

```javascript
const globo = document.getElementById("globo-info");

/* El botón que tiene el globo abierto, o null. Uno solo a la vez: dos
   globos abiertos se pisan y no se sabe cuál explica qué. */
let abierto = null;

const MARGEN = 8;

function ubicar(boton) {
  const b = boton.getBoundingClientRect();
  // Medirlo exige mostrarlo, y mostrarlo antes de ubicarlo lo hace
  // parpadear en la esquina. `visibility` lo deja medible e invisible.
  globo.style.visibility = "hidden";
  globo.classList.remove("oculto");
  const g = globo.getBoundingClientRect();

  // A la derecha del ícono si entra; si no, a la izquierda. En una ventana
  // angosta el panel ya se come casi todo y la derecha no alcanza.
  let x = b.right + MARGEN;
  if (x + g.width > window.innerWidth - MARGEN) x = b.left - MARGEN - g.width;
  let y = b.top;
  if (y + g.height > window.innerHeight - MARGEN) {
    y = window.innerHeight - MARGEN - g.height;
  }

  globo.style.left = `${Math.round(Math.max(MARGEN, x))}px`;
  globo.style.top = `${Math.round(Math.max(MARGEN, y))}px`;
  globo.style.visibility = "";
}

function abrir(boton) {
  const texto = TEXTOS[boton.dataset.info];
  if (!texto) return;
  globo.textContent = texto;
  ubicar(boton);
  boton.setAttribute("aria-expanded", "true");
  boton.setAttribute("aria-describedby", "globo-info");
  abierto = boton;
}

function cerrar() {
  if (!abierto) return;
  globo.classList.add("oculto");
  abierto.setAttribute("aria-expanded", "false");
  abierto.removeAttribute("aria-describedby");
  abierto = null;
}

document.addEventListener("click", (e) => {
  const boton = e.target.closest?.(".boton-info");
  // El mismo botón cierra el que tenía abierto. Sin esto, apretar dos veces
  // lo cierra y lo vuelve a abrir en el mismo gesto y parece que no hace
  // nada.
  if (boton && boton === abierto) { cerrar(); return; }
  cerrar();
  if (boton) abrir(boton);
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || !abierto) return;
  const boton = abierto;
  cerrar();
  boton.focus();
});

// En captura: el que scrollea es `.panel-opciones`, y el scroll de un
// elemento no burbujea hasta document.
document.addEventListener("scroll", cerrar, true);
window.addEventListener("resize", cerrar);
```

- [ ] **Step 5: Correr toda la suite de la interfaz**

```bash
.venv/bin/python -m pytest tests/app -q
```

Esperado: PASS, sin fallas ni errores.

- [ ] **Step 6: Commit**

```bash
git add src/nesting_app/web/info.js src/nesting_app/web/app.css tests/app/test_web_javascript.py tests/app/test_web_estatico.py
git commit -m "El globo se abre, se ubica contra su ícono y se cierra"
```

---

### Task 4: Verificarlo en la ventana de verdad

Los tests leen archivos como texto: ninguno abre un navegador, así que nada
de lo anterior probó que el globo se vea. Esta clase de defecto —algo que se
dibuja distinto en WKWebView, algo que se recorta— ya salió tres veces en
este proyecto y las tres habían pasado la revisión de código.

**Files:**
- Modify: ninguno, salvo que la verificación encuentre algo.
- Test: `herramientas/ventana_real.py`, a mano.

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: nada.

- [ ] **Step 1: Correr la suite entera**

```bash
.venv/bin/python -m pytest -q
```

Esperado: PASS. Son ~856 tests y tarda unos 4 minutos. Anotá el número que
sale: si subió respecto de 856, es por los tests nuevos de este plan.

- [ ] **Step 2: Que el layout siga sano**

```bash
.venv/bin/python herramientas/ventana_real.py layout
```

Esperado: salida sin problemas y código de salida 0. Abre una ventana y
tarda unos diez segundos; necesita una pantalla.

- [ ] **Step 3: Mirarlo con los ojos**

```bash
.venv/bin/nest-app
```

En la ventana, verificar una por una:

1. Los diez íconos están y se ven grises, del mismo tamaño que los demás.
2. Un clic en el de **Separación** abre el globo a la derecha del ícono.
3. Un clic en el de **Borde** cierra el anterior y abre el suyo: nunca hay dos.
4. Otro clic en el mismo ícono lo cierra.
5. Un clic en cualquier lado de la pantalla lo cierra.
6. Con el globo abierto, Escape lo cierra y el foco vuelve al ícono (el
   siguiente Tab sigue desde ahí).
7. Abriendo **Opciones avanzadas** y con el panel scrolleado, el globo de
   **Resolución** no sale cortado por el borde de abajo de la ventana.
8. Scrollear el panel con un globo abierto lo cierra.
9. Achicar la ventana a lo mínimo (960 × 640) y abrir el globo de
   **Material**: entra en pantalla, no se corta contra el borde derecho.
10. El ícono de **Permitir piezas espejadas** abre el globo **sin** dar
    vuelta la casilla.
11. Con Tab se llega a cada ícono y con Enter se abre el globo.

- [ ] **Step 4: Decidir qué hacer con la captura del README**

`docs/imagenes/pantalla.png` es la captura que muestran los dos README, y
ahora le faltan los íconos. **No la reemplaces por tu cuenta:** sacar esa
captura es a mano y la encuadró el usuario. Preguntale si quiere volver a
sacarla o si la deja para más adelante.

- [ ] **Step 5: Commit si hubo arreglos**

Si los pasos 2 y 3 no encontraron nada, no hay nada que commitear y la
implementación está terminada. Si encontraron algo, arreglalo con un test
que lo cubra primero, y commiteá el arreglo junto con su test.

---

## Qué queda listo y qué no

Quedan explicadas las diez opciones del panel. **No** quedan explicadas las
dos opciones de veta de la pantalla de Materiales: ya se explican solas con
un `<small>` abajo de cada una, y el spec las dejó afuera a propósito.
