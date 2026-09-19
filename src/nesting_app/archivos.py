"""La única parte del programa que sabe si corre en escritorio o en web.

En escritorio, el diálogo nativo devuelve una ruta del disco del usuario y
el archivo ya está ahí. En la web llega el contenido subido y hay que
guardarlo en algún lado. Los dos caminos terminan en un `Fuente` con un id,
y de ahí para adelante nadie vuelve a preguntar de dónde salió.

Mantener esa diferencia encerrada acá es lo que permite que la misma
interfaz y la misma API sirvan en los dos lados.
"""

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

EXTENSIONES = (".dxf", ".ai", ".3dm")
"""Lo que los lectores de `nesting.io` saben abrir.

`.cdr` no está y no va a estar: es formato binario cerrado de Corel, sin
parser libre confiable, y quedó fuera de alcance desde el diseño del motor.
"""


class FuenteDesconocidaError(KeyError):
    """No hay ninguna fuente registrada con ese id."""

    def __str__(self) -> str:
        return self.args[0] if self.args else ""


class ExtensionNoSoportadaError(ValueError):
    """El archivo no es de un formato que este programa sepa leer."""


@dataclass(frozen=True)
class Fuente:
    """Un archivo de entrada listo para leer, venga de donde venga."""

    id: str
    ruta: Path
    nombre: str
    """Cómo se llama para el usuario, que no siempre es `ruta.name`."""


def _verificar_extension(nombre: str) -> None:
    # Rechazar nombres con bytes nulos temprano: causarían ValueError al escribir
    if "\x00" in nombre:
        raise ValueError(
            f"el nombre del archivo contiene un carácter nulo y no se "
            f"puede usar: {nombre!r}. Renombrá el archivo sin ese "
            "carácter y volvé a intentar."
        )

    if Path(nombre).suffix.lower() not in EXTENSIONES:
        mensaje = (
            f"{nombre} no es un formato que este programa pueda leer. "
            f"Se aceptan {', '.join(EXTENSIONES)}."
        )
        # Solo mencionar CorelDRAW si el rechazo es específicamente por .cdr
        if Path(nombre).suffix.lower() == ".cdr":
            mensaje += " Un .cdr hay que exportarlo a DXF desde CorelDRAW primero."
        raise ExtensionNoSoportadaError(mensaje)


class Deposito:
    """Las fuentes vivas de esta corrida del programa."""

    def __init__(self, carpeta: Path) -> None:
        self.carpeta = Path(carpeta)
        self._fuentes: dict[str, Fuente] = {}

    def registrar_local(self, ruta: str | Path) -> Fuente:
        """Una ruta del disco del usuario. No se copia nada.

        El archivo ya existe donde el usuario lo tiene; duplicar medio mega
        por cada análisis no compraría nada.
        """
        ruta = Path(ruta)
        if not ruta.is_file():
            raise FileNotFoundError(f"no existe el archivo {ruta}")
        _verificar_extension(ruta.name)
        return self._registrar(ruta, ruta.name)

    def registrar_subida(self, nombre: str, datos: bytes) -> Fuente:
        """Contenido subido, que hay que guardar en algún lado.

        Cada subida va a su propia subcarpeta con nombre al azar: dos
        archivos que se llamen igual no se pisan, y el nombre que viene de
        afuera nunca se usa para elegir carpeta, sólo hoja.
        """
        _verificar_extension(nombre)
        fuente_id = uuid.uuid4().hex
        destino = self.carpeta / fuente_id
        destino.mkdir(parents=True, exist_ok=True)
        # `Path(nombre).name` descarta cualquier `..` o barra: un nombre que
        # llega de afuera no puede elegir dónde se escribe. Normalizamos
        # separadores a forward slash primero para que Path.name corte también
        # los intentos que usan backslash (plataforma Windows).
        nombre_limpio = Path(nombre.replace("\\", "/")).name
        archivo = destino / nombre_limpio
        archivo.write_bytes(datos)
        return self._registrar(archivo, nombre, fuente_id=fuente_id)

    def obtener(self, fuente_id: str) -> Fuente:
        try:
            return self._fuentes[fuente_id]
        except KeyError:
            raise FuenteDesconocidaError(
                f"no hay ningún archivo registrado con el id {fuente_id!r}; "
                "puede que el programa se haya reiniciado. Volvé a elegirlo."
            ) from None

    def limpiar(self) -> None:
        """Borra todo lo subido. Se llama al arrancar y al cerrar."""
        shutil.rmtree(self.carpeta, ignore_errors=True)
        self._fuentes.clear()

    def _registrar(self, ruta: Path, nombre: str, fuente_id: str | None = None) -> Fuente:
        fuente = Fuente(id=fuente_id or uuid.uuid4().hex, ruta=ruta, nombre=nombre)
        self._fuentes[fuente.id] = fuente
        return fuente
