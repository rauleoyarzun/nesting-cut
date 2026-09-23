"""Las rutas HTTP. La misma API sirve en escritorio y en la web.

El servidor escucha sólo en 127.0.0.1, pero eso no alcanza: cualquier
página abierta en el navegador del usuario también puede hablarle a
localhost. Por eso toda ruta bajo /api/ exige un token que sólo conoce la
ventana, porque se lo pasamos al cargarla.
"""

import hmac
from typing import Annotated, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from nesting.model.material import Material
from nesting.params import NestParams, ParamsInvalidosError, Recorte, validar
from nesting_app import corredor, materials_store, rutas
from nesting_app.archivos import (
    Deposito,
    ExtensionNoSoportadaError,
    FuenteDesconocidaError,
)
from nesting_app.jobs import ERRORES_DEL_USUARIO, Registro, TrabajoDesconocidoError

VETA_POR_NOMBRE = {
    "libre": materials_store.VETA_LIBRE,
    "respetar": materials_store.VETA_RESPETAR,
}


def _nombre_de_veta(grados: float) -> str:
    """De grados a la palabra que muestra la interfaz.

    Cualquier valor de 90 o más equivale a rotación libre, por cómo se
    calcula la distancia al eje de veta. La traducción vive acá para que el
    JavaScript no tenga que saber esa regla.
    """
    return "libre" if grados >= 90 else "respetar"


class MaterialEntrada(BaseModel):
    nombre: str
    ancho: float = Field(gt=0)
    alto: float = Field(gt=0)
    veta: Literal["libre", "respetar"]

    @field_validator("nombre")
    @classmethod
    def _nombre_no_vacio(cls, valor: str) -> str:
        limpio = valor.strip()
        if not limpio:
            raise ValueError("el material necesita un nombre")
        return limpio

    def a_material(self) -> Material:
        return Material(
            name=self.nombre,
            sheet_w=self.ancho,
            sheet_h=self.alto,
            grain_tolerance=VETA_POR_NOMBRE[self.veta],
        )


class RutaLocal(BaseModel):
    ruta: str


class RecorteEntrada(BaseModel):
    ancho: float
    alto: float
    cantidad: int = 1
    veta_cruzada: bool = False

    def a_recorte(self) -> Recorte:
        return Recorte(
            ancho=self.ancho,
            alto=self.alto,
            cantidad=self.cantidad,
            veta_cruzada=self.veta_cruzada,
        )


class PedidoAnalisis(BaseModel):
    fuente_id: str
    unidades: str | None = None
    tol_cierre: float = Field(default=0.1, gt=0)


class ParamsEntrada(BaseModel):
    """Los parámetros tal como los manda la interfaz.

    Las reglas de rango NO están acá: viven en `nesting.params.validar`, que
    es el mismo código que usa la CLI. Pydantic sólo verifica que los tipos
    sean los que son.
    """

    material: str
    sep: float = 5.0
    borde: float = 10.0
    copias: int = 1
    angulos: list[float] = Field(default_factory=lambda: [0.0, 90.0, 180.0, 270.0])
    espejo: bool = True
    unidades: str | None = None
    tol_cierre: float = 0.1
    resolucion: float = 1.0
    esfuerzo: str = "normal"
    recortes: list[RecorteEntrada] = Field(default_factory=list)
    veta: Literal["respetar", "libre"] | None = None

    def a_params(self) -> NestParams:
        return NestParams(
            material=self.material,
            sep=self.sep,
            borde=self.borde,
            copias=self.copias,
            angulos=tuple(self.angulos),
            espejo=self.espejo,
            unidades=self.unidades,
            tol_cierre=self.tol_cierre,
            resolucion=self.resolucion,
            esfuerzo=self.esfuerzo,
            recortes=tuple(r.a_recorte() for r in self.recortes),
            veta=self.veta,
        )


class PedidoTrabajo(BaseModel):
    fuente_id: str
    params: ParamsEntrada


ARCHIVOS_DEL_RESULTADO = {
    "salida.dxf": "application/dxf",
    "preview.png": "image/png",
    "diagnostico.png": "image/png",
}


