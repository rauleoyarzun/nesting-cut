"""Ejercita los globos de ayuda en la ventana de escritorio de verdad.

    .venv/bin/python herramientas/globos_reales.py

NO es un test y no corre en la suite: abre una ventana, necesita una
pantalla y tarda unos quince segundos.

Por qué existe
--------------
El globo de ayuda de cada opción (`src/nesting_app/web/info.js`) es puro
DOM: se abre con un `click`, se ubica con `getBoundingClientRect` y se
cierra con `scroll`, `resize` o Escape. Nada en la suite ejecuta ese
JavaScript -- los tests de `tests/app/` leen `info.js` como texto y
verifican su forma, nunca lo corren -- así que ninguno puede probar que el
globo realmente aparece en pantalla, en el lugar que le toca, sin recortarse
contra el borde de la ventana. La funcionalidad pasó por cuatro rondas de
endurecimiento de esos tests de texto y en ninguna se pudo demostrar que el
globo se viera de verdad: hacía falta abrir la ventana a mano y mirar.

Esta herramienta automatiza esa mirada manejando la ventana real desde
afuera con `evaluate_js`, que es lo único en este proyecto capaz de
ejecutar el JavaScript de la interfaz.

Cuándo agarrarla
----------------
Después de tocar `info.js`, el marcado de `.boton-info` en el HTML, o el
CSS de `.globo-info`.

La revisión devuelve una lista de problemas en castellano y el programa
sale con 1 si encontró alguno.
"""

import json
import threading
import time

import webview

from nesting_app import desktop, rutas
from nesting_app.archivos import Deposito
from nesting_app.jobs import Registro

CLAVES = ["archivo", "material", "sep", "borde", "copias", "esfuerzo",
          "angulos", "tol-cierre", "resolucion", "espejo"]
"""Una por opción, igual al `data-info` de su botón. `info.js` tiene la
misma lista escrita a mano; si alguna vez difieren es una señal de que se
agregó una opción sin su globo, o al revés."""

PRELUDIO = """
window.__p = {
  boton: (k) => document.querySelector(`.boton-info[data-info="${k}"]`),
  globo: () => document.getElementById("globo-info"),
  caja: (e) => { if (!e) return null; const b = e.getBoundingClientRect();
    return {x: Math.round(b.left), y: Math.round(b.top),
            w: Math.round(b.width), h: Math.round(b.height),
            der: Math.round(b.right), aba: Math.round(b.bottom)};
  },
  visible: (e) => { if (!e) return false; const b = e.getBoundingClientRect();
    return b.width > 0 && b.height > 0 &&
           getComputedStyle(e).visibility !== "hidden"; },
  panel: () => document.querySelector(".panel-opciones"),
};
"""


# --- la parte con criterio, separada de la ventana para poder probarla ---
#
# Cada función toma lo que se midió en la página (un diccionario de forma
# fija, ver `estado()` más abajo) y devuelve una lista de problemas en
# castellano. No tocan `webview` ni `evaluate_js`: por eso las prueba
# `tests/test_herramienta_globos_reales.py` sin abrir ninguna ventana.

def problemas_de_inventario(iconos: list[dict]) -> list[str]:
    """Comportamiento 1: los diez íconos existen, en el orden de `CLAVES`,
    miden 16x16 como el resto de los íconos de la interfaz, y son
    `<button>` a los que se llega con Tab."""
    fallas = []
    claves = [i["clave"] for i in iconos]
    if claves != CLAVES:
        fallas.append(f"los íconos no son los diez esperados, en este orden: {claves}")
    if any(i["caja"] is None for i in iconos):
        fallas.append("algún botón de información no tiene un <svg> adentro para medir")
    else:
        tamanos = {(i["caja"]["w"], i["caja"]["h"]) for i in iconos}
        if tamanos != {(16, 16)}:
            fallas.append(f"los íconos no miden todos 16x16: {sorted(tamanos)}")
    if not all(i["tipo"] == "BUTTON" and i["enfocable"] for i in iconos):
        fallas.append("algún ícono de información no es un <button> al que se llegue con Tab")
    return fallas


