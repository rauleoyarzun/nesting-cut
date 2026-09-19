"""De un archivo de entrada a un DXF acomodado, con sus dos imágenes.

Es el mismo recorrido que hace `cli.py`, con dos diferencias: informa el
avance, y deja los resultados en una carpeta en vez de donde el usuario
dijo. Guardar donde el usuario quiere es un paso posterior y explícito.
"""

from dataclasses import dataclass
from pathlib import Path

from nesting.engine.packer import Avance, layout_cost, pack, replicate
from nesting.engine.raster.masks import MaskCache
from nesting.engine.raster.oracle import RasterOracle
from nesting.geometry.verify import verify
from nesting.io.ai_reader import read_ai
from nesting.io.diagnostic import write_diagnostic
from nesting.io.dxf_reader import UnknownUnitsError, read_dxf
from nesting.io.dxf_writer import write_dxf
from nesting.io.preview import write_preview
from nesting.io.rhino_reader import read_3dm
from nesting.model.discard import Discard
from nesting.params import NestParams, a_config
from nesting.pipeline import discard_plate_outline, prepare_parts
from nesting_app import materials_store
from nesting_app.archivos import Fuente
from nesting_app.jobs import Resultado

NOMBRE_DXF = "salida.dxf"
NOMBRE_PREVIEW = "preview.png"
NOMBRE_DIAGNOSTICO = "diagnostico.png"


class UnidadesNoDeclaradasError(ValueError):
    """El archivo no dice en qué unidades está.

    Se distingue del resto a propósito: en la CLI es un error y en la
    interfaz es una pregunta con cinco botones. Que tenga su propio tipo es
    lo que le permite a la API mostrar la pregunta en vez del error.
    """


class VerificacionFallidaError(ValueError):
    """El árbitro geométrico encontró el acomodo inválido.

    No se escribió ningún archivo, y eso es lo primero que hay que decirle
    al usuario: lo que va a la fresadora no puede salir de un layout que no
    verificó.
    """

    def __init__(self, violaciones: list[str]) -> None:
        super().__init__(
            f"la verificación geométrica encontró {len(violaciones)} problema(s). "
            "No se escribió ningún archivo."
        )
        self.violaciones = violaciones


@dataclass(frozen=True)
class Analisis:
    """Lo que se sabe del archivo antes de acomodar nada."""

    piezas: int
    avisos: list[str]
    descartes: list[dict]
    unidades: str


def _leer(fuente: Fuente, unidades: str | None):
    sufijo = fuente.ruta.suffix.lower()
    try:
        if sufijo == ".ai":
            return read_ai(fuente.ruta)
        if sufijo == ".3dm":
            return read_3dm(fuente.ruta, units_override=unidades)
        return read_dxf(fuente.ruta, units_override=unidades)
    except UnknownUnitsError as error:
        raise UnidadesNoDeclaradasError(str(error)) from error


def _a_dict(descarte: Discard) -> dict:
    """Un descarte en la forma que la interfaz sabe dibujar."""
    centro = descarte.centroid
    return {
        "motivo": descarte.reason,
        "etiqueta": descarte.style.label,
        "color": list(descarte.style.color),
        "detalle": descarte.detail,
        "puntos": [list(p) for p in descarte.path],
        "centro": list(centro) if centro else None,
    }


def analizar(fuente: Fuente, unidades: str | None, tol_cierre: float) -> Analisis:
    """Lee el archivo y cuenta qué hay, sin acomodar nada. Tarda ~1 segundo."""
    drawing = _leer(fuente, unidades)
    piezas, avisos, descartes = prepare_parts(drawing, chain_tol=tol_cierre)
    return Analisis(
        piezas=len(piezas),
        avisos=list(avisos),
        descartes=[_a_dict(d) for d in descartes],
        unidades=drawing.source_units,
    )


def acomodar(
    fuente: Fuente,
    params: NestParams,
    progreso,
    carpeta: Path,
) -> Resultado:
    """El recorrido completo. Deja tres archivos en `carpeta`."""
    materiales = materials_store.leer()
    material = materiales[params.material]

    drawing = _leer(fuente, params.unidades)
    piezas, avisos, descartes = prepare_parts(drawing, chain_tol=params.tol_cierre)
    piezas, contornos_placa = discard_plate_outline(
        piezas, material.sheet_w, material.sheet_h
    )
    if contornos_placa:
        avisos.append(
            f"se ignoraron {len(contornos_placa)} rectángulo(s) del tamaño exacto "
            f"de la placa; si alguno era una pieza de verdad, hay que cambiarle "
            "el tamaño."
        )
        descartes.extend(
            Discard(
                reason="contorno_placa",
                points=parte.outer,
                detail=f"{material.sheet_w:.0f} x {material.sheet_h:.0f} mm",
                closed=True,
            )
            for parte in contornos_placa
        )

    write_diagnostic(carpeta / NOMBRE_DIAGNOSTICO, piezas, descartes)

    if not piezas:
        raise ValueError(
            f"no se encontró ninguna pieza en {fuente.nombre}. "
            "Mirá la revisión para ver qué se descartó y por qué."
        )

    piezas = replicate(piezas, params.copias)
    config = a_config(params)
    cache = MaskCache()
    resultado = pack(
        piezas, material, config, lambda: RasterOracle(cache=cache), progreso=progreso
    )

    violaciones = verify(
        piezas, resultado.placements, material.sheet_w, material.sheet_h,
        sep=config.sep, margin=config.margin,
    )
    if violaciones:
        # Antes de escribir nada, y sin escribir nada. Esta es la regla más
        # dura del motor y no se ablanda por venir de una interfaz.
        raise VerificacionFallidaError([v.detail for v in violaciones])

    write_dxf(
        carpeta / NOMBRE_DXF, drawing, piezas, resultado.placements,
        material.sheet_w, material.sheet_h,
    )
    write_preview(
        carpeta / NOMBRE_PREVIEW, piezas, resultado.placements,
        material.sheet_w, material.sheet_h, resultado.utilization,
        colors=_colores(drawing, piezas),
    )

    _, alto_usado = layout_cost(resultado, piezas)
    return Resultado(
        placas=resultado.sheets_used,
        aprovechamiento=list(resultado.utilization),
        total=resultado.total_utilization,
        segundos=resultado.seconds,
        sobrante_mm=material.sheet_h - alto_usado,
        carpeta=carpeta,
    )


def _colores(drawing, piezas) -> dict[int, tuple[int, int, int]]:
    """El color de la primera entidad de cada pieza, para la previsualización."""
    colores: dict[int, tuple[int, int, int]] = {}
    for pieza in piezas:
        if not pieza.entity_ids:
            continue
        rgb = drawing.entities[pieza.entity_ids[0]].style.rgb
        if rgb is not None:
            colores[pieza.id] = rgb
    return colores
