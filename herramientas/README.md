# Herramientas de diagnóstico

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