def problemas_de_contenido(m: dict, etiqueta: str) -> list[str]:
    """Que el globo de `etiqueta` esté de verdad abierto y con texto adentro.

    Sin esto, un globo invisible o vacío pasaría cualquier revisión de
    encuadre sin que nadie se diera cuenta: un rectángulo de 0x0 en la
    esquina "entra" en cualquier ventana."""
    if not m["visible"] or not m["texto"].strip():
        return [f"el globo de {etiqueta} está vacío o no se ve"]
    return []


def problemas_de_apertura(m: dict, etiqueta: str, clave: str, texto_esperado: str,
                           boton_der: int | None = None) -> list[str]:
    """Comportamientos 2 y 3: un clic en el ícono de `etiqueta` abre su
    globo, con su texto, y deja el ARIA (`aria-expanded`, `aria-describedby`)
    puesto sólo en ese ícono -- nunca en el que estaba abierto antes.

    `boton_der` es el borde derecho del ícono en píxeles; si se lo pasa,
    también se revisa que el globo haya salido a la derecha de él (así se
    ubica cuando hay lugar, según `ubicar()` en `info.js`)."""
    fallas = list(problemas_de_contenido(m, etiqueta))
    if m["visible"]:
        if boton_der is not None and m["caja"]["x"] < boton_der:
            fallas.append(
                f"el globo de {etiqueta} no salió a la derecha de su ícono "
                f"({m['caja']['x']} < {boton_der})"
            )
        if texto_esperado not in m["texto"]:
            fallas.append(f"el texto no es el de {etiqueta}: {m['texto'][:60]!r}")
    if m["abiertos"] != [clave]:
        fallas.append(f"quedó abierto {m['abiertos']} en vez de sólo {clave!r}")
    if m["describedby"] != [clave]:
        fallas.append(f"aria-describedby quedó en {m['describedby']} en vez de sólo {clave!r}")
    return fallas


def problemas_de_cierre(m: dict, accion: str) -> list[str]:
    """Comportamientos 4, 5 y 8: después de `accion` (el mismo ícono, un
    clic afuera, o scrollear el panel) no debería quedar ningún globo
    abierto ni ningún resto de ARIA en ningún ícono."""
    fallas = []
    if m["visible"]:
        fallas.append(f"{accion} no cerró el globo: sigue visible")
    if m["abiertos"]:
        fallas.append(f"{accion}: quedó {m['abiertos']} con aria-expanded en \"true\"")
    if m["describedby"]:
        fallas.append(f"{accion}: quedó {m['describedby']} con aria-describedby puesto")
    return fallas


def problemas_de_escape(m: dict, foco_antes: bool, foco_volvio: bool) -> list[str]:
    """Comportamiento 6: Escape cierra el globo, igual que cualquier otro
    cierre, y además devuelve el foco al ícono que lo tenía."""
    fallas = problemas_de_cierre(m, "Escape")
    if not foco_antes:
        fallas.append("el ícono no tenía el foco antes de apretar Escape; la revisión no probó nada")
    elif not foco_volvio:
        fallas.append("Escape cerró el globo pero el foco no volvió al ícono")
    return fallas


def problemas_de_encuadre(caja: dict, vw: int, vh: int, etiqueta: str) -> list[str]:
    """Comportamientos 7, 9 y parte del 11: el globo de `etiqueta` tiene que
    quedar entero adentro de la ventana. `ubicar()` en `info.js` lo corrige
    contra el borde derecho y el de abajo; esto es lo que comprueba que esa
    corrección funcionó, tanto con el panel scrolleado del todo (el globo de
    Resolución se recortaba contra abajo) como en la ventana mínima de
    960x640 (el de Material se recortaba contra la derecha)."""
    fallas = []
    if caja["aba"] > vh:
        fallas.append(
            f"el globo de {etiqueta} se sale por abajo: termina en {caja['aba']} px, "
            f"la ventana mide {vh} px"
        )
    if caja["der"] > vw:
        fallas.append(
            f"el globo de {etiqueta} se sale por la derecha: termina en {caja['der']} px, "
            f"la ventana mide {vw} px"
        )
    if caja["x"] < 0:
        fallas.append(f"el globo de {etiqueta} se sale por la izquierda: x={caja['x']}")
    if caja["y"] < 0:
        fallas.append(f"el globo de {etiqueta} se sale por arriba: y={caja['y']}")
    return fallas


