"""Levanta el servidor local y abre la ventana.

Es el único archivo del paquete que sabe de ventanas. Sacándolo, lo que
queda es un servidor HTTP que sirve exactamente igual detrás de un dominio.
"""

import argparse
import multiprocessing
import os
import secrets
import sys
import threading
import traceback
import urllib.request
from pathlib import Path

import uvicorn
from starlette.datastructures import Headers

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


def _cartel(mensaje: str) -> None:
    """El cartel nativo de Windows. Aparte para poder probar `avisar`."""
    import ctypes

    MB_ICONERROR = 0x10
    ctypes.windll.user32.MessageBoxW(0, mensaje, "Nesting", MB_ICONERROR)


def avisar(mensaje: str) -> None:
    """Le pone el mensaje delante al usuario, y no en una consola que no hay.

    El .exe se arma con `console=False` -- que es lo correcto, porque si no
    queda una ventana negra detrás del programa --, y eso hace que stdout y
    stderr no vayan a ningún lado. Todo lo que este programa tiene para
    decirle al usuario antes de abrir la ventana pasa por acá: un `print` a
    secas es un doble click que no hace nada, que es peor que el error feo.

    El cartel no necesita que la ventana del programa exista, que es
    exactamente el caso en el que hace falta.
    """
    print(mensaje, file=sys.stderr)
    if sys.platform == "win32" and rutas.esta_congelado():
        _cartel(mensaje)


class VentanaNoDisponible(RuntimeError):
    """El motor nativo de la ventana no cargó. El mensaje es para el usuario."""


def desmarcar_zona_internet(carpeta: Path | None = None) -> int:
    """Le saca a las DLL del paquete la marca de "esto vino de internet".

    Windows le pone esa marca -- un flujo alternativo de NTFS llamado
    `Zone.Identifier` -- a todo archivo que sale de un .zip bajado con el
    navegador, y el Explorador se la propaga a cada cosa que descomprime.
    A Python no le importa, por eso el programa arranca igual. Pero la
    ventana la dibuja .NET, y .NET SE NIEGA a cargar un assembly marcado
    así: la carga tira FileLoadException y clr_loader, que no la ve venir,
    devuelve un puntero nulo.

    Lo que le llegó al primero que recibió el .zip fue "Failed to resolve
    Python.Runtime.Loader.Initialize", un renglón que no nombra ni la marca
    ni la forma de sacarla, en un programa que se cierra solo.

    Borrar el flujo es literalmente lo que hace `Unblock-File` de PowerShell,
    y el programa puede hacérselo a sí mismo: para cuando esto corre, el
    proceso ya está andando.

    Sólo las .dll, que son los únicos archivos que .NET va a cargar como
    assembly. Recorrer todo lo demás que trae scipy sería pagar un rato de
    arranque, en cada arranque, por nada.

    Devuelve cuántas desmarcó. Que no pueda -- una carpeta de sólo lectura,
    un antivirus -- no es motivo para no abrir: si la marca frena igual, el
    mensaje de `motor_de_ventana` explica cómo sacarla a mano.
    """
    if sys.platform != "win32":
        return 0
    # La rendija por la que el CI prueba que la marca es de verdad la causa:
    # con esto puesto el programa NO se defiende, así que el autotest sobre
    # un paquete marcado tiene que fallar. Si un día deja de fallar, es que
    # Windows o .NET cambiaron y esta función dejó de hacer falta.
    if os.environ.get("NESTING_SIN_DESMARCAR"):
        return 0
    if carpeta is None:
        if not rutas.esta_congelado():
            return 0
        carpeta = Path(sys._MEIPASS)  # noqa: SLF001 - así lo expone PyInstaller
    desmarcadas = 0
    for dll in carpeta.rglob("*.dll"):
        try:
            os.remove(f"{dll}:Zone.Identifier")
        except OSError:
            continue  # no tenía la marca, o no nos dejan escribir ahí
        desmarcadas += 1
    return desmarcadas


def _por_que_no_abre(error: Exception) -> str:
    """El mensaje que reemplaza a la traza que el usuario no puede leer."""
    detalle = f"{type(error).__name__}: {error}"
    if sys.platform != "win32":
        return f"no cargó el motor de la ventana -- {detalle}"
    return (
        "No se pudo cargar la parte de .NET que dibuja la ventana.\n"
        "\n"
        "Si bajaste el programa comprimido, lo más probable es que Windows le "
        "haya puesto a sus archivos la marca de 'esto vino de internet': .NET "
        "se niega a cargarlos así. Abrí PowerShell en la carpeta del programa "
        "y corré\n"
        "\n"
        "    Get-ChildItem -Recurse . | Unblock-File\n"
        "\n"
        f"El error de abajo fue -- {detalle}"
    )


