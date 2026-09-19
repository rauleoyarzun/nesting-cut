"""The material catalogue: sheet size and grain constraint, together.

Choosing a material configures both at once, because they always change
together in practice.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml


def _default_materials_path() -> Path:
    """Dónde está el catálogo que viene con el programa.

    Contar niveles sobre `__file__` funciona desde el repo y NO funciona
    dentro de un ejecutable congelado, donde PyInstaller deja los recursos
    en otro lado. `nesting_app.rutas` sabe distinguir los dos casos.

    La importación es perezosa a propósito: `nesting` no puede depender de
    `nesting_app` al importarse, o se invertiría la dependencia que sostiene
    toda la arquitectura. Acá se usa sólo si alguien pide el valor por
    omisión, y si el paquete de la interfaz no está (una instalación del
    motor a secas), se cae a la cuenta de siempre.
    """
    try:
        from nesting_app.rutas import recurso

        return recurso("materials.yaml")
    except (ImportError, FileNotFoundError):
        return Path(__file__).resolve().parents[3] / "materials.yaml"


DEFAULT_MATERIALS_PATH = _default_materials_path()

GRAIN_EPS = 1e-9


@dataclass(frozen=True)
class Material:
    name: str
    sheet_w: float
    sheet_h: float
    grain_tolerance: float
    """Degrees a part may deviate from the grain axis.

    El rango util real es 0 a 90: por como se calcula la distancia angular al
    eje de veta (ver `_distance_to_grain_axis`), esa distancia nunca supera 90
    grados, asi que cualquier valor de 90 o mas equivale a rotacion libre,
    igual que 180. Por convencion se usa 180 para expresar "libre".
    """


def _as_float(value: object, *, name: str, field: str) -> float:
    """Convert `value` to float, raising a clear, Spanish, per-field error."""
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"el material {name!r} tiene un valor inválido en '{field}': {value!r}"
            " (se esperaba un número)"
        ) from None


def load_materials(path: str | Path) -> dict[str, Material]:
    """Read the YAML catalogue, failing loudly on a malformed entry."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        raw = yaml.safe_load(text) or {}
    except yaml.YAMLError as error:
        # yaml.YAMLError is not an OSError (the file read fine) nor a
        # ValueError (it is not raised by this function), so callers that
        # only catch those two would otherwise see a raw yaml.YAMLError
        # traceback instead of a handled input error.
        raise ValueError(
            f"el catálogo de materiales {path} tiene un error de sintaxis YAML: {error}"
        ) from error

    if not isinstance(raw, dict):
        raise ValueError(
            "el catálogo de materiales tiene que ser un mapeo de 'nombre: campos'"
            f", no {type(raw).__name__} ({raw!r})"
        )

    materials: dict[str, Material] = {}

    for name, spec in raw.items():
        if not isinstance(spec, dict):
            raise ValueError(f"el material {name!r} no es un bloque de campos")

        size = spec.get("placa")
        if not isinstance(size, (list, tuple)) or len(size) != 2:
            raise ValueError(
                f"el material {name!r} necesita 'placa: [ancho, alto]' en milímetros"
            )
        if "tolerancia_veta" not in spec:
            raise ValueError(f"al material {name!r} le falta el campo 'tolerancia_veta'")

        sheet_w = _as_float(size[0], name=name, field="placa.ancho")
        sheet_h = _as_float(size[1], name=name, field="placa.alto")
        grain_tolerance = _as_float(
            spec["tolerancia_veta"], name=name, field="tolerancia_veta"
        )

        if sheet_w <= 0 or sheet_h <= 0:
            raise ValueError(
                f"el material {name!r} tiene 'placa' inválida: [{size[0]!r}, {size[1]!r}]"
                " (ancho y alto tienen que ser estrictamente positivos)"
            )

        if not (0 <= grain_tolerance <= 180):
            raise ValueError(
                f"el material {name!r} tiene 'tolerancia_veta' inválida: {spec['tolerancia_veta']!r}"
                " (tiene que estar entre 0 y 180 grados inclusive)"
            )

        materials[name] = Material(
            name=name,
            sheet_w=sheet_w,
            sheet_h=sheet_h,
            grain_tolerance=grain_tolerance,
        )

    return materials


def allowed_angles(material: Material, angles: Sequence[float]) -> list[float]:
    """Keep only the angles the material's grain constraint permits.

    An angle is allowed when it lies within `grain_tolerance` degrees of the
    grain axis, which runs along both 0 and 180 degrees.

    The distance to the grain axis (`_distance_to_grain_axis`) is always in
    [0, 90], so any `grain_tolerance` of 90 or more allows every angle, same
    as 180. The useful range is really 0 to 90; 180 is the conventional
    spelling for "free rotation".
    """
    return [a for a in angles if _distance_to_grain_axis(a) <= material.grain_tolerance + GRAIN_EPS]


def _distance_to_grain_axis(angle: float) -> float:
    folded = angle % 180.0
    return min(folded, 180.0 - folded)