def problemas_de_casilla(casilla: dict) -> list[str]:
    """Comportamiento 10: el ícono de información de "Permitir piezas
    espejadas" comparte fila con la casilla, y un clic mal delegado podría
    terminar dándola vuelta en vez de sólo abrir el globo."""
    if casilla["antes"] != casilla["despues"]:
        return ["el ícono de información de piezas espejadas dio vuelta la casilla"]
    return []


# --- la parte que maneja la ventana ---

def js(ventana, expr: str):
    return json.loads(ventana.evaluate_js(f"JSON.stringify((() => {{ {expr} }})())"))


def estado(ventana) -> dict:
    return js(ventana, """
      const g = window.__p.globo();
      const abiertos = [...document.querySelectorAll('.boton-info[aria-expanded="true"]')]
        .map(b => b.dataset.info);
      return {
        visible: window.__p.visible(g),
        texto: g.textContent,
        caja: window.__p.caja(g),
        abiertos,
        describedby: [...document.querySelectorAll(".boton-info[aria-describedby]")]
          .map(b => b.dataset.info),
        vw: window.innerWidth, vh: window.innerHeight,
      };
    """)


def instalar_contador_de_eventos(ventana) -> None:
    """Cuenta los `scroll` (en captura, igual que `info.js`) y los `resize`
    que le llegan a la página. `esperar_quietud` lo usa para saber cuándo ya
    no va a llegar ninguno más."""
    ventana.evaluate_js("""
      window.__cuentaEventos = 0;
      document.addEventListener("scroll", () => window.__cuentaEventos++, true);
      window.addEventListener("resize", () => window.__cuentaEventos++);
    """)


def esperar_quietud(ventana, quieto_seg: float = 0.5, tope_seg: float = 6) -> None:
    """Espera a que dejen de llegar eventos `scroll`/`resize`.

    WKWebView despacha el `scroll` de una asignación de `scrollTop` por
    script en forma asíncrona, con una demora que se midió en casi un
    segundo. Si esta herramienta scrollea el panel y hace clic enseguida,
    ese `scroll` tardío puede llegar recién DESPUÉS del clic -- y cerrar el
    globo que el clic acababa de abrir, exactamente como `info.js` cierra
    cualquier globo ante un scroll. Se diagnosticó viendo el globo con
    `left`/`top` ya escritos por `ubicar()` y la clase `oculto` puesta de
    nuevo un milisegundo después del clic: no era la interfaz la que fallaba,
    era esta revisión adelantándose a un evento que todavía estaba en
    camino.

    Por eso no alcanza con dormir un tiempo fijo -- corto un día, de sobra
    otro --: hay que esperar a que la cuenta de eventos deje de moverse
    durante un rato (`quieto_seg`) y recién ahí seguir.
    """
    limite = time.time() + tope_seg
    anterior = int(ventana.evaluate_js("window.__cuentaEventos") or 0)
    while time.time() < limite:
        time.sleep(quieto_seg)
        actual = int(ventana.evaluate_js("window.__cuentaEventos") or 0)
        if actual == anterior:
            return
        anterior = actual