class _ExigirTokenEnApi:
    """Corta cualquier pedido a /api/ sin el token correcto, antes de que
    llegue a enrutarse.

    A propósito NO es una dependencia puesta ruta por ruta: una lista así
    se puede olvidar al agregar un endpoint nuevo, y ese olvido no avisa.
    Acá alcanza con que el path empiece con /api/ -- exista o no una ruta
    que lo atienda -- así que no hay nada que acordarse de actualizar.

    Y a propósito NO es un `@app.middleware("http")`: ese se implementa con
    `BaseHTTPMiddleware`, que arranca con "si el scope no es http, pasalo
    de largo sin mirarlo" -- así que deja pasar cualquier WebSocket sin
    tocarlo, token o no. Este middleware es ASGI puro: mira `scope["path"]`
    sin importar de qué tipo es el scope, así que un handshake de WebSocket
    bajo /api/ sin token se cierra igual que un pedido HTTP se rechaza con
    401. Hoy no hay ninguna ruta websocket, pero el punto de este mecanismo
    es que no haga falta acordarse cuando aparezca la primera.
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return

        recibido = Headers(scope=scope).get("x-token", "")
        # hmac.compare_digest en vez de == : acá no hay una amenaza concreta
        # (explotar la fuga de tiempo desde JavaScript contra este stack no
        # es viable en la práctica), pero comparar secretos así es gratis y
        # evita tener que volver a razonarlo cada vez.
        if not hmac.compare_digest(recibido, self.token):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                response = JSONResponse(
                    {"detail": "token inválido o ausente"}, status_code=401
                )
                await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def crear_app(token: str, deposito: Deposito, registro: Registro) -> FastAPI:
    app = FastAPI(title="nesting", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(_ExigirTokenEnApi, token=token)

    # --- materiales ---------------------------------------------------------

    @app.get("/api/materiales")
    def listar_materiales() -> dict:
        try:
            materiales = materials_store.leer()
        except ValueError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return {
            "materiales": [
                {
                    "nombre": m.name,
                    "ancho": m.sheet_w,
                    "alto": m.sheet_h,
                    "veta": _nombre_de_veta(m.grain_tolerance),
                }
                for m in sorted(materiales.values(), key=lambda m: m.name)
            ]
        }

    @app.post("/api/materiales")
    def agregar_material(entrada: MaterialEntrada) -> dict:
        try:
            materials_store.agregar(entrada.a_material())
        except materials_store.MaterialDuplicadoError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            # `agregar()` también lee el catálogo antes de escribirlo: un
            # catálogo corrupto acá tiene que dar el mismo 500 con el
            # mensaje en español (y el "se puede restaurar") que ya da
            # `GET /api/materiales`, no un "Internal Server Error" crudo.
            raise HTTPException(status_code=500, detail=str(error)) from error
        return {"ok": True}

    @app.put("/api/materiales/{nombre}")
    def editar_material(nombre: str, entrada: MaterialEntrada) -> dict:
        try:
            materials_store.editar(nombre, entrada.a_material())
        except materials_store.MaterialDesconocidoError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except materials_store.MaterialDuplicadoError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return {"ok": True}

    @app.delete("/api/materiales/{nombre}")
    def borrar_material(nombre: str) -> dict:
        try:
            materials_store.borrar(nombre)
        except materials_store.MaterialDesconocidoError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return {"ok": True}

    @app.post("/api/materiales/restaurar")
    def restaurar_materiales() -> dict:
        materials_store.restaurar()
        return {"ok": True}

    # --- archivos -----------------------------------------------------------

    @app.post("/api/archivos/local")
    def registrar_local(pedido: RutaLocal) -> dict:
        try:
            fuente = deposito.registrar_local(pedido.ruta)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ExtensionNoSoportadaError as error:
            raise HTTPException(status_code=415, detail=str(error)) from error
        return {"id": fuente.id, "nombre": fuente.nombre}

    @app.post("/api/archivos")
    async def subir_archivo(archivo: Annotated[UploadFile, File()]) -> dict:
        try:
            fuente = deposito.registrar_subida(
                archivo.filename or "sin_nombre", await archivo.read()
            )
        except ExtensionNoSoportadaError as error:
            raise HTTPException(status_code=415, detail=str(error)) from error
        return {"id": fuente.id, "nombre": fuente.nombre}

    # --- análisis -----------------------------------------------------------

    @app.post("/api/analizar")
    def analizar(pedido: PedidoAnalisis) -> dict:
        try:
            fuente = deposito.obtener(pedido.fuente_id)
        except FuenteDesconocidaError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        try:
            analisis = corredor.analizar(fuente, pedido.unidades, pedido.tol_cierre)
        except corredor.UnidadesNoDeclaradasError as error:
            # 409 y no 400: no es que el pedido esté mal armado, es que falta
            # un dato que sólo el usuario puede dar. La interfaz lo distingue
            # por la marca y muestra la pregunta con los cinco botones.
            raise HTTPException(
                status_code=409,
                detail={"faltan_unidades": True, "mensaje": str(error)},
            ) from error
        except ERRORES_DEL_USUARIO as error:
            # La misma tupla que usa `jobs._correr` para clasificar el
            # resultado de un trabajo: un contorno que no cierra, piezas que
            # se pisan, una curva no plana, etc. Antes acá sólo se atrapaba
            # `ValueError`, así que `OpenContourError`,
            # `OverlappingContourError` y `NonPlanarCurveError` (que heredan
            # de `Exception` a secas) se escapaban como 500 -- el mismo
            # archivo que por `/api/trabajos` termina bien clasificado, con
            # el mensaje en español, acá tiraba "Internal Server Error".
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "piezas": analisis.piezas,
            "avisos": analisis.avisos,
            "descartes": analisis.descartes,
            "unidades": analisis.unidades,
        }

    @app.get("/api/archivos/{fuente_id}/{nombre}")
    def bajar_del_analisis(fuente_id: str, nombre: str) -> FileResponse:
        """La revisión del análisis, que existe sin haber acomodado nada.

        `nombre` se compara contra un único valor exacto, así que no hay
        forma de que un `..` elija otro archivo; y `fuente_id` no se usa
        para armar una ruta, sino para buscar en el registro del depósito.
        """
        if nombre != corredor.NOMBRE_DIAGNOSTICO:
            raise HTTPException(status_code=404, detail=f"no existe {nombre!r}")
        try:
            fuente = deposito.obtener(fuente_id)
        except FuenteDesconocidaError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        archivo = fuente.carpeta / nombre
        if not archivo.is_file():
            # 409 y no 404: el archivo está registrado, lo que falta es el
            # análisis. La pantalla distingue ese caso y lo explica en el
            # lienzo en vez de abrir un cartel de error.
            raise HTTPException(
                status_code=409,
                detail=f"todavía no se analizó {fuente.nombre}",
            )
        return FileResponse(archivo, media_type="image/png", filename=nombre)

    # --- estimación ---------------------------------------------------------

    @app.post("/api/estimar")
    def estimar(pedido: PedidoTrabajo) -> dict:
        """Cuánto va a tardar el acomodo, antes de arrancarlo.

        Recibe exactamente lo mismo que `POST /api/trabajos`, así que todo
        parámetro nuevo de la corrida -- la veta, los recortes -- entra en la
        estimación sin tocar esta ruta. Una fuente que no existe es un
        `null` y no un 404: la pantalla pide la estimación cada vez que
        cambia una opción, y no tiene nada que mostrar en ese caso.
        """
        try:
            fuente = deposito.obtener(pedido.fuente_id)
        except FuenteDesconocidaError:
            return {"segundos": None}
        return {"segundos": corredor.estimar(fuente, pedido.params.a_params())}

    # --- trabajos -----------------------------------------------------------

    def _avance_a_dict(avance) -> dict | None:
        if avance is None:
            return None
        return {
            "intento": avance.intento,
            "intentos": avance.intentos,
            "ubicadas": avance.ubicadas,
            "totales": avance.totales,
            "placa": avance.placa,
            "compactando": avance.compactando,
            "consultas_hechas": avance.consultas_hechas,
            "consultas_previstas": avance.consultas_previstas,
            "combinaciones": avance.combinaciones,
            "combinaciones_hechas": avance.combinaciones_hechas,
            "placa_minima": avance.placa_minima,
        }

    @app.post("/api/trabajos")
    def crear_trabajo(pedido: PedidoTrabajo) -> dict:
        try:
            fuente = deposito.obtener(pedido.fuente_id)
        except FuenteDesconocidaError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        params = pedido.params.a_params()
        try:
            materiales = materials_store.leer()
        except ValueError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        material = materiales.get(params.material)

        try:
            # Con el material, si existe: es lo que deja mirar la regla de la
            # veta. Si no existe, se valida lo demás igual y el 404 sale
            # abajo, como antes -- un pedido con dos errores sigue
            # señalando primero el mismo.
            validar(params, material)
        except ParamsInvalidosError as error:
            # El campo va aparte del mensaje para que la interfaz pueda poner
            # el texto justo debajo del control que lo tiene mal.
            raise HTTPException(
                status_code=422,
                detail={
                    "campo": error.rota.campo,
                    "mensaje": f"tiene que ser {error.rota.regla}",
                    "valor": error.rota.valor,
                },
            ) from error

        if material is None:
            raise HTTPException(
                status_code=404,
                detail=f"no existe ningún material llamado {params.material!r}",
            )

        trabajo = registro.crear(fuente, params, corredor.acomodar)
        return {"id": trabajo.id}

    @app.get("/api/trabajos/{trabajo_id}")
    def ver_trabajo(trabajo_id: str) -> dict:
        try:
            trabajo = registro.obtener(trabajo_id)
        except TrabajoDesconocidoError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        resultado = None
        if trabajo.resultado is not None:
            resultado = {
                "placas": trabajo.resultado.placas,
                "aprovechamiento": trabajo.resultado.aprovechamiento,
                "total": trabajo.resultado.total,
                "segundos": trabajo.resultado.segundos,
                "sobrante_mm": trabajo.resultado.sobrante_mm,
                "material_ultima_placa_m2": trabajo.resultado.material_ultima_placa_m2,
                "recortes_usados": trabajo.resultado.recortes_usados,
            }
        return {
            "estado": str(trabajo.estado),
            "avance": _avance_a_dict(trabajo.avance),
            "restante_s": trabajo.restante_s,
            "avisos": trabajo.avisos,
            "error": trabajo.error,
            "es_bug": trabajo.es_bug,
            "detalle_tecnico": trabajo.detalle_tecnico,
            "resultado": resultado,
        }

    @app.post("/api/trabajos/{trabajo_id}/cancelar")
    def cancelar_trabajo(trabajo_id: str) -> dict:
        try:
            registro.cancelar(trabajo_id)
        except TrabajoDesconocidoError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"ok": True}

    @app.get("/api/trabajos/{trabajo_id}/{nombre}")
    def bajar_archivo(trabajo_id: str, nombre: str) -> FileResponse:
        if nombre not in ARCHIVOS_DEL_RESULTADO:
            raise HTTPException(status_code=404, detail=f"no existe {nombre!r}")
        try:
            trabajo = registro.obtener(trabajo_id)
        except TrabajoDesconocidoError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        # El diagnóstico se escribe ANTES de acomodar, así que existe aunque
        # el trabajo haya fallado -- y es justo cuando más sirve, porque el
        # usuario necesita ver qué se descartó.
        carpeta = registro.carpeta / trabajo_id
        archivo = carpeta / nombre
        if not archivo.is_file():
            raise HTTPException(
                status_code=409,
                detail=f"el trabajo está en estado {trabajo.estado} y todavía "
                       f"no produjo {nombre}",
            )
        return FileResponse(
            archivo, media_type=ARCHIVOS_DEL_RESULTADO[nombre], filename=nombre
        )

    _montar_interfaz(app)
    return app


def _montar_interfaz(app: FastAPI) -> None:
    """La interfaz estática, servida desde la raíz.

    Va al final para que ninguna ruta de /api/ quede tapada por el montaje.
    """
    web = rutas.recurso("web")
    app.mount("/", StaticFiles(directory=str(web), html=True), name="web")
