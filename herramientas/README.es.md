# Herramientas de diagnóstico

*[English](README.md)*

Cosas que se corren a mano, no en la suite.

## `ventana_real.py`

Maneja la ventana de escritorio de verdad desde afuera y revisa dos cosas que
no se pueden ver de ninguna otra forma.

```bash
.venv/bin/python herramientas/ventana_real.py            # las dos revisiones
.venv/bin/python herramientas/ventana_real.py layout
.venv/bin/python herramientas/ventana_real.py cierre
```

Abre una ventana, necesita una pantalla y tarda unos diez segundos. Sale con
1 si encuentra algún problema, y los lista en castellano.

### Por qué existe

Esta interfaz tiene una clase de defecto que no se ve leyendo el código ni
corriendo la página en un navegador. Vive en el hilo principal de Cocoa: es
donde WKWebView dibuja, y donde pywebview ejecuta los handlers que necesitan
devolver un valor. Tres bugs reales salieron de acá, y los tres habían pasado
antes por revisión de código y por el navegador:

- **La barra de acción se estiraba a toda la altura.** Sin `grid-row`
  explícito, la fila que le toca a cada hijo depende de cuántos hermanos estén
  ocultos, y la pantalla de materiales oculta justo al del medio. Queda tapada
  y no se ve; al volver, WKWebView no re-ubica y la pantalla principal queda en
  0 px hasta que un resize fuerza el recálculo.
- **Cerrar con un acomodo sin guardar colgaba el programa para siempre.** El
  handler de `closing` corre en el hilo principal, y el diálogo que abría
  encola su dibujo en ese mismo hilo y después lo espera.
- **La revisión ampliada estiraba la columna de la grilla** en vez de
  scrollear.

### Cuándo agarrarla

Cuando algo se ve o se comporta distinto en la ventana que en el navegador,
cuando aparece un cuelgue al cerrar o al abrir un diálogo, o después de tocar
`desktop.py`, el layout de `app.css` o el cambio entre pantallas.

### Cómo revisa el cierre

El diálogo de verdad esperaría a una persona, así que lo reemplaza por uno que
imita su forma exacta —`AppHelper.callAfter` para dibujar, más un semáforo para
esperar la respuesta— y lo contesta solo. Esa forma es justamente la que
colgaba. El cierre se dispara con `AppHelper.callAfter`, o sea en el hilo
principal: llamarlo desde el hilo del guion no reproduciría nada, porque el
bug es precisamente que el handler corre en el principal.

La revisión de cierre es sólo para macOS; en otra plataforma se saltea y lo
dice.

### Su propio criterio está probado

Una herramienta de diagnóstico que dejó de detectar cosas se ve igual que una
que no encuentra problemas. La parte con criterio (`problemas_de_medida`) es
aritmética pura y vive en `tests/test_herramienta_ventana_real.py`, con los
números que midió en la ventana real antes y después de cada arreglo.

## `globos_reales.py`

Ejercita los globos de ayuda de las opciones (`src/nesting_app/web/info.js`)
en la ventana de escritorio de verdad, manejándolos desde afuera.

```bash
.venv/bin/python herramientas/globos_reales.py
```

Abre una ventana, necesita una pantalla y tarda unos quince segundos. Sale
con 1 si encuentra algún problema, y los lista en castellano.

### Por qué existe

Nada en la suite ejecuta el JavaScript de la interfaz: los tests de
`tests/app/` leen `info.js` como texto y revisan su forma, nunca lo corren.
Eso alcanza para muchas cosas, pero no para saber si el globo de ayuda
realmente aparece en pantalla, al lado de su ícono y sin recortarse contra
el borde de la ventana. La funcionalidad pasó por cuatro rondas de
endurecimiento de esos tests de texto y en ninguna se pudo demostrar que el
globo se viera de verdad: hacía falta abrir la ventana a mano y mirar. Esta
herramienta automatiza esa mirada con `evaluate_js`, que es lo único en este
proyecto capaz de ejecutar ese código.

Revisa que los diez íconos existan, midan 16x16 y se lleguen con Tab; que un
globo abra a la derecha de su ícono con el texto que le toca; que abrir otro
cierre el anterior y limpie su ARIA; que el mismo ícono, un clic afuera, un
Escape o scrollear el panel lo cierren; que Escape además devuelva el foco;
que el globo de Resolución no se corte contra el borde de abajo con el panel
scrolleado del todo, ni el de Material contra la derecha en la ventana
mínima de 960x640; y que el ícono de piezas espejadas abra su globo sin dar
vuelta la casilla.

### Cuándo agarrarla

Después de tocar `info.js`, el marcado de `.boton-info` en el HTML, o el CSS
de `.globo-info`.

### El evento `scroll` tardío de WKWebView

Asignar `scrollTop` por script hace que WKWebView despache el `scroll` de
forma asíncrona, con una demora que llegó a medirse en casi un segundo. Una
revisión que scrollea el panel y hace clic enseguida puede recibir ese
`scroll` recién después del clic, y como cualquier scroll cierra el globo
según `info.js`, el clic que acababa de abrirlo lo ve cerrado: una carrera
de la herramienta, no un bug de la interfaz. `esperar_quietud` espera a que
la cuenta de eventos `scroll`/`resize` deje de moverse en vez de dormir un
tiempo fijo, así no depende de adivinar cuánto tarda esa demora.

### Su propio criterio está probado

La parte con criterio (`problemas_de_inventario`, `problemas_de_apertura`,
`problemas_de_cierre`, `problemas_de_escape`, `problemas_de_encuadre`,
`problemas_de_contenido` y `problemas_de_casilla`) es pura y vive en
`tests/test_herramienta_globos_reales.py`, con números que se midieron en
corridas reales de la herramienta.

## `icono.py`

Dibuja el ícono del programa y genera todo lo que se hace con él.

```bash
.venv/bin/python herramientas/icono.py            # regenera todos los archivos
.venv/bin/python herramientas/icono.py comparar   # lo muestra sobre varios fondos
```

Deja `packaging/icono.ico` (Windows), `packaging/icono.icns` (macOS),
`src/nesting_app/web/icono.png` (la pestaña del navegador) y
`docs/imagenes/icono.png` (el maestro a 1024).

El ícono se dibuja con código y no se guarda sólo como binario: un `.ico` no
se puede corregir ni entender mirándolo, y éste tiene tres colores y una
composición que alguna vez van a querer ajustarse.

**Son dos dibujos, no uno.** A 16 y 32 px las cinco piezas de la versión
grande quedan en bloques de dos o tres píxeles separados por ranuras de menos
de uno: puré. Para esos tamaños hay una composición de tres piezas, con la
misma idea y la misma paleta. Cada tamaño del `.ico` va **dibujado**, no
reescalado desde el grande, que es la única forma de que los chicos usen la
versión simplificada.

`icono.icns` necesita `iconutil`, que es de macOS; en otra plataforma se
saltea diciéndolo.