def revisar(ventana) -> list[str]:
    fallas: list[str] = []

    def agregar(nuevas: list[str]) -> None:
        if nuevas:
            fallas.extend(nuevas)
            for f in nuevas:
                print(f"  MAL  {f}")
        return nuevas

    ventana.evaluate_js(PRELUDIO)
    instalar_contador_de_eventos(ventana)
    # Las opciones avanzadas están plegadas: un <details> cerrado no dibuja
    # a sus hijos, así que sin esto Ángulos, Tolerancia de cierre,
    # Resolución y espejadas no existirían todavía para el DOM.
    ventana.evaluate_js('document.getElementById("avanzadas").open = true')
    time.sleep(0.4)

    # 1. los diez íconos están, se ven y miden lo mismo
    iconos = js(ventana, """
      return [...document.querySelectorAll(".boton-info")].map(b => ({
        clave: b.dataset.info, tipo: b.tagName,
        caja: window.__p.caja(b.querySelector("svg")),
        enfocable: b.tabIndex >= 0,
      }));
    """)
    if not agregar(problemas_de_inventario(iconos)):
        print(f"  ok   están los diez íconos, 16x16 y enfocables: {', '.join(CLAVES)}")

    # 2. abre a la derecha del ícono, con el texto que le toca
    b = js(ventana, 'return window.__p.caja(window.__p.boton("sep"));')
    ventana.evaluate_js('window.__p.boton("sep").click()')
    time.sleep(0.3)
    m = estado(ventana)
    if not agregar(problemas_de_apertura(m, "Separación", "sep", "fresa", boton_der=b["der"])):
        print(f"  ok   Separación abre a la derecha de su ícono, {m['caja']['w']}x{m['caja']['h']} px")

    # 3. otro ícono cierra el anterior: nunca hay dos
    ventana.evaluate_js('window.__p.boton("borde").click()')
    time.sleep(0.3)
    m = estado(ventana)
    if not agregar(problemas_de_apertura(m, "Borde", "borde", "grampas")):
        print("  ok   Borde cierra el de Separación y limpia su ARIA: nunca hay dos")

    # 4. el mismo ícono lo cierra
    ventana.evaluate_js('window.__p.boton("borde").click()')
    time.sleep(0.3)
    m = estado(ventana)
    if not agregar(problemas_de_cierre(m, "el mismo ícono")):
        print("  ok   el mismo ícono lo cierra y deshace el ARIA")

    # 5. un clic en cualquier lado lo cierra
    ventana.evaluate_js('window.__p.boton("copias").click()')
    time.sleep(0.25)
    ventana.evaluate_js('document.querySelector(".panel-dibujo").click()')
    time.sleep(0.25)
    m = estado(ventana)
    if not agregar(problemas_de_cierre(m, "un clic afuera")):
        print("  ok   un clic afuera lo cierra")

    # 6. Escape cierra y el foco vuelve al ícono
    foco = js(ventana, """
      const b = window.__p.boton("esfuerzo");
      b.focus(); b.click();
      return {antes: document.activeElement === b};
    """)
    time.sleep(0.25)
    ventana.evaluate_js(
        'document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", bubbles: true}))')
    time.sleep(0.25)
    m = estado(ventana)
    volvio = js(ventana, 'return document.activeElement === window.__p.boton("esfuerzo");')
    if not agregar(problemas_de_escape(m, foco["antes"], volvio)):
        print("  ok   Escape cierra y devuelve el foco al ícono")

    # 7. abajo de todo, el globo de Resolución no se sale por el borde inferior
    ventana.evaluate_js('const p = window.__p.panel(); p.scrollTop = p.scrollHeight;')
    esperar_quietud(ventana)
    ventana.evaluate_js('window.__p.boton("resolucion").click()')
    time.sleep(0.3)
    m = estado(ventana)
    problemas = problemas_de_contenido(m, "Resolución") + \
        problemas_de_encuadre(m["caja"], m["vw"], m["vh"], "Resolución")
    if not agregar(problemas):
        print(f"  ok   Resolución abajo de todo entra entero (termina en {m['caja']['aba']} de {m['vh']})")

    # 8. scrollear el panel lo cierra
    ventana.evaluate_js('window.__p.panel().scrollTop -= 60;')
    esperar_quietud(ventana)
    m = estado(ventana)
    if not agregar(problemas_de_cierre(m, "scrollear el panel")):
        print("  ok   scrollear el panel lo cierra")

    # 9. en la ventana mínima, el globo de Material entra horizontalmente
    ventana.resize(960, 640)
    esperar_quietud(ventana, tope_seg=8)
    ventana.evaluate_js(PRELUDIO)
    instalar_contador_de_eventos(ventana)
    ventana.evaluate_js('window.__p.panel().scrollTop = 0;')
    esperar_quietud(ventana)
    ventana.evaluate_js('window.__p.boton("material").click()')
    time.sleep(0.3)
    m = estado(ventana)
    problemas = problemas_de_contenido(m, "Material") + \
        problemas_de_encuadre(m["caja"], m["vw"], m["vh"], "Material")
    if not agregar(problemas):
        print(f"  ok   en 960x640 Material entra (x={m['caja']['x']}..{m['caja']['der']} de {m['vw']})")
    ventana.evaluate_js('document.querySelector(".panel-dibujo").click()')
    time.sleep(0.2)

    # 10. el de espejadas abre su globo sin dar vuelta la casilla
    casilla = js(ventana, """
      document.getElementById("avanzadas").open = true;
      const c = document.getElementById("espejo");
      const antes = c.checked;
      window.__p.boton("espejo").click();
      return {antes, despues: c.checked};
    """)
    time.sleep(0.3)
    m = estado(ventana)
    problemas = problemas_de_casilla(casilla) + problemas_de_apertura(
        m, "piezas espejadas", "espejo", "guante")
    if not agregar(problemas):
        print("  ok   espejadas abre el globo sin tocar la casilla")

    # 11. los diez abren con texto adentro y ninguno se sale de la ventana
    ventana.evaluate_js('document.querySelector(".panel-dibujo").click()')
    time.sleep(0.2)
    vacios, cortados = [], []
    for clave in CLAVES:
        ventana.evaluate_js(f'window.__p.boton("{clave}").click()')
        time.sleep(0.18)
        m = estado(ventana)
        if problemas_de_contenido(m, clave):
            vacios.append(clave)
        cortados.extend(problemas_de_encuadre(m["caja"], m["vw"], m["vh"], clave))
    ventana.evaluate_js('document.querySelector(".panel-dibujo").click()')
    if vacios:
        agregar([f"globos vacíos o invisibles: {vacios}"])
    else:
        print("  ok   los diez abren con texto adentro")
    if not agregar(cortados):
        print("  ok   ninguno de los diez se sale de la ventana mínima")

    return fallas


def main() -> int:
    carpeta = rutas.carpeta_datos()
    deposito = Deposito(carpeta / "herramienta-globos-fuentes")
    deposito.limpiar()
    registro = Registro(carpeta / "herramienta-globos-trabajos")
    _, _, url = desktop.servidor(deposito, registro)

    puente = desktop.Puente()
    ventana = webview.create_window(
        "Nesting (herramienta de diagnóstico: globos)", url,
        width=1100, height=720, min_size=(960, 640), js_api=puente,
    )
    puente.ventana = ventana
    problemas: list[str] = []
    # `webview.start()` devuelve en cuanto la ventana muere, y el guion
    # todavía está imprimiendo sus últimas líneas. Sin esperarlo, el
    # resumen sale intercalado en el medio (ver `ventana_real.py`).
    termino = threading.Event()

    def guion(v):
        time.sleep(2.5)
        try:
            print("\n== los globos de ayuda ==")
            problemas.extend(revisar(v))
        except Exception as error:  # noqa: BLE001 - es una herramienta a mano
            problemas.append(f"la revisión reventó: {error!r}")
        finally:
            termino.set()
            v.destroy()

    try:
        webview.start(guion, ventana)
        termino.wait(15)
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
