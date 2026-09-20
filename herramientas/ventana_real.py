"""Mide la ventana de escritorio de verdad, manejándola desde afuera.

NO es un test y no corre en la suite: abre una ventana, necesita una pantalla
y tarda unos segundos. Se ejecuta a mano.

    python herramientas/ventana_real.py            # las dos revisiones
    python herramientas/ventana_real.py layout
    python herramientas/ventana_real.py cierre

Por qué existe
--------------
Hay una clase de defecto de esta interfaz que no se ve de ninguna otra forma:
ni leyendo el código, ni corriendo la página en un navegador. Vive en el hilo
principal de Cocoa, que es donde WKWebView dibuja y donde pywebview ejecuta
los handlers que necesitan devolver un valor. Tres bugs de verdad salieron de
acá, y los tres habían pasado antes por revisión de código y por el navegador:

- La barra de acción se estiraba a toda la altura cuando la pantalla de
  materiales ocultaba a su hermana, y al volver la pantalla principal quedaba
  en 0 px hasta que un resize forzaba el recálculo.
- Cerrar con un acomodo sin guardar colgaba el programa para siempre: el
  handler de `closing` corre en el hilo principal, y el diálogo que abría
  encola su dibujo en ese mismo hilo y después lo espera.
- La revisión ampliada estiraba la columna de la grilla en vez de scrollear.

Cuándo agarrarlo
----------------
Cuando algo se ve o se comporta distinto en la ventana que en el navegador,
cuando aparece un cuelgue al cerrar o al abrir un diálogo, o después de tocar
`desktop.py`, el layout de `app.css` o el cambio entre pantallas.

Las revisiones devuelven una lista de problemas en castellano y el programa
sale con 1 si encontró alguno.
"""

import argparse
import json
import sys
import threading
import time
from pathlib import Path

import webview

from nesting_app import desktop, rutas
from nesting_app.archivos import Deposito
from nesting_app.jobs import Registro

ALTO_ESPERADO_DE_LA_BARRA = 120
"""La barra de acción mide 76 px. Más que esto significa que se corrió a la
fila elástica de la grilla, que es el bug que se busca; el margen es para que
un salto de línea en el texto del resultado no lo dispare."""

MEDIR = """
(() => {
  const r = (s) => { const e = document.querySelector(s); if (!e) return null;
    const b = e.getBoundingClientRect();
    return {top: Math.round(b.top), h: Math.round(b.height), w: Math.round(b.width)}; };
  return JSON.stringify({
    vh: document.documentElement.clientHeight,
    vw: document.documentElement.clientWidth,
    body: r("body"),
    principal: r("#pantalla-principal"),
    barra: r(".barra-accion"),
    principal_visible:
      !document.getElementById("pantalla-principal").classList.contains("oculto"),
  });
})()
"""


def problemas_de_medida(etiqueta: str, m: dict) -> list[str]:
    """La parte con criterio, separada de la ventana para poder probarla.

    Tres invariantes, una por cada forma en que se rompió:
    el body mide lo que la ventana, la barra de acción termina justo en el
    borde de abajo, y la pantalla principal tiene alto cuando está visible.
    """
    fallas = []
    if m["body"]["h"] != m["vh"]:
        fallas.append(
            f"{etiqueta}: el body mide {m['body']['h']} px y la ventana "
            f"{m['vh']} px"
        )
    fin_de_la_barra = m["barra"]["top"] + m["barra"]["h"]
    if fin_de_la_barra != m["vh"]:
        fallas.append(
            f"{etiqueta}: la barra de acción termina en {fin_de_la_barra} px y "
            f"la ventana en {m['vh']} px"
        )
    if m["barra"]["h"] > ALTO_ESPERADO_DE_LA_BARRA:
        fallas.append(
            f"{etiqueta}: la barra de acción mide {m['barra']['h']} px de alto; "
            "se corrió a la fila elástica de la grilla"
        )
    if m["principal_visible"] and m["principal"]["h"] <= 0:
        fallas.append(
            f"{etiqueta}: la pantalla principal está visible y mide "
            f"{m['principal']['h']} px de alto"
        )
    if m["body"]["w"] != m["vw"]:
        fallas.append(
            f"{etiqueta}: el body mide {m['body']['w']} px de ancho y la "
            f"ventana {m['vw']} px"
        )
    return fallas


def revisar_layout(ventana) -> list[str]:
    """La secuencia que rompía: ir a materiales, redimensionar, volver."""
    problemas = []

    def medir(etiqueta):
        m = json.loads(ventana.evaluate_js(MEDIR))
        print(f"  {etiqueta}")
        print(f"     ventana {m['vw']}x{m['vh']}  body alto={m['body']['h']}"
              f"  principal alto={m['principal']['h']}"
              f"  barra top={m['barra']['top']} alto={m['barra']['h']}")
        problemas.extend(problemas_de_medida(etiqueta, m))

    print("\n== layout ==")
    medir("recién abierta")

    ventana.evaluate_js('document.getElementById("btn-materiales").click()')
    time.sleep(0.8)
    medir("en materiales")

    ventana.resize(980, 900)
    time.sleep(1.2)
    medir("en materiales, con la ventana redimensionada")

    ventana.evaluate_js('document.getElementById("btn-volver").click()')
    time.sleep(1.0)
    medir("de vuelta en la principal, SIN redimensionar")

    return problemas


