import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))

from calibrate import (  # noqa: E402
    CONTACT_CANDIDATES,
    EFFORT_LEVELS,
    RESOLUTION_CANDIDATES,
    sweep_effort,
    sweep_resolution,
    sweep_weights,
)
from make_sample import write_sample  # noqa: E402

from nesting.engine.oracle import NestConfig  # noqa: E402
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

    for (_, _, _, sheets_few), (_, _, _, sheets_many) in zip(few, many):
        assert sheets_many > sheets_few
