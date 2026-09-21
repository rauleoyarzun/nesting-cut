import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))

from make_sample import write_sample  # noqa: E402
from run_bench import run_one  # noqa: E402

from nesting.engine.oracle import NestConfig  # noqa: E402
from nesting.engine.shelf_oracle import ShelfOracle  # noqa: E402
from nesting.model.material import Material  # noqa: E402

MATERIAL = Material("mdf18", 1830.0, 2600.0, grain_tolerance=180.0)
CONFIG = NestConfig(sep=6.0, margin=10.0)


def test_the_sample_generator_produces_a_readable_file(tmp_path):
    from nesting.io.dxf_reader import read_dxf
    from nesting.pipeline import prepare_parts

    path = tmp_path / "muestra.dxf"
    write_sample(path)

    parts, _, _ = prepare_parts(read_dxf(path))
    assert len(parts) == 12, "4 asientos mas 8 patas"


def test_the_seats_have_their_slots_as_holes(tmp_path):
    from nesting.io.dxf_reader import read_dxf
    from nesting.pipeline import prepare_parts

    path = tmp_path / "muestra.dxf"
    write_sample(path)
    parts, _, _ = prepare_parts(read_dxf(path))

    seats = [p for p in parts if len(p.holes) > 0]
    assert len(seats) == 4
    assert all(len(p.holes) == 4 for p in seats)


def test_run_one_reports_the_three_numbers(tmp_path):
    path = tmp_path / "muestra.dxf"
    write_sample(path)

    result = run_one(path, MATERIAL, CONFIG, ShelfOracle, "shelf")

    assert result.parts == 12
    assert result.sheets >= 1
    assert 0.0 < result.total_utilization <= 1.0
    assert result.seconds >= 0.0
    assert result.engine == "shelf"


def test_the_baseline_layout_is_geometrically_valid(tmp_path):
    """Sea cual sea la densidad, la salida del banco no puede violar nada."""
    path = tmp_path / "muestra.dxf"
    write_sample(path)
    result = run_one(path, MATERIAL, CONFIG, ShelfOracle, "shelf")
    assert result.violations == 0


def test_more_copies_need_more_sheets(tmp_path):
    path = tmp_path / "muestra.dxf"
    write_sample(path)

    one = run_one(path, MATERIAL, CONFIG, ShelfOracle, "shelf", copies=1)
    many = run_one(path, MATERIAL, CONFIG, ShelfOracle, "shelf", copies=8)
    assert many.sheets > one.sheets


def test_a_corrupt_file_does_not_abort_the_run(tmp_path, monkeypatch, capsys):
    """Un DXF corrupto no puede tirar abajo la medicion del resto de la corrida."""
    import run_bench

    valid_path = tmp_path / "muestra.dxf"
    write_sample(valid_path)
    # "corrupto.dxf" ordena alfabeticamente antes que "muestra.dxf".
    corrupt_path = tmp_path / "corrupto.dxf"
    corrupt_path.write_text("esto no es un dxf valido\n")

    monkeypatch.setattr(run_bench, "FILES_DIR", tmp_path)

    expected = run_one(valid_path, MATERIAL, CONFIG, ShelfOracle, "shelf")

    exit_code = run_bench.main([])
    out = capsys.readouterr().out

    assert exit_code != 0
    assert "ERROR" in out
    assert "corrupto.dxf" in out
    assert "muestra.dxf" in out
    assert f"{expected.parts:>7}" in out
    assert f"{expected.sheets:>8}" in out


def test_a_dxf_without_declared_units_is_reported_as_an_error(tmp_path, monkeypatch, capsys):
    import ezdxf

    import run_bench

    path = tmp_path / "sin_unidades.dxf"
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 0  # $INSUNITS = 0: sin declarar.
    doc.modelspace().add_lwpolyline(
        [(0, 0), (100, 0), (100, 100), (0, 100)], close=True,
    )
    doc.saveas(str(path))

    monkeypatch.setattr(run_bench, "FILES_DIR", tmp_path)

    exit_code = run_bench.main([])
    out = capsys.readouterr().out

    assert exit_code != 0
    assert "ERROR" in out
    assert "sin_unidades.dxf" in out


def test_the_same_file_measures_once_units_are_given(tmp_path, monkeypatch, capsys):
    import ezdxf

    import run_bench

    path = tmp_path / "sin_unidades.dxf"
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 0
    doc.modelspace().add_lwpolyline(
        [(0, 0), (100, 0), (100, 100), (0, 100)], close=True,
    )
    doc.saveas(str(path))

    monkeypatch.setattr(run_bench, "FILES_DIR", tmp_path)

    exit_code = run_bench.main(["--unidades", "mm"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "ERROR" not in out
    assert "sin_unidades.dxf" in out


def test_run_one_lets_chaining_invariant_errors_through(tmp_path, monkeypatch):
    """Un `ChainingInvariantError` es un bug interno: tiene que propagar, no
    quedar atrapado como si fuera un problema del archivo."""
    from nesting.geometry.chaining import ChainingInvariantError
    import nesting.pipeline as pipeline_module

    path = tmp_path / "muestra.dxf"
    write_sample(path)

    def broken_chain_contours(*args, **kwargs):
        raise ChainingInvariantError("bug interno simulado")

    monkeypatch.setattr(pipeline_module, "chain_contours", broken_chain_contours)

    with pytest.raises(ChainingInvariantError):
        run_one(path, MATERIAL, CONFIG, ShelfOracle, "shelf")


def test_run_one_reports_the_seconds_from_pack_result(tmp_path, monkeypatch):
    """`seconds` tiene que venir de `PackResult.seconds`, no de un reloj propio."""
    import run_bench
    from nesting.engine.packer import PackResult

    path = tmp_path / "muestra.dxf"
    write_sample(path)

    recognizable_seconds = 12345.678

    def fake_pack(parts, supply, config, oracle_factory):
        return PackResult(
            placements=[], sheets=[MATERIAL.stock_sheet()], utilization=[0.5],
            total_utilization=0.5, seconds=recognizable_seconds,
        )

    monkeypatch.setattr(run_bench, "pack", fake_pack)

    result = run_bench.run_one(path, MATERIAL, CONFIG, ShelfOracle, "shelf")
    assert result.seconds == recognizable_seconds
