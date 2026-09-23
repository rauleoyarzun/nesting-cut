"""De un archivo de entrada a un DXF acomodado, con sus dos imágenes.

Es el mismo recorrido que hace `cli.py`, con dos diferencias: informa el
avance, y deja los resultados en una carpeta en vez de donde el usuario
dijo. Guardar donde el usuario quiere es un paso posterior y explícito.
"""

from dataclasses import dataclass
from pathlib import Path

from nesting.engine.packer import (
    Avance,
    Cancelado,
    initial_forecast,
    layout_cost,
    pack,
    probe_query_seconds,
    replicate,
)
from nesting.engine.raster.oracle import RasterOracleFactory
from nesting.geometry.verify import verify
from nesting.io.ai_reader import read_ai
from nesting.io.diagnostic import write_diagnostic
from nesting.io.dxf_reader import UnknownUnitsError, read_dxf
from nesting.io.dxf_writer import write_dxf
from nesting.io.preview import write_preview
from nesting.io.rhino_reader import read_3dm
from nesting.model.discard import Discard
from nesting.params import NestParams, a_config, a_supply, validar
from nesting.pipeline import discard_plate_outline, prepare_parts
from nesting_app import materials_store
from nesting_app.archivos import Fuente
from nesting_app.jobs import ERRORES_DEL_USUARIO, Resultado

NOMBRE_DXF = "salida.dxf"
NOMBRE_PREVIEW = "preview.png"
NOMBRE_DIAGNOSTICO = "diagnostico.png"

FACTOR_LLENO = 1.42
"""Cuánto más cara es, en promedio, una consulta de la corrida que la de la prueba.

La prueba de `estimar_segundos` pregunta sobre una placa VACÍA, y una placa
vacía es el caso más barato: el árbitro exacto (`engine/exact.py`) verifica
candidatos contra las piezas ya colocadas, y ahí no hay ninguna. A medida
que la placa se llena, cada consulta verifica más candidatos contra más
vecinos. Este factor lleva el costo de la prueba al costo medio de una
consulta de la corrida.

MEDIDO EL 2026-09-23 con `bench/calibrate.py --factor-lleno` sobre
`bench/files/*` (multilam18, sep 8, borde 5, 1 mm/px, esfuerzo normal), en
la máquina del taller:

    FACTOR_LLENO  (multilam18, veta 5 grados, 4 posiciones con espejo, sep 8, borde 5, 1 mm/px, esfuerzo normal, --copias 1)
    archivo                      piezas orient. previstas  reales s/c prueba  s/c real  factor  s reales
    ----------------------------------------------------------------------------------------------------
    muestra.dxf                      12       4       192     192     0.0232    0.0537    2.32      10.3
    banqueta final raulo.ai          40       4      1040     640     0.0564    0.0788    1.40      50.5
    banqueta-alta.ai                 57       4      1496     928     0.1073    0.1285    1.20     119.2

    -> mediana del factor: 1.40

    FACTOR_LLENO  (multilam18, veta 180 grados, 8 posiciones con espejo, sep 8, borde 5, 1 mm/px, esfuerzo normal, --copias 1)
    archivo                      piezas orient. previstas  reales s/c prueba  s/c real  factor  s reales
    ----------------------------------------------------------------------------------------------------
    muestra.dxf                      12      16       768     768     0.0248    0.0571    2.31      43.8
    banqueta final raulo.ai          40      16      4160    2560     0.0566    0.0816    1.44     208.8
    banqueta-alta.ai                 57      16      5984    4688     0.1094    0.1351    1.23     633.4

    -> mediana del factor: 1.44

Se usa la mediana de los factores de las dos tablas juntas, y no el
promedio, para que un archivo raro no mueva la estimación de todos. El
factor corrige sólo el costo por consulta: el error de la previsión de
consultas de arranque (columnas "previstas" contra "reales") es aparte, y
la previsión se corrige sola apenas termina el primer intento.

Para volver a medir: correr los dos comandos de arriba (ver
`bench/calibrate.py --help`) y reemplazar las dos tablas y el valor.
"""