def revisar_cierre(ventana, puente) -> list[str]:
    """Que cerrar con un acomodo sin guardar no cuelgue el hilo principal.

    El diálogo de verdad esperaría a una persona, así que se reemplaza por
    uno que imita su forma exacta -- `AppHelper.callAfter` para dibujar, más
    un semáforo para esperar la respuesta -- y se contesta solo. Esa forma es
    justamente la que colgaba: si el handler de `closing` lo llamara sin
    salirse del hilo principal, el semáforo no se libera nunca.
    """
    print("\n== cierre con un acomodo sin guardar ==")
    if sys.platform != "darwin":
        print("  se saltea: el disparo del cierre está escrito para Cocoa")
        return []

    from PyObjCTools import AppHelper
    from webview.platforms.cocoa import BrowserView

    contesto = threading.Event()
    cerro = threading.Event()

    def dialogo_con_la_forma_de_pywebview():
        listo = threading.Semaphore(0)
        AppHelper.callAfter(listo.release)
        if not listo.acquire(timeout=6):
            return False
        contesto.set()
        return True

    def cerrar():
        cerro.set()
        ventana.destroy()

    cierre = desktop.CierreSeguro(puente, dialogo_con_la_forma_de_pywebview, cerrar)
    ventana.events.closing += cierre.puede_cerrar
    puente.hay_sin_guardar = True

    volvio = threading.Event()

    def cerrar_como_cocoa():
        # La función que Cocoa llama cuando apretás la cruz roja, en el hilo
        # en que la llama. Invocarla desde acá no reproduciría nada: el bug
        # es justamente que el handler corre en el hilo principal.
        BrowserView.should_close(ventana)
        volvio.set()

    AppHelper.callAfter(cerrar_como_cocoa)

    if not volvio.wait(6):
        return [
            "cierre: el handler no devolvió. El hilo principal quedó esperando "
            "el diálogo que él mismo tiene que dibujar; la app no cierra nunca"
        ]
    print("  el handler devolvió enseguida: el hilo principal quedó libre")

    problemas = []
    if not contesto.wait(6):
        problemas.append("cierre: el diálogo nunca llegó a dibujarse")
    if not cerro.wait(6):
        problemas.append("cierre: se aceptó perder el acomodo y la ventana no cerró")
    time.sleep(1.2)
    if BrowserView.instances:
        problemas.append(
            f"cierre: quedaron {len(BrowserView.instances)} ventana(s) abiertas; "
            "`destroy()` desde otro hilo no cerró de verdad"
        )
    else:
        print("  la ventana se cerró de verdad (0 abiertas)")
    return problemas


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "revision", nargs="?", default="todo", choices=["todo", "layout", "cierre"]
    )
    args = parser.parse_args(argv)

    carpeta = rutas.carpeta_datos()
    deposito = Deposito(carpeta / "herramienta-fuentes")
    deposito.limpiar()
    registro = Registro(carpeta / "herramienta-trabajos")
    _, _, url = desktop.servidor(deposito, registro)

    puente = desktop.Puente()
    ventana = webview.create_window(
        "Nesting (herramienta de diagnóstico)", url,
        width=1100, height=720, min_size=(960, 640), js_api=puente,
    )
    puente.ventana = ventana
    problemas: list[str] = []
    # `webview.start()` devuelve en cuanto la ventana muere, y el guion
    # todavía está imprimiendo sus últimas líneas. Sin esperarlo, el resumen
    # sale intercalado en el medio.
    termino = threading.Event()

    def guion(ventana):
        time.sleep(2.5)
        try:
            if args.revision in ("todo", "layout"):
                problemas.extend(revisar_layout(ventana))
            # El cierre va último: destruye la ventana.
            if args.revision in ("todo", "cierre"):
                problemas.extend(revisar_cierre(ventana, puente))
            else:
                ventana.destroy()
        except Exception as error:  # noqa: BLE001 - es una herramienta a mano
            problemas.append(f"la revisión reventó: {error!r}")
            try:
                ventana.destroy()
            except Exception:
                pass
        finally:
            termino.set()

    try:
        webview.start(guion, ventana)
        termino.wait(10)
    finally:
        registro.cerrar()
        deposito.limpiar()
        desktop.apagar()

    print()
    if problemas:
        print(f"{len(problemas)} problema(s):")
        for p in problemas:
            print(f"  - {p}")
        return 1
    print("sin problemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
