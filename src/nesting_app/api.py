"""Las rutas HTTP. La misma API sirve en escritorio y en la web.

El servidor escucha sólo en 127.0.0.1, pero eso no alcanza: cualquier
página abierta en el navegador del usuario también puede hablarle a
localhost. Por eso toda ruta bajo /api/ exige un token que sólo conoce la
ventana, porque se lo pasamos al cargarla.
"""

import hmac
from typing import Annotated, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from nesting.model.material import Material
from nesting_app import corredor, materials_store, rutas
from nesting_app.archivos import (
    Deposito,
    ExtensionNoSoportadaError,
    FuenteDesconocidaError,
)
from nesting_app.jobs import Registro

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


class PedidoAnalisis(BaseModel):
    fuente_id: str
    unidades: str | None = None
    tol_cierre: float = Field(default=0.1, gt=0)


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
        return {"ok": True}

    @app.put("/api/materiales/{nombre}")
    def editar_material(nombre: str, entrada: MaterialEntrada) -> dict:
        try:
            materials_store.editar(nombre, entrada.a_material())
        except materials_store.MaterialDesconocidoError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except materials_store.MaterialDuplicadoError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"ok": True}

    @app.delete("/api/materiales/{nombre}")
    def borrar_material(nombre: str) -> dict:
        try:
            materials_store.borrar(nombre)
        except materials_store.MaterialDesconocidoError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
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
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "piezas": analisis.piezas,
            "avisos": analisis.avisos,
            "descartes": analisis.descartes,
            "unidades": analisis.unidades,
        }

    _montar_interfaz(app)
    return app


def _montar_interfaz(app: FastAPI) -> None:
    """La interfaz estática, servida desde la raíz.

    Va al final para que ninguna ruta de /api/ quede tapada por el montaje.
    """
    web = rutas.recurso("web")
    app.mount("/", StaticFiles(directory=str(web), html=True), name="web")