class UnidadesNoDeclaradasError(ValueError):
    """El archivo no dice en qué unidades está.

    Se distingue del resto a propósito: en la CLI es un error y en la
    interfaz es una pregunta con cinco botones. Que tenga su propio tipo es
    lo que le permite a la API mostrar la pregunta en vez del error.
    """


def _traducir_para_interfaz(error: Exception) -> None:
    """Reescribe, en el lugar, un mensaje del motor que nombra un flag de
    la CLI, para que hable del control de la interfaz en vez de eso.

    `nesting/pipeline.py` dice "afloje la tolerancia con --tol-cierre":
    correcto para quien lo lee en una terminal, porque `--tol-cierre` es
    justamente el flag que tiene que escribir. Pero la interfaz gráfica no
    tiene una terminal: el control se llama "Tolerancia de cierre", y
    mostrarle a alguien un flag que no puede tipear en ningún lado no
    ayuda.

    La traducción vive acá, del lado de la aplicación, y no en el motor:
    `nesting/pipeline.py` sigue nombrando su propio flag para la CLI (que
    lo necesita tal cual, ver `tests/test_pipeline.py` y
    `tests/test_cli.py`), y esta función sólo reescribe `args` sin tocar el
    tipo de la excepción -- así que `jobs.ERRORES_DEL_USUARIO` sigue
    clasificándola igual.
    """
    if not error.args:
        return
    mensaje = str(error.args[0])
    si_dice_cli = "afloje la tolerancia con --tol-cierre"
    if si_dice_cli in mensaje:
        error.args = (
            mensaje.replace(si_dice_cli, 'afloje la "Tolerancia de cierre"'),
        ) + error.args[1:]


def _con_avisos(error: Exception, avisos: list[str]) -> Exception:
    """Cuelga los avisos ya generados de una excepción antes de lanzarla.

    Si `acomodar()` falla después de haber calculado avisos (por ejemplo,
    "no se encontró ninguna pieza", que es justamente el que explica por
    qué no quedó nada), esos avisos no tienen dónde más viajar: `Resultado`
    no llega a existir porque el trabajo no terminó bien. Se los deja como
    atributo de la excepción -- el mismo lugar de donde `VerificacionFallidaError`
    ya sacaba sus `violaciones` -- y `Registro._correr` los lee de ahí con
    `getattr`, sin necesidad de conocer cada tipo de excepción en particular.
    """
    error.avisos = list(avisos)
    return error


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
    """Lee el archivo y cuenta qué hay, sin acomodar nada. Tarda ~1 segundo.

    Deja además la imagen de revisión en `fuente.carpeta`. Es el mismo dibujo
    que produce `acomodar`, pero disponible antes de comprometerse a un
    acomodo que puede tardar nueve minutos: la pregunta "¿cuáles son los dos
    que descartó?" se contesta en el segundo que tarda el análisis, que es
    cuando el usuario todavía puede volver al archivo original y corregirlo.

    La del acomodo no es redundante: aquélla conoce el material, así que
    marca además los rectángulos del tamaño exacto de la placa. Ésta no sabe
    sobre qué placa se va a cortar y no puede marcarlos.
    """
    drawing = _leer(fuente, unidades)
    try:
        piezas, avisos, descartes = prepare_parts(drawing, chain_tol=tol_cierre)
    except Exception as error:
        _traducir_para_interfaz(error)
        raise
    try:
        write_diagnostic(fuente.carpeta / NOMBRE_DIAGNOSTICO, piezas, descartes)
    except OSError as error:
        # No se levanta: el análisis ya tiene su respuesta y perderla por no
        # poder escribir un PNG sería peor que quedarse sin la imagen. La
        # ruta que la sirve contesta 409 y la pantalla lo dice.
        avisos.append(
            f"no se pudo dibujar la revisión ({error}); el resto del análisis "
            "es válido."
        )
    return Analisis(
        piezas=len(piezas),
        avisos=list(avisos),
        descartes=[_a_dict(d) for d in descartes],
        unidades=drawing.source_units,
    )


