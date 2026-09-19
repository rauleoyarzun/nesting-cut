"""El catálogo de materiales que el usuario puede editar.

El catálogo que trae el programa queda de sólo lectura adentro del
ejecutable, así que la copia editable vive en la carpeta de datos del
usuario. La primera vez se siembra con el original: arrancar con una lista
vacía obligaría a tipear cuatro materiales antes de poder hacer nada.
"""

from dataclasses import replace
from pathlib import Path

import yaml

from nesting.model.material import Material, load_materials
from nesting_app import rutas

VETA_LIBRE = 180.0
"""La pieza gira libre. Típico del MDF.

Por convención del catálogo, cualquier valor de 90 o más equivale a rotación
libre; 180 es el que usa el catálogo que trae el programa.
"""

VETA_RESPETAR = 5.0
"""Sólo 0 y 180 grados: corte cruzado bloqueado. Multilaminado, fenólico."""


class MaterialDuplicadoError(ValueError):
    """Ya hay un material con ese nombre."""


class MaterialDesconocidoError(KeyError):
    """No hay ningún material con ese nombre."""

    def __str__(self) -> str:
        return self.args[0] if self.args else ""


def ruta_catalogo() -> Path:
    """El catálogo editable, sembrado con el original la primera vez."""
    destino = rutas.carpeta_datos() / "materials.yaml"
    if not destino.exists():
        destino.write_text(
            rutas.recurso("materials.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    return destino


def leer() -> dict[str, Material]:
    """Lee el catálogo del usuario.

    Un YAML roto sale como `ValueError` con el nombre del archivo adentro:
    el usuario pudo haberlo editado a mano y necesita saber dónde está para
    arreglarlo, o para borrarlo y dejar que se siembre de nuevo.
    """
    ruta = ruta_catalogo()
    try:
        return load_materials(ruta)
    except ValueError as error:
        raise ValueError(
            f"el catálogo de materiales en {ruta} no se pudo leer: {error}. "
            "Se puede restaurar el catálogo original desde la pantalla de "
            "materiales."
        ) from error


def guardar(materiales: dict[str, Material]) -> None:
    """Escribe el catálogo entero. El orden alfabético lo hace diffeable."""
    crudo = {
        nombre: {
            "placa": [materiales[nombre].sheet_w, materiales[nombre].sheet_h],
            "tolerancia_veta": materiales[nombre].grain_tolerance,
        }
        for nombre in sorted(materiales)
    }
    ruta_catalogo().write_text(
        yaml.safe_dump(crudo, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def agregar(material: Material) -> None:
    materiales = leer()
    if material.name in materiales:
        raise MaterialDuplicadoError(
            f"ya existe un material llamado {material.name!r}; "
            "elegí otro nombre o editá el que está."
        )
    materiales[material.name] = material
    guardar(materiales)


def editar(nombre: str, material: Material) -> None:
    """Cambia un material, con o sin renombrarlo."""
    materiales = leer()
    if nombre not in materiales:
        raise MaterialDesconocidoError(f"no existe ningún material llamado {nombre!r}")
    if material.name != nombre and material.name in materiales:
        raise MaterialDuplicadoError(
            f"ya existe un material llamado {material.name!r}; "
            "elegí otro nombre."
        )
    del materiales[nombre]
    materiales[material.name] = material
    guardar(materiales)


def borrar(nombre: str) -> None:
    materiales = leer()
    if nombre not in materiales:
        raise MaterialDesconocidoError(f"no existe ningún material llamado {nombre!r}")
    del materiales[nombre]
    guardar(materiales)


def restaurar() -> None:
    """Vuelve al catálogo que trae el programa.

    Pisa el archivo sin leerlo: es la salida que se le ofrece al usuario
    cuando el suyo quedó ilegible, así que tiene que funcionar justamente en
    ese estado.
    """
    ruta_catalogo().write_text(
        rutas.recurso("materials.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
