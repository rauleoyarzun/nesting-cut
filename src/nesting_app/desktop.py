"""Levanta el servidor local y abre la ventana.

Es el único archivo del paquete que sabe de ventanas. Sacándolo, lo que
queda es un servidor HTTP que sirve exactamente igual detrás de un dominio.
"""

import argparse
import secrets
import sys
import threading
import urllib.request
from pathlib import Path

import uvicorn

from nesting_app import rutas
from nesting_app.api import crear_app
from nesting_app.archivos import Deposito
from nesting_app.jobs import Registro

_servidor: uvicorn.Server | None = None
_hilo: threading.Thread | None = None


def falta_webview2() -> bool:
    """Si en Windows falta el runtime de WebView2.

    Sin él la ventana abre en blanco y el usuario no tiene forma de adivinar
    qué pasó. Windows 11 lo trae siempre y Windows 10 casi siempre, pero
    'casi' no sirve cuando el programa se lo mandás a otra persona.
    """
    if sys.platform != "win32":
        return False
    import winreg

    claves = [
        r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"
        r"\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        r"SOFTWARE\Microsoft\EdgeUpdate\Clients"
        r"\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    ]
    for clave in claves:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, clave) as k:
                if winreg.QueryValueEx(k, "pv")[0] not in ("", "0.0.0.0"):
                    return False
        except OSError:
            continue
    return True


class _ConToken:
    """Sirve `index.html` con el token inyectado, y el resto sin tocar.

    El token viaja en un `<meta>` y no en la URL: una URL queda en el
    historial y en cualquier `Referer` que la página mande.
    """

    def __init__(self, app, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] in ("/", "/index.html"):
            html = (rutas.recurso("web") / "index.html").read_text(encoding="utf-8")
            html = html.replace(
                "<head>",
                f'<head>\n<meta name="token" content="{self.token}">'
                f'\n<meta name="escritorio" content="1">',
                1,
            )
            cuerpo = html.encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/html; charset=utf-8"),
                    (b"content-length", str(len(cuerpo)).encode()),
                    (b"cache-control", b"no-store"),
                ],
            })
            await send({"type": "http.response.body", "body": cuerpo})
            return
        await self.app(scope, receive, send)


class Puente:
    """Lo que pywebview le expone al JavaScript: diálogos nativos.

    Guardar sólo acepta rutas que salieron de un diálogo que el usuario vio.
    Sin esa lista, el JavaScript podría armar cualquier ruta y escribir
    donde quisiera -- y el JavaScript es justamente la parte que, en la
    versión web, va a correr contra contenido que no controlamos.
    """

    def __init__(self) -> None:
        self._autorizadas: set[str] = set()
        self.ventana = None
        self.hay_sin_guardar = False
        """Si hay un DXF acomodado que todavía no se guardó a ningún lado.

        El resultado vive en una carpeta temporal que se borra al cerrar. Sin
        este aviso, cerrar la ventana tira media hora de acomodo sin decir
        una palabra.
        """

    def marcar_sin_guardar(self, valor: bool) -> None:
        self.hay_sin_guardar = bool(valor)

    def _clave(self, destino: str) -> str:
        """Identifica un destino por dónde vive, sin seguir su último tramo.

        `Path.resolve()` a secas sigue un enlace simbólico si el destino
        mismo es uno: dos rutas que el usuario ve como archivos distintos
        terminarían señalando la misma clave. Acá resolvemos sólo el
        directorio contenedor (eso normaliza cosas como `..` de forma
        legítima) y dejamos el nombre final tal cual, así la clave describe
        el archivo que el usuario vio -- no a dónde apunta si es un enlace.
        """
        ruta = Path(destino)
        return str(ruta.parent.resolve() / ruta.name)

    def _autorizar(self, destino: str) -> None:
        self._autorizadas.add(self._clave(destino))

    def elegir_archivo(self) -> list[str]:
        import webview

        elegidos = self.ventana.create_file_dialog(
            # `webview.OPEN_DIALOG` sigue funcionando pero está deprecado, y
            # cada llamada imprime el aviso en la consola. En el paquete
            # armado esa consola no se ve, así que el día que pywebview lo
            # saque nos enteraríamos por un diálogo que dejó de abrir.
            webview.FileDialog.OPEN,
            allow_multiple=False,
            file_types=("Dibujos vectoriales (*.dxf;*.ai;*.3dm)",),
        )
        return list(elegidos or [])

    def elegir_destino(self, sugerido: str) -> str | None:
        import webview

        elegido = self.ventana.create_file_dialog(
            webview.FileDialog.SAVE, save_filename=sugerido
        )
        if not elegido:
            return None
        destino = elegido if isinstance(elegido, str) else elegido[0]
        self._autorizar(destino)
        return destino

    def guardar(self, destino: str, datos: list[int]) -> None:
        ruta = Path(destino)
        # Chequeo acá y no sólo en _autorizar: el enlace puede aparecer
        # recién ahora, en el momento entre elegir el destino y guardar.
        if ruta.is_symlink():
            raise PermissionError(
                "el destino elegido es un enlace simbólico a otro archivo; "
                "no se escribe a través de un enlace"
            )
        # Un hard link no es un symlink: is_symlink() da False y el chequeo
        # de arriba lo deja pasar de largo. Pero si `destino` y `victima`
        # son dos nombres del mismo inodo, escribir en uno escribe en el
        # otro -- y es peor que el symlink porque a simple vista, incluso
        # en el selector de archivos nativo, un hard link es indistinguible
        # de un archivo común. `st_nlink > 1` lo detecta. Sólo tiene
        # sentido si el archivo ya existe: si todavía no existe (el caso
        # normal al guardar) no hay inodo que consultar. En Windows no lo
        # chequeamos: `st_nlink` ahí depende de cómo se resolvió el handle
        # (comparticiones de red, ciertos puntos de reanálisis) y no es un
        # dato del que fiarse sin verificarlo en esa plataforma en
        # particular; preferimos no bloquear guardados legítimos con un
        # dato dudoso antes que dar una falsa sensación de seguridad ahí.
        if sys.platform != "win32" and ruta.exists() and ruta.stat().st_nlink > 1:
            raise PermissionError(
                "el destino elegido tiene más de un nombre apuntando al "
                "mismo archivo (hard link); escribirlo cambiaría también "
                "el otro nombre"
            )
        if self._clave(destino) not in self._autorizadas:
            raise PermissionError(
                "ese destino no salió de un diálogo de guardado"
            )
        # Residual conocido y aceptado: el patrón sigue siendo "chequear y
        # después escribir". Entre el chequeo de arriba y el write_bytes de
        # abajo queda una ventana microscópica en la que, en teoría,
        # alguien con acceso a este mismo directorio podría reemplazar
        # `destino` por un hard link. Cerrarla del todo exigiría abrir el
        # archivo con O_NOFOLLOW y escribir por descriptor en vez de por
        # ruta. No lo hacemos ahora porque la ventana que importaba de
        # verdad -- entre `elegir_destino`/`_autorizar` y `guardar`, con
        # tiempo real de por medio para que el usuario mire otra cosa -- ya
        # está cerrada por el chequeo de arriba. Esto queda anotado para
        # que no se lea como un descuido.
        ruta.write_bytes(bytes(datos))
        # Guardar es lo que resuelve el pendiente. Dejar que el JavaScript se
        # acuerde de avisarlo aparte sería una forma de olvidarse.
        self.hay_sin_guardar = False


