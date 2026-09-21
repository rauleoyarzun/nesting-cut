import math
import sys
from pathlib import Path

import pytest

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import (
    EFFORT_RESTARTS,
    PackResult,
    UnknownEffortError,
    layout_cost,
    pack,
    replicate,
)
from nesting.engine.raster.oracle import RasterOracle
from nesting.geometry.verify import verify
from nesting.model.entities import Transform
from nesting.model.material import Material
from nesting.model.part import Part, Placement

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "bench"))
from make_sample import write_sample  # noqa: E402

MATERIAL = Material("test", 1000.0, 1000.0, grain_tolerance=180.0)


def base_config(**overrides):
    defaults = dict(sep=8.0, margin=15.0, angles=(0.0, 90.0), mirror=False,
                    resolution=2.0, effort="rapido", seed=0)
    defaults.update(overrides)
    return NestConfig(**defaults)


def rect_part(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def circle_part(part_id, radius, segments=40):
    ring = tuple(
        (radius * math.cos(2 * math.pi * i / segments),
         radius * math.sin(2 * math.pi * i / segments))
        for i in range(segments)
    )
    return Part(part_id, ring, (), (part_id,))


def test_the_effort_table_has_the_three_levels():
    assert set(EFFORT_RESTARTS) == {"rapido", "normal", "lento"}
    assert EFFORT_RESTARTS["rapido"] < EFFORT_RESTARTS["normal"] < EFFORT_RESTARTS["lento"]


def test_an_unknown_effort_level_is_rejected():
    parts = [rect_part(0, 100.0, 100.0)]
    with pytest.raises(UnknownEffortError) as info:
        pack(parts, MATERIAL, base_config(effort="turbo"), RasterOracle)
    assert "turbo" in str(info.value)


def test_layout_cost_prefers_fewer_sheets():
    few = [rect_part(i, 300.0, 300.0) for i in range(4)]
    many = [rect_part(i, 300.0, 300.0) for i in range(16)]

    one_sheet = pack(few, MATERIAL, base_config(), RasterOracle)
    several = pack(many, MATERIAL, base_config(), RasterOracle)

    assert layout_cost(one_sheet, few).placas < layout_cost(several, many).placas


def test_layout_cost_reports_the_height_used_on_the_last_sheet():
    parts = [rect_part(0, 200.0, 200.0)]
    result = pack(parts, MATERIAL, base_config(), RasterOracle)
    costo = layout_cost(result, parts)
    sheets, height = costo.placas, costo.alto_ultima

    assert sheets == 1
    assert 200.0 <= height <= 260.0, "el alto usado es el de la pieza mas el margen"


def test_el_costo_prefiere_dejar_menos_material_en_la_ultima_placa():
    """Entre dos layouts de la misma cantidad de placas, gana el que deja
    menos material en la última: es el que está más cerca de no necesitarla.

    Es el caso exacto que el motor encontraba y descartaba sobre
    `NESTING 2.ai`: un layout de 33 piezas en la placa 1 y 3 en la 2
    perdía contra uno de 29 y 7, porque las 3 apiladas llegaban más
    alto que las 7 en fila.
    """
    parts = [rect_part(i, 100.0, 100.0) for i in range(4)]
    # `poco` deja una sola pieza en la placa 1 (la última); `mucho` deja tres.
    poco = PackResult(
        placements=[
            Placement(0, 0, Transform(0.0, False, 0.0, 0.0)),
            Placement(1, 0, Transform(0.0, False, 0.0, 200.0)),
            Placement(2, 0, Transform(0.0, False, 0.0, 400.0)),
            Placement(3, 1, Transform(0.0, False, 0.0, 0.0)),
        ],
        sheets_used=2,
    )
    mucho = PackResult(
        placements=[
            Placement(0, 0, Transform(0.0, False, 0.0, 0.0)),
            Placement(1, 1, Transform(0.0, False, 0.0, 0.0)),
            Placement(2, 1, Transform(0.0, False, 200.0, 0.0)),
            Placement(3, 1, Transform(0.0, False, 400.0, 0.0)),
        ],
        sheets_used=2,
    )
    # `mucho` deja las tres piezas en una fila baja: gana en alto.
    assert layout_cost(mucho, parts).alto_ultima <= layout_cost(poco, parts).alto_ultima
    # Y aun así pierde, porque deja el triple de material en la última placa.
    assert layout_cost(poco, parts) < layout_cost(mucho, parts)


def test_el_alto_sigue_desempatando_con_el_mismo_material():
    """Con el mismo material en la última placa, gana la más compactada:
    la tira sobrante queda en un solo bloque en vez de en pedazos."""
    parts = [rect_part(i, 100.0, 100.0) for i in range(2)]
    baja = PackResult(
        placements=[
            Placement(0, 0, Transform(0.0, False, 0.0, 0.0)),
            Placement(1, 1, Transform(0.0, False, 0.0, 0.0)),
        ],
        sheets_used=2,
    )
    alta = PackResult(
        placements=[
            Placement(0, 0, Transform(0.0, False, 0.0, 0.0)),
            Placement(1, 1, Transform(0.0, False, 0.0, 500.0)),
        ],
        sheets_used=2,
    )
    assert layout_cost(baja, parts).material_ultima == layout_cost(alta, parts).material_ultima
    assert layout_cost(baja, parts) < layout_cost(alta, parts)


def test_rapido_is_a_single_pass():
    parts = [circle_part(i, 90.0) for i in range(10)]
    first = pack(parts, MATERIAL, base_config(effort="rapido"), RasterOracle)
    second = pack(parts, MATERIAL, base_config(effort="rapido"), RasterOracle)
    assert first.placements == second.placements


def test_the_same_seed_gives_the_same_result():
    parts = [circle_part(i, 80.0) for i in range(12)]
    config = base_config(effort="normal", seed=7)
    assert pack(parts, MATERIAL, config, RasterOracle).placements == \
           pack(parts, MATERIAL, config, RasterOracle).placements


def test_different_seeds_can_give_different_results():
    """Piezas variadas, en una cantidad pasada apenas el quiebre a dos placas.

    El fixture tiene que caer donde el orden de insercion importa. El
    anterior (18 rectangulos identicos) no lo hacia: cualquier orden daba el
    mismo resultado y la asercion se cumplia trivialmente. El que lo
    reemplazo (43 piezas de estos tamanios) si lo hacia con el peso de
    contacto de entonces, pero dejo de hacerlo cuando la Tarea 6 recalibro
    `Weights.contact` a 4.0: medido con 4 semillas (1, 2, 3, 4) sobre este
    mismo material, sep y margen, 43 piezas dan 3 layouts distintos con
    contacto 1.0 y UNO SOLO con contacto 4.0 -- ninguna perturbacion mejora
    al orden por area, asi que `best` nunca se reemplaza.

    52 es la cantidad medida que sigue siendo sensible con los dos pesos: 4
    layouts distintos entre esas 4 semillas tanto a contacto 1.0 como a 4.0.
    No se baja la exigencia de la asercion -- sigue siendo que dos semillas
    dan placements distintos -- se corrige el fixture para que vuelva a
    estar donde el orden decide.
    """
    sizes = [(120.0, 90.0), (200.0, 60.0), (150.0, 150.0), (80.0, 200.0),
             (250.0, 40.0), (100.0, 100.0), (170.0, 110.0), (60.0, 300.0),
             (140.0, 140.0), (90.0, 220.0)]
    parts = [rect_part(i, *sizes[i % len(sizes)]) for i in range(52)]
    a = pack(parts, MATERIAL, base_config(effort="normal", seed=1), RasterOracle)
    b = pack(parts, MATERIAL, base_config(effort="normal", seed=2), RasterOracle)
    assert a.placements != b.placements


def test_normal_is_never_worse_than_rapido():
    """El costo del mejor de N intentos no puede superar al del primero."""
    parts = [circle_part(i, 85.0) for i in range(16)]
    quick = pack(parts, MATERIAL, base_config(effort="rapido"), RasterOracle)
    normal = pack(parts, MATERIAL, base_config(effort="normal", seed=3), RasterOracle)

    assert layout_cost(normal, parts) <= layout_cost(quick, parts)


def test_every_effort_level_produces_a_valid_layout():
    parts = [circle_part(i, 90.0) for i in range(14)]
    for effort in ("rapido", "normal", "lento"):
        config = base_config(effort=effort, seed=5)
        result = pack(parts, MATERIAL, config, RasterOracle)
        violations = verify(parts, result.placements, MATERIAL.sheet_w, MATERIAL.sheet_h,
                            sep=config.sep, margin=config.margin)
        assert violations == [], f"el nivel {effort} produjo una salida invalida"


def test_every_part_is_placed_at_every_effort_level():
    parts = [rect_part(i, 150.0, 100.0) for i in range(12)]
    for effort in ("rapido", "normal", "lento"):
        result = pack(parts, MATERIAL, base_config(effort=effort), RasterOracle)
        assert len(result.placements) == len(parts)


def test_the_last_sheet_gets_compacted():
    """Dos placas: la segunda tiene que quedar apretada contra el borde de abajo."""
    parts = [rect_part(i, 400.0, 400.0) for i in range(6)]
    config = base_config(effort="normal", seed=2)
    result = pack(parts, MATERIAL, config, RasterOracle)

    assert result.sheets_used >= 2
    last_height = layout_cost(result, parts).alto_ultima
    assert last_height < MATERIAL.sheet_h * 0.75, "el sobrante quedo en un bloque"


def test_the_reported_time_grows_with_the_effort():
    parts = [circle_part(i, 90.0) for i in range(10)]
    quick = pack(parts, MATERIAL, base_config(effort="rapido"), RasterOracle)
    normal = pack(parts, MATERIAL, base_config(effort="normal"), RasterOracle)
    assert normal.seconds > quick.seconds


# --- Hallazgo 1: monotonia completa entre niveles de esfuerzo -------------
#
# `lento <= normal <= rapido` es la garantia que el usuario espera: subir el
# esfuerzo nunca puede empeorar el resultado. `normal <= rapido` ya estaba
# cubierta (`test_normal_is_never_worse_than_rapido`), pero el hueco entre
# `normal` y `lento` no tenia ningun test -- y era exactamente donde vivia
# el defecto, porque las dos trayectorias de perturbacion divergian desde
# el primer paso. Estos tests cubren ese hueco con resolucion gruesa
# (barata) sobre varios conjuntos de piezas y semillas, y ademas fijan el
# caso exacto de la reproduccion reportada (24 piezas de `muestra.dxf`).


def test_effort_levels_are_monotonic():
    """lento <= normal <= rapido, para varios conjuntos de piezas y semillas."""
    cases = [
        [rect_part(i, 170.0, 110.0) for i in range(18)],
        [circle_part(i, 85.0) for i in range(14)],
        [rect_part(i, 90.0, 220.0) for i in range(20)],
    ]
    for parts in cases:
        for seed in (0, 1, 3):
            costs = {
                effort: layout_cost(
                    pack(parts, MATERIAL, base_config(effort=effort, seed=seed,
                                                       resolution=5.0), RasterOracle),
                    parts,
                )
                for effort in ("rapido", "normal", "lento")
            }
            assert costs["lento"] <= costs["normal"] <= costs["rapido"], (
                f"orden roto con seed={seed}: {costs}"
            )


def test_effort_levels_are_monotonic_on_the_reported_regression(tmp_path):
    """El caso exacto de la reproduccion: 24 piezas de `muestra.dxf`.

    Antes del arreglo, con esta misma configuracion, `lento` (1, 1324.0) daba
    peor que `normal` (1, 1321.0). Con el arreglo, `lento` es un
    superconjunto de los reintentos de `normal`, asi que no puede superarlo.
    """
    from nesting.io.dxf_reader import read_dxf
    from nesting.pipeline import prepare_parts

    dxf_path = tmp_path / "muestra.dxf"
    write_sample(dxf_path)
    parts, _, _ = prepare_parts(read_dxf(dxf_path))
    parts = replicate(parts, 2)
    assert len(parts) == 24

    material = Material("mdf18", 1830.0, 2600.0, grain_tolerance=180.0)
    costs = {
        effort: layout_cost(
            pack(parts, material,
                 NestConfig(sep=6.0, margin=10.0, resolution=3.0, effort=effort, seed=1),
                 RasterOracle),
            parts,
        )
        for effort in ("rapido", "normal", "lento")
    }
    assert costs["lento"] <= costs["normal"] <= costs["rapido"], (
        f"orden roto en el caso de la reproduccion: {costs}"
    )
