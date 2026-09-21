import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))

from calibrate import (  # noqa: E402
    CONTACT_CANDIDATES,
    EFFORT_LEVELS,
    RESOLUTION_CANDIDATES,
    _mejor,
    sweep_effort,
    sweep_resolution,
    sweep_weights,
)
from make_sample import write_sample  # noqa: E402

from nesting.engine.oracle import NestConfig, Weights  # noqa: E402
from nesting.model.material import Material  # noqa: E402

MATERIAL = Material("mdf18", 1830.0, 2600.0, grain_tolerance=180.0)


def sample(tmp_path):
    path = tmp_path / "muestra.dxf"
    write_sample(path)
    return [path]


def test_the_weight_sweep_covers_every_candidate(tmp_path):
    config = NestConfig(sep=6.0, margin=10.0, effort="rapido", resolution=3.0)
    rows = sweep_weights(sample(tmp_path), MATERIAL, config)

    assert len(rows) == len(CONTACT_CANDIDATES)
    assert [row[0] for row in rows] == list(CONTACT_CANDIDATES)
    assert all(0.0 < row[1] <= 1.0 for row in rows)


def test_the_resolution_sweep_covers_every_candidate(tmp_path):
    config = NestConfig(sep=6.0, margin=10.0, effort="rapido")
    rows = sweep_resolution(sample(tmp_path), MATERIAL, config)

    assert len(rows) == len(RESOLUTION_CANDIDATES)
    assert [row[0] for row in rows] == list(RESOLUTION_CANDIDATES)
    assert all(0.0 < row[1] <= 1.0 for row in rows)


def test_the_effort_sweep_covers_every_level(tmp_path):
    config = NestConfig(sep=6.0, margin=10.0, resolution=4.0)
    rows = sweep_effort(sample(tmp_path), MATERIAL, config)

    assert [row[0] for row in rows] == list(EFFORT_LEVELS)
    assert all(0.0 < row[1] <= 1.0 for row in rows)


def test_more_effort_never_uses_more_sheets(tmp_path):
    config = NestConfig(sep=6.0, margin=10.0, resolution=4.0)
    rows = sweep_effort(sample(tmp_path), MATERIAL, config)
    sheets = {row[0]: row[3] for row in rows}
    assert sheets["normal"] <= sheets["rapido"]
    assert sheets["lento"] <= sheets["normal"]


def test_every_sweep_reports_what_the_engine_actually_minimises(tmp_path):
    """Las filas traen material en la última placa y tira libre, no sólo aprovechamiento.

    `layout_cost` ordena por (placas, material en la última, alto de la
    última). Un barrido que no reportara esas cifras no podría elegir con el
    mismo criterio que el motor, que es justo lo que pasaba antes de la
    Tarea 6.

    Se ejercitan dos de los tres barridos y no los tres: las filas las arma
    `calibrate._fila`, que es la misma para los tres, y `sweep_effort`
    incluye `lento` (12 reintentos) -- pagar eso acá no agregaria cobertura.
    """
    config = NestConfig(sep=6.0, margin=10.0, effort="rapido", resolution=3.0)
    files = sample(tmp_path)

    for rows in (
        sweep_weights(files, MATERIAL, config),
        sweep_resolution(files, MATERIAL, config),
    ):
        for row in rows:
            assert len(row) == 6
            _, _, seconds, sheets, material_ultima, tira_libre = row
            assert seconds > 0.0
            assert sheets >= 1
            assert material_ultima > 0.0
            assert 0.0 <= tira_libre <= MATERIAL.sheet_h


def test_the_best_row_is_picked_with_the_engines_criterion_not_the_first_sheet():
    """Menos placas y menos material en la última mandan sobre el aprovechamiento.

    La fila `perdedora` gana en aprovechamiento de la primera placa y es más
    rápida, pero deja más material en la última: el motor la descartaría, así
    que el calibrador también tiene que descartarla. Con el orden anterior
    (aprovechamiento primero) este test fallaría.
    """
    ganadora = (1.0, 0.50, 200.0, 2, 0.30, 400.0)
    perdedora = (2.0, 0.90, 10.0, 2, 0.90, 900.0)
    con_mas_placas = (4.0, 0.99, 1.0, 3, 0.01, 2000.0)

    assert _mejor([perdedora, ganadora, con_mas_placas]) == 1.0


def test_the_best_row_breaks_ties_by_time():
    """A igualdad de placas y de material en la última, gana la más rápida."""
    lenta = (1.0, 0.60, 300.0, 2, 0.50, 400.0)
    rapida = (2.0, 0.60, 30.0, 2, 0.50, 400.0)

    assert _mejor([lenta, rapida]) == 2.0


def test_the_weight_sweep_respects_the_copies_argument(tmp_path):
    """`copies` tiene que llegar de verdad a `run_one`, no quedar ignorado.

    Si `sweep_weights` lo ignorara, la cantidad de placas totales seria la
    misma con `copies=1` que con `copies=6`; al pasarlo de verdad, 6 copias
    de la pieza sintetica necesitan mas placas que 1.
    """
    config = NestConfig(sep=6.0, margin=10.0, effort="rapido", resolution=3.0)
    files = sample(tmp_path)

    few = sweep_weights(files, MATERIAL, config, copies=1)
    many = sweep_weights(files, MATERIAL, config, copies=6)

    for row_few, row_many in zip(few, many):
        assert row_many[3] > row_few[3]


def test_los_valores_recalibrados_no_vuelven_en_silencio_a_los_viejos():
    """Detector de cambio, no de propiedad: ninguna regla del código exige
    `Weights.contact == 4.0` ni `NestConfig.resolution == 2.0` -- son los
    valores de un barrido medido (Tarea 6 del plan de densidad y colisión
    exacta), no algo derivable del código. El único piso funcional que los
    protege hoy es `test_a_small_part_is_nested_inside_a_big_hole` (en
    `tests/engine/raster/test_raster_oracle.py`), que pasa con `contact`
    desde 0.7 en adelante: un revert silencioso de 4.0 a 1.0 -- o a
    cualquier otro valor por encima de ese piso -- es invisible para ese
    test, aunque le cueste al archivo de referencia pasar de 32/4 a 34/2
    piezas en la última placa (ver la tabla de `Weights.contact` en
    `nesting/engine/oracle.py`). Lo mismo pasa con `resolution`: nada
    revienta con 3.0 en vez de 2.0, sólo se pierde densidad.

    Si este test se rompe porque alguien cambió alguno de los dos valores a
    propósito, no hay que tocar el assert sin volver a medir: ver la tabla
    completa y el razonamiento en `docs/superpowers/calibracion.md` y en los
    docstrings de `Weights.contact` / `NestConfig.resolution`.
    """
    assert Weights().contact == 4.0
    assert NestConfig().resolution == 2.0