def servidor(deposito: Deposito, registro: Registro) -> tuple[str, int, str]:
    """Arranca uvicorn en un hilo y devuelve (token, puerto, url)."""
    global _servidor, _hilo

    token = secrets.token_urlsafe(32)
    app = _ConToken(crear_app(token, deposito, registro), token)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    _servidor = uvicorn.Server(config)
    _hilo = threading.Thread(target=_servidor.run, daemon=True)
    _hilo.start()

    while not _servidor.started:
        if not _hilo.is_alive():
            raise RuntimeError("el servidor local no pudo arrancar")
    # El host sale del socket real, no de una constante repetida acá: si
    # algún día el `host="127.0.0.1"` de arriba cambiara sin querer (por
    # ejemplo a "0.0.0.0"), una URL armada con el literal seguiría diciendo
    # 127.0.0.1 y el test que lo verifica pasaría igual sin haber probado
    # nada.
    host_real, puerto = _servidor.servers[0].sockets[0].getsockname()[:2]
    return token, puerto, f"http://{host_real}:{puerto}"


def apagar() -> None:
    global _servidor, _hilo
    if _servidor is not None:
        _servidor.should_exit = True
        if _hilo is not None:
            _hilo.join(timeout=5)
        _servidor = None
        _hilo = None


def _autotest() -> int:
    """Arranca todo y pide una ruta. Sale 0 si el paquete está bien armado.

    Los bugs de empaquetado -- una ruta que no resuelve, un módulo que
    PyInstaller no encontró, `materials.yaml` que no está donde el código lo
    busca -- no aparecen en ningún test normal: aparecen cuando el usuario
    abre el programa. Esto los agarra en la máquina que compila.
    """
    registro = Registro(Path(rutas.carpeta_datos()) / "autotest")
    try:
        token, _, url = servidor(Deposito(Path(rutas.carpeta_datos()) / "autotest-f"), registro)
        pedido = urllib.request.Request(
            f"{url}/api/materiales", headers={"X-Token": token}
        )
        with urllib.request.urlopen(pedido, timeout=10) as respuesta:
            if respuesta.status != 200:
                raise RuntimeError(f"la API respondió {respuesta.status}")
        urllib.request.urlopen(url, timeout=10).read()
    except Exception as error:  # noqa: BLE001 - es el punto del autotest
        print(f"autotest FALLÓ: {error}", file=sys.stderr)
        return 1
    finally:
        registro.cerrar()
        apagar()
    print("autotest ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nest-app")
    parser.add_argument(
        "--autotest", action="store_true",
        help="arranca todo, pide una ruta y sale; para verificar el ejecutable",
    )
    args = parser.parse_args(argv)

    if args.autotest:
        return _autotest()

    if falta_webview2():
        print(
            "Falta el runtime de WebView2, que es lo que dibuja la ventana.\n"
            "Se baja gratis de https://go.microsoft.com/fwlink/p/?LinkId=2124703",
            file=sys.stderr,
        )
        return 1

    import webview

    carpeta = rutas.carpeta_datos()
    deposito = Deposito(carpeta / "fuentes")
    deposito.limpiar()  # restos de una corrida anterior que terminó mal
    registro = Registro(carpeta / "trabajos")
    _, _, url = servidor(deposito, registro)

    puente = Puente()
    ventana = webview.create_window(
        "Nesting", url, width=1100, height=720, min_size=(960, 640), js_api=puente
    )
    puente.ventana = ventana

    def al_cerrar() -> bool:
        """Devolver False cancela el cierre."""
        if not puente.hay_sin_guardar:
            return True
        return ventana.create_confirmation_dialog(
            "Hay un acomodo sin guardar",
            "El DXF todavía no se guardó en ningún lado y se va a perder. "
            "¿Cerrar igual?",
        )

    ventana.events.closing += al_cerrar
    try:
        webview.start()
    finally:
        registro.cerrar()
        deposito.limpiar()
        apagar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