def estimar_segundos(piezas, supply, config) -> float | None:
    """Cuántos segundos va a tardar `pack(piezas, supply, config, ...)`, antes de correrlo.

        segundos = segundos_por_consulta_medido
                   * consultas_previstas_al_arrancar
                   * FACTOR_LLENO

    La prueba usa una caché de máscaras nueva, así que incluye rasterizar;
    ver `probe_query_seconds`.
    """
    por_consulta = probe_query_seconds(
        piezas, supply, config, RasterOracleFactory()
    )
    if por_consulta is None:
        return None
    return por_consulta * initial_forecast(piezas, supply, config) * FACTOR_LLENO


def estimar(fuente: Fuente, params: NestParams) -> float | None:
    """La estimación previa de un acomodo, o `None` si no se puede estimar.

    Recorre lo mismo que `acomodar` hasta tener las piezas -- leer, preparar,
    descartar el contorno de la placa, replicar -- y no escribe nada.
    Todo lo que `jobs.ERRORES_DEL_USUARIO` llama "tu archivo o tus
    parámetros tienen un problema" da `None`: la pantalla no muestra nada, y
    el error de verdad lo va a dar Acomodar, con su cartel. Un bug del
    programa no está en esa tupla y sale como tal.

    `materials_store.leer()` corre AFUERA de ese `try` a propósito: un
    catálogo corrupto es `ValueError`, que está en `ERRORES_DEL_USUARIO`
    por ambigüedad de origen, pero acá el origen no es ambiguo -- es un bug
    o un archivo de datos roto, no "tu archivo o tus parámetros". Adentro
    del `try`, ese `ValueError` se hubiera disfrazado de `{"segundos":
    None}` mientras `POST /api/trabajos` (`api.py`) surte la misma
    condición como 500: la misma rotura, dos caras. Se propaga tal cual,
    para que salga 500 acá también.
    """
    materiales = materials_store.leer()
    material = materiales.get(params.material)
    try:
        # `validar` primero y no después, igual que `POST /api/trabajos`:
        # acepta `material=None` y así un pedido con dos errores (parámetros
        # inválidos Y material inexistente) señala primero el mismo problema
        # en las dos rutas.
        validar(params, material)
        if material is None:
            return None
        drawing = _leer(fuente, params.unidades)
        piezas, _, _ = prepare_parts(drawing, chain_tol=params.tol_cierre)
        piezas, _ = discard_plate_outline(piezas, material.sheet_w, material.sheet_h)
        return estimar_segundos(
            replicate(piezas, params.copias),
            a_supply(params, material),
            a_config(params),
        )
    except ERRORES_DEL_USUARIO:
        return None