def motor_de_ventana(inicializar=None):
    """Importa pywebview y carga el motor nativo de la plataforma.

    Es el paso donde se rompió el paquete de Windows, y el único del arranque
    que se puede ejercer sin abrir una ventana: por eso vive separado de
    `main()` y por eso el autotest lo llama. `import webview` a secas no
    alcanzaría: el backend -- y con él pythonnet, y con él .NET -- se carga
    recién en `initialize()`.

    `inicializar` es para los tests. pywebview atrapa sólo `ImportError` al
    elegir el backend, así que cualquier otra cosa que pase abajo sale por
    acá; de ahí el `except Exception` y no algo más fino.
    """
    desmarcar_zona_internet()
    import webview
    # Del módulo y no de `webview.guilib`: el paquete define `guilib = None`
    # después de importar el submódulo, así que el atributo del paquete es
    # None hasta que pywebview elige el backend.
    from webview.guilib import initialize

    try:
        (inicializar or initialize)()
    except Exception as error:  # noqa: BLE001 - ver el docstring
        raise VentanaNoDisponible(_por_que_no_abre(error)) from error
    return webview


HOSTS_LOCALES = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})
"""Los nombres con los que esta ventana se llama a sí misma."""


class _SoloDesdeEstaVentana:
    """Rechaza todo pedido cuyo `Host` no sea este servidor.

    Sin esto el programa le abre una puerta a cualquier página web que el
    usuario visite mientras lo tiene abierto. El ataque se llama DNS
    rebinding y no necesita nada raro:

    1. El usuario entra a una página cualquiera del atacante.
    2. El dominio de esa página resuelve primero al servidor del atacante y,
       segundos después, a 127.0.0.1 -- el atacante controla su propio DNS y
       pone el TTL en cero.
    3. Para el navegador la página SIGUE SIENDO el mismo origen, así que le
       deja leer las respuestas. Pero los paquetes ahora van a esta ventana.
    4. La página pide `GET /`, que devuelve el token en un `<meta>` sin pedir
       nada a cambio -- tiene que ser así, es como arranca la interfaz.
    5. Con el token encadena `POST /api/archivos/local` (que acepta CUALQUIER
       ruta del disco), `POST /api/analizar` y `GET diagnostico.png`, y se
       lleva el dibujo del usuario.

    Está reproducido de punta a punta: mandando todo con
    `Host: evil.attacker.com` se robaba el token y salía un PNG de 37 KB con
    un dibujo privado adentro.

    Lo que corta el ataque es justamente el `Host`: después del rebinding el
    navegador sigue mandando el dominio del atacante, porque para él la
    página no cambió de origen. Un pedido legítimo de la ventana dice
    127.0.0.1; uno rebindeado dice evil.attacker.com. No hay forma de que el
    atacante lo falsifique desde una página: `Host` es una cabecera prohibida
    para el JavaScript.

    Vive acá y no en `api.py` a propósito. Que el único host válido sea el
    local es verdad para la ventana de escritorio y FALSO para la versión web,
    que algún día va a estar detrás de un dominio de verdad. `api.py` es la
    capa compartida; esta regla es de esta capa.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] in ("http", "websocket") and not self._permitido(scope):
            await self._rechazar(scope, send)
            return
        await self.app(scope, receive, send)

    @staticmethod
    def _host_de(valor: bytes | None) -> str | None:
        """El nombre sin el puerto. `None` si no vino la cabecera."""
        if valor is None:
            return None
        texto = valor.decode("latin-1").strip().lower()
        if texto.startswith("["):                      # IPv6: [::1]:8080
            return texto.split("]")[0] + "]"
        return texto.rsplit(":", 1)[0] if ":" in texto else texto

    def _permitido(self, scope) -> bool:
        cabeceras = Headers(scope=scope)
        host = self._host_de(cabeceras.get("host", "").encode() or None)
        if host not in HOSTS_LOCALES:
            return False
        # Segunda cerradura: si el pedido declara un origen, tiene que ser el
        # nuestro. Un `fetch` de la propia página manda `Origin` en los POST;
        # uno de otra página declararía el suyo.
        origen = cabeceras.get("origin")
        if origen:
            sin_esquema = origen.split("://", 1)[-1]
            if self._host_de(sin_esquema.encode()) not in HOSTS_LOCALES:
                return False
        return True

    @staticmethod
    async def _rechazar(scope, send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        cuerpo = b"este servidor solo atiende a la ventana del programa"
        await send({"type": "http.response.start", "status": 403, "headers": [
            (b"content-type", b"text/plain; charset=utf-8"),
            (b"content-length", str(len(cuerpo)).encode()),
        ]})
        await send({"type": "http.response.body", "body": cuerpo})


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


def _en_hilo_aparte(funcion) -> None:
    threading.Thread(target=funcion, daemon=True).start()


class CierreSeguro:
    """Decide si la ventana puede cerrarse, y pregunta cuando hace falta.

    Preguntar parece trivial y no lo es. El handler de `closing` corre
    SINCRÓNICAMENTE en el hilo principal de Cocoa: pywebview arma ese evento
    con `should_lock=True` porque necesita su valor de retorno, así que lo
    ejecuta en el hilo que lo disparó en vez de tirarlo a uno nuevo. Y
    `create_confirmation_dialog` encola el dibujo del diálogo en el run loop
    de ese mismo hilo (`AppHelper.callAfter`) y después se queda esperando un
    semáforo.

    Preguntar desde adentro del handler cuelga el programa para siempre: el
    hilo que tiene que dibujar el diálogo es exactamente el que está
    esperando a que el diálogo conteste. Y sólo pasa cuando hay algo sin
    guardar -- o sea, después de acomodar --, que es justo como lo reportó
    el usuario.

    La salida es no preguntar ahí. El handler cancela este cierre y vuelve
    enseguida, con lo cual el hilo principal queda libre; la pregunta va a un
    hilo aparte; y si el usuario acepta, se cierra la ventana a mano.

    Está afuera de `main()` para poder probarlo. No hay forma de ver este bug
    leyendo el código ni corriendo la página en un navegador: hace falta el
    hilo principal de Cocoa, o una simulación fiel de su forma.
    """

    def __init__(self, puente, preguntar, cerrar, en_hilo=_en_hilo_aparte) -> None:
        self.puente = puente
        self._preguntar = preguntar
        self._cerrar = cerrar
        self._en_hilo = en_hilo
        self._preguntando = threading.Event()
        self._confirmado = threading.Event()

    def puede_cerrar(self) -> bool:
        """El handler de `closing`. Devolver False cancela ese cierre.

        No puede bloquear: ver la explicación de arriba.
        """
        if self._confirmado.is_set() or not self.puente.hay_sin_guardar:
            return True
        # Sin esta guarda, el segundo click de alguien impaciente abre otro
        # diálogo encima del primero.
        if not self._preguntando.is_set():
            self._preguntando.set()
            self._en_hilo(self._preguntar_y_cerrar)
        return False

    def _preguntar_y_cerrar(self) -> None:
        try:
            acepto = self._preguntar()
        except Exception:  # noqa: BLE001 - la alternativa es no poder salir
            # Si el diálogo no se pudo mostrar, lo que queda es una ventana
            # que no cierra nunca y un usuario sin forma de salir. Entre
            # perder un DXF -- que se vuelve a generar apretando Acomodar --
            # y dejar el programa trabado, se cierra.
            traceback.print_exc()
            acepto = True
        if acepto:
            self._confirmado.set()
        self._preguntando.clear()
        if acepto:
            self._cerrar()


def servidor(deposito: Deposito, registro: Registro) -> tuple[str, int, str]:
    """Arranca uvicorn en un hilo y devuelve (token, puerto, url)."""
    global _servidor, _hilo

    token = secrets.token_urlsafe(32)
    # El chequeo de `Host` va AFUERA de `_ConToken`: la página que entrega el
    # token es justamente lo que el atacante quiere leer, así que tiene que
    # quedar detrás de la cerradura, no delante.
    app = _SoloDesdeEstaVentana(_ConToken(crear_app(token, deposito, registro), token))
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


class ProcesosColgados(RuntimeError):
    """La corrida con procesos no terminó a tiempo: puede quedar trabajo en el pool."""


def _terminar_hijos(espera: float = 5.0) -> None:
    """Termina los procesos hijos que queden vivos, y los mata si no terminan.

    Hace falta para poder salir: al terminar el intérprete,
    `concurrent.futures` espera al hilo que administra el pool, y ése espera
    a los procesos que tienen trabajo en curso. Un proceso colgado cuelga la
    salida, y que el hilo que corría la cartera sea daemon no cambia nada.
    """
    hijos = multiprocessing.active_children()
    for hijo in hijos:
        hijo.terminate()
    for hijo in hijos:
        hijo.join(espera)
        if hijo.is_alive():
            hijo.kill()
            hijo.join(espera)


def _prueba_de_procesos(timeout: float = 120.0) -> None:
    """Una corrida de la cartera con dos procesos, con tiempo límite.

    Un `spawn` sin `multiprocessing.freeze_support()` anda perfecto desde el
    repo y se cuelga en el ejecutable congelado: cada proceso del pool
    vuelve a arrancar el programa entero en vez de ser un proceso del pool.
    Ningún test normal lo ve. Esto sí, en la máquina que arma el paquete.

    Tres cuadrados de 600 en una placa de 1000: uno por placa, tres placas,
    y la cota por área es dos, así que la cartera no se conforma con la base
    y manda una tanda de variantes al pool.
    """
    from nesting.engine.cartera import run_portfolio
    from nesting.engine.oracle import NestConfig
    from nesting.engine.raster.oracle import RasterOracleFactory
    from nesting.model.part import Part
    from nesting.model.sheet import Sheet, SheetSupply

    piezas = [
        Part(i, ((0.0, 0.0), (600.0, 0.0), (600.0, 600.0), (0.0, 600.0)), (), (i,))
        for i in range(3)
    ]
    config = NestConfig(sep=5.0, margin=10.0, angles=(0.0, 90.0), mirror=False,
                        resolution=5.0, effort="normal", workers=2)
    plan = SheetSupply(stock=Sheet(1000.0, 1000.0, grain_tolerance=180.0))
    salida: list = []

    def correr() -> None:
        try:
            salida.append(run_portfolio(piezas, plan, config, RasterOracleFactory()))
        except BaseException as error:  # noqa: BLE001 - se relanza abajo
            salida.append(error)

    hilo = threading.Thread(target=correr, daemon=True)
    hilo.start()
    hilo.join(timeout)
    if hilo.is_alive():
        _terminar_hijos()
        raise ProcesosColgados(
            f"la corrida con 2 procesos no terminó en {timeout:.0f} s: "
            "¿falta multiprocessing.freeze_support() al principio de main?"
        )
    if isinstance(salida[0], BaseException):
        raise salida[0]
    if salida[0].result.sheets_used != 3:
        raise RuntimeError(
            f"la corrida con 2 procesos dio {salida[0].result.sheets_used} placas "
            "y tenían que ser 3"
        )


def _autotest() -> int:
    """Arranca todo y pide una ruta. Sale 0 si el paquete está bien armado.

    Los bugs de empaquetado -- una ruta que no resuelve, un módulo que
    PyInstaller no encontró, `materials.yaml` que no está donde el código lo
    busca -- no aparecen en ningún test normal: aparecen cuando el usuario
    abre el programa. Esto los agarra en la máquina que compila.
    """
    registro = Registro(Path(rutas.carpeta_datos()) / "autotest")
    try:
        # Primero el motor de la ventana: es la parte que más se rompe al
        # empaquetar -- .NET, pythonnet, las DLL nativas de pywebview -- y no
        # necesita que el servidor esté arriba para contestar.
        motor_de_ventana()
        token, _, url = servidor(Deposito(Path(rutas.carpeta_datos()) / "autotest-f"), registro)
        pedido = urllib.request.Request(
            f"{url}/api/materiales", headers={"X-Token": token}
        )
        with urllib.request.urlopen(pedido, timeout=10) as respuesta:
            if respuesta.status != 200:
                raise RuntimeError(f"la API respondió {respuesta.status}")
        urllib.request.urlopen(url, timeout=10).read()
        # Al final y no al principio: es lo más lento del autotest (arranca
        # dos procesos), y si el paquete está roto por otra cosa conviene
        # enterarse antes.
        _prueba_de_procesos()
    except Exception as error:  # noqa: BLE001 - es el punto del autotest
        print(f"autotest FALLÓ: {error}", file=sys.stderr)
        colgada = isinstance(error, ProcesosColgados)
    else:
        colgada = None
    finally:
        registro.cerrar()
        apagar()
    if colgada is None:
        print("autotest ok")
        return 0
    if colgada:
        # Los hijos ya se terminaron (`_terminar_hijos`), pero si algo del
        # pool quedara esperando, la salida normal del intérprete se colgaría
        # y con ella `construir.sh`, que no le pone tiempo límite. Salida
        # dura, sólo en este camino: el error ya está impreso.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)
    return 1


def main(argv: list[str] | None = None) -> int:
    # Antes que nada, incluido argparse: ver `nesting.cli.main`.
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(prog="nest-app")
    parser.add_argument(
        "--autotest", action="store_true",
        help="arranca todo, pide una ruta y sale; para verificar el ejecutable",
    )
    args = parser.parse_args(argv)

    if args.autotest:
        return _autotest()

    if falta_webview2():
        avisar(
            "Falta el runtime de WebView2, que es lo que dibuja la ventana.\n"
            "Se baja gratis de https://go.microsoft.com/fwlink/p/?LinkId=2124703"
        )
        return 1

    try:
        webview = motor_de_ventana()
    except VentanaNoDisponible as error:
        avisar(str(error))
        return 1

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

    cierre = CierreSeguro(
        puente,
        preguntar=lambda: ventana.create_confirmation_dialog(
            "Hay un acomodo sin guardar",
            "El DXF todavía no se guardó en ningún lado y se va a perder. "
            "¿Cerrar igual?",
        ),
        cerrar=ventana.destroy,
    )
    ventana.events.closing += cierre.puede_cerrar
    try:
        webview.start()
    finally:
        registro.cerrar()
        deposito.limpiar()
        apagar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
