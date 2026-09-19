"""Dónde está cada cosa, corriendo del repo o dentro de un ejecutable.

PyInstaller no reproduce la estructura de carpetas del proyecto: descomprime
los recursos declarados en una carpeta temporal y deja su ruta en
`sys._MEIPASS`. Cualquier código que llegue a un archivo del proyecto
contando niveles sobre `__file__` funciona en desarrollo y falla al
congelar -- y falla recién cuando alguien abre el programa, porque ningún
test normal corre contra un ejecutable congelado.

Todo el acceso a archivos que viajan con el programa pasa por acá.
"""

import sys
from pathlib import Path

NOMBRE_APP = "nesting"

EN_EL_REPO = {
    "materials.yaml": "materials.yaml",
    "web": "src/nesting_app/web",
}
"""Dónde vive cada recurso cuando se corre desde el repositorio.

Congelado no hace falta: PyInstaller aplana todos los recursos declarados
en la raíz de `_MEIPASS`, sin conservar la estructura del proyecto. Este
mapa existe porque en el repo NO están todos en el mismo lado -- el
catálogo está en la raíz y la interfaz adentro del paquete, que es donde
tiene que estar para que `pip install` la instale.
"""


def esta_congelado() -> bool:
    """Si estamos adentro de un ejecutable armado con PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def _raiz_del_repo() -> Path:
    # src/nesting_app/rutas.py -> src/nesting_app -> src -> la raíz del repo
    return Path(__file__).resolve().parents[2]


def _ruta_del_recurso(nombre: str) -> Path:
    if esta_congelado():
        return Path(sys._MEIPASS) / nombre  # noqa: SLF001 - así lo expone PyInstaller
    return _raiz_del_repo() / EN_EL_REPO.get(nombre, nombre)


def recurso(nombre: str) -> Path:
    """Un archivo o carpeta que viaja con el programa.

    Que falte no es un problema del usuario: es un error de empaquetado, y
    el mensaje lo nombra para que quien arme el paquete sepa qué agregar.
    """
    ruta = _ruta_del_recurso(nombre)
    if not ruta.exists():
        raise FileNotFoundError(
            f"falta el recurso {nombre!r} en {ruta}. "
            "Si esto pasa en el ejecutable, hay que agregarlo a los datos "
            "declarados en el .spec de PyInstaller."
        )
    return ruta


def _base_de_datos() -> Path:
    """La carpeta de datos del usuario que corresponde a esta plataforma."""
    if sys.platform == "win32":
        import os

        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / NOMBRE_APP
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / NOMBRE_APP
    return Path.home() / ".local" / "share" / NOMBRE_APP


def carpeta_datos() -> Path:
    """Donde el programa guarda lo que es del usuario, creada si no estaba."""
    destino = _base_de_datos()
    destino.mkdir(parents=True, exist_ok=True)
    return destino