def acomodar(
    fuente: Fuente,
    params: NestParams,
    progreso,
    carpeta: Path,
) -> Resultado:
    """El recorrido completo. Deja tres archivos en `carpeta`."""
    materiales = materials_store.leer()
    try:
        material = materiales[params.material]
    except KeyError as error:
        # La API prechequea que el material exista antes de encolar el
        # trabajo, pero ese chequeo y esta lectura -- que corre en el hilo
        # trabajador, potencialmente mucho después -- no son atómicos: el
        # material puede borrarse o renombrarse desde la pantalla de
        # materiales mientras el trabajo espera en la cola. Sin este except,
        # ese `KeyError` crudo caía fuera de `jobs.ERRORES_DEL_USUARIO` (que
        # excluye `KeyError` a propósito, por ambiguo) y el usuario veía
        # "se rompió el programa" con el repr de una clave de diccionario,
        # para un problema que no tiene nada que ver con un bug.
        raise materials_store.MaterialDesconocidoError(
            f"el material {params.material!r} ya no está en el catálogo: "
            "puede haberse borrado o renombrado mientras este trabajo "
            "esperaba en la cola. Elegí un material que exista en la lista "
            "y volvé a acomodar."
        ) from error

    drawing = _leer(fuente, params.unidades)
    try:
        piezas, avisos, descartes = prepare_parts(drawing, chain_tol=params.tol_cierre)
    except Exception as error:
        _traducir_para_interfaz(error)
        raise
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

    # A partir de acá, cualquier excepción que se escape lleva colgados los
    # avisos ya calculados -- son la explicación de por qué no quedó nada,
    # y `Resultado` no llega a existir para cargarlos por las buenas. Un
    # único `try` para todo el resto de la función, en vez de un
    # `_con_avisos` en cada `raise`, es lo que garantiza que un error nuevo
    # el día de mañana (una pieza demasiado grande, un esfuerzo desconocido,
    # una resolución inválida, un `sep` o `borde` negativo, lo que sea) no
    # vuelva a perderlos en silencio por faltarle el envoltorio.
    #
    # `Cancelado` es la única excepción que tiene que pasar sin tocar:
    # `Registro` lo distingue de un error para marcar el trabajo como
    # cancelado, no como fallido.
    try:
        try:
            write_diagnostic(carpeta / NOMBRE_DIAGNOSTICO, piezas, descartes)
        except OSError as error:
            raise OSError(
                f"no se pudo escribir el diagnóstico en "
                f"{carpeta / NOMBRE_DIAGNOSTICO}: {error}. Verifique que el "
                "directorio de destino exista."
            ) from error

        if not piezas:
            raise ValueError(
                f"no se encontró ninguna pieza en {fuente.nombre}. "
                "Mirá la revisión para ver qué se descartó y por qué."
            )

        piezas = replicate(piezas, params.copias)
        config = a_config(params)
        supply = a_supply(params, material)
        resultado = pack(
            piezas, supply, config, RasterOracleFactory(), progreso=progreso
        )

        violaciones = verify(
            piezas, resultado.placements, resultado.sheets,
            sep=config.sep, margin=config.margin,
        )
        if violaciones:
            # Antes de escribir nada, y sin escribir nada. Esta es la regla
            # más dura del motor y no se ablanda por venir de una interfaz.
            raise VerificacionFallidaError([v.detail for v in violaciones])

        try:
            write_dxf(
                carpeta / NOMBRE_DXF, drawing, piezas, resultado.placements,
                resultado.sheets,
            )
        except OSError as error:
            raise OSError(
                f"no se pudo escribir la salida en {carpeta / NOMBRE_DXF}: "
                f"{error}. Verifique que el directorio de destino exista."
            ) from error

        try:
            write_preview(
                carpeta / NOMBRE_PREVIEW, piezas, resultado.placements,
                resultado.sheets, resultado.utilization,
                colors=_colores(drawing, piezas),
            )
        except (ValueError, OSError) as error:
            # Cosmético, no estructural: el DXF (lo que de verdad va a la
            # fresadora) ya se escribió arriba, con éxito. Igual que en la
            # CLI, fallar acá con una excepción le haría creer al usuario
            # que no quedó nada. Se degrada a aviso y se sigue, así que no
            # pasa por el `except` de abajo.
            avisos.append(
                f"no se pudo generar la previsualización: {error}. El DXF sí se "
                "escribió correctamente y está listo para usar."
            )
    except Cancelado:
        raise
    except Exception as error:
        # Se cuelgan los avisos y se relanza el mismo objeto -- ni un tipo
        # ni un mensaje distinto -- porque `Registro` clasifica por tipo
        # para decidir si es un problema del usuario o un bug nuestro.
        _con_avisos(error, avisos)
        raise

    costo = layout_cost(resultado, piezas)
    return Resultado(
        placas=resultado.sheets_used,
        aprovechamiento=list(resultado.utilization),
        total=resultado.total_utilization,
        segundos=resultado.seconds,
        sobrante_mm=(
            resultado.sheets[-1].height - costo.alto_ultima
            if resultado.sheets else 0.0
        ),
        material_ultima_placa_m2=costo.material_ultima / 1e6,
        carpeta=carpeta,
        avisos=list(avisos),
        recortes_usados=sum(1 for hoja in resultado.sheets if hoja.scrap),
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
