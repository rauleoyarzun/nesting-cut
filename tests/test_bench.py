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


def test_un_caso_fijo_sin_su_archivo_se_saltea(tmp_path):
    import run_bench

    assert run_bench.run_fixed(run_bench.CASOS_FIJOS[0], files_dir=tmp_path) is None


def test_la_banqueta_alta_es_un_caso_fijo_del_banco():
    import run_bench

    caso = next(c for c in run_bench.CASOS_FIJOS if c.archivo == "banqueta-alta.ai")
    assert caso.esperado == 1
    assert (caso.placa.width, caso.placa.height, caso.placa.grain_tolerance) == (1220.0, 2440.0, 180.0)
    assert caso.config.resolution == 1.0
    assert caso.config.effort == "normal"


def test_un_caso_fijo_corre_con_los_nucleos_de_la_maquina(tmp_path, monkeypatch):
    """No con un N fijo: doce procesos de 2,3 GB no entran en cualquier
    máquina, y con `MIN_BATCH` las variantes son las mismas con cualquier N
    de hasta doce."""
    import run_bench

    from nesting.engine import workers

    monkeypatch.setattr(workers, "machine", lambda: workers.Machine(cpus=8, cap=3, default=3))
    vistos = []
    monkeypatch.setattr(run_bench, "run_one",
                        lambda path, material, config, *rest: vistos.append(config.workers))
    (tmp_path / "banqueta-alta.ai").write_bytes(b"")

    run_bench.run_fixed(run_bench.CASOS_FIJOS[0], files_dir=tmp_path)

    assert vistos == [3]


def test_los_casos_fijos_se_buscan_en_la_carpeta_del_banco(tmp_path, monkeypatch, capsys):
    """Con `FILES_DIR` cambiado, un caso fijo que no está ahí se saltea: no
    se va a buscar a `bench/files`, donde la banqueta tardaría minutos."""
    import run_bench

    write_sample(tmp_path / "muestra.dxf")
    monkeypatch.setattr(run_bench, "FILES_DIR", tmp_path)
    medir = run_bench.run_one

    def solo_de_la_carpeta(path, *rest, **nombrados):
        assert path.parent == tmp_path, f"midió {path}, fuera de la carpeta del banco"
        return medir(path, *rest, **nombrados)

    monkeypatch.setattr(run_bench, "run_one", solo_de_la_carpeta)

    assert run_bench.main([]) == 0
    assert "banqueta-alta.ai        (falta en bench/files: se saltea)" in capsys.readouterr().out


def test_un_caso_fijo_ilegible_da_una_fila_de_error_y_no_tira_la_corrida(
    tmp_path, monkeypatch, capsys
):
    """Igual que un `*.dxf` roto: una fila ERROR, cuenta en los fallidos, y
    el banco sale con error sin haber explotado. Una carpeta con el nombre
    del archivo es un `OSError` al leerlo, como un archivo sin permisos."""
    import run_bench

    write_sample(tmp_path / "muestra.dxf")
    (tmp_path / "banqueta-alta.ai").mkdir()
    monkeypatch.setattr(run_bench, "FILES_DIR", tmp_path)

    exit_code = run_bench.main([])
    salida = capsys.readouterr()

    assert exit_code != 0
    assert "banqueta-alta.ai" in salida.out and "ERROR" in salida.out
    assert "1 de" in salida.err
