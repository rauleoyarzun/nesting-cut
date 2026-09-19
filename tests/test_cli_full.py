import re

import ezdxf
import pytest

from nesting.cli import main


def write_input(tmp_path, squares, units=4):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = units
    msp = doc.modelspace()
    for x0, y0, side in squares:
        msp.add_lwpolyline(
            [(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side)],
            close=True, dxfattribs={"color": 1},
        )
    path = tmp_path / "in.dxf"
    doc.saveas(path)
    return path


def catalogue(tmp_path):
    path = tmp_path / "materials.yaml"
    path.write_text("test:\n  placa: [1000, 1000]\n  tolerancia_veta: 180\n", encoding="utf-8")
    return path


def run(args):
    return main([str(a) for a in args])


def base(tmp_path, source, out):
    return [source, "--material", "test", "--materiales", catalogue(tmp_path), "-o", out]


@pytest.mark.parametrize("effort", ["rapido", "normal", "lento"])
def test_every_effort_level_runs(tmp_path, effort):
    source = write_input(tmp_path, [(0, 0, 200), (300, 0, 150)])
    out = tmp_path / f"{effort}.dxf"
    assert run(base(tmp_path, source, out) + ["--esfuerzo", effort]) == 0
    assert out.exists()


def test_an_unknown_effort_level_is_rejected_by_argparse(tmp_path):
    source = write_input(tmp_path, [(0, 0, 200)])
    with pytest.raises(SystemExit):
        run(base(tmp_path, source, tmp_path / "o.dxf") + ["--esfuerzo", "turbo"])


def test_preview_writes_a_png(tmp_path):
    source = write_input(tmp_path, [(0, 0, 200), (300, 0, 150)])
    preview = tmp_path / "vista.png"
    code = run(base(tmp_path, source, tmp_path / "o.dxf") + ["--preview", preview])

    assert code == 0
    assert preview.exists()


def test_no_preview_by_default(tmp_path):
    source = write_input(tmp_path, [(0, 0, 200)])
    run(base(tmp_path, source, tmp_path / "o.dxf"))
    assert not (tmp_path / "vista.png").exists()


def test_the_summary_reports_the_usable_offcut(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 200)])
    run(base(tmp_path, source, tmp_path / "o.dxf"))
    assert "sobrante" in capsys.readouterr().out.lower()


def test_the_summary_reports_parts_sheets_and_time(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 200), (300, 0, 200), (0, 300, 200)])
    run(base(tmp_path, source, tmp_path / "o.dxf") + ["--copias", "4"])

    output = capsys.readouterr().out
    assert "12 piezas" in output
    assert "placas" in output
    assert re.search(r"\d+\.\d+s", output), (
        f"no se encontro un tiempo en segundos (ej. '0.1s') en: {output!r}"
    )


def test_resolution_flag_changes_nothing_about_validity(tmp_path):
    source = write_input(tmp_path, [(0, 0, 200), (300, 0, 150)])
    assert run(base(tmp_path, source, tmp_path / "a.dxf") + ["--resolucion", "0.5"]) == 0
    assert run(base(tmp_path, source, tmp_path / "b.dxf") + ["--resolucion", "3"]) == 0


def test_mirroring_can_be_turned_off(tmp_path):
    source = write_input(tmp_path, [(0, 0, 200)])
    out = tmp_path / "o.dxf"
    assert run(base(tmp_path, source, out) + ["--sin-espejo", "--copias", "4"]) == 0
    assert out.exists()


def test_resolution_must_be_positive(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 200)])
    code = run(base(tmp_path, source, tmp_path / "o.dxf") + ["--resolucion", "0"])
    assert code == 1
    assert "--resolucion" in capsys.readouterr().err


def test_the_help_lists_every_flag(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    output = capsys.readouterr().out
    for flag in ("--material", "--copias", "--sep", "--borde", "--angulos",
                 "--esfuerzo", "--sin-espejo", "--resolucion", "--unidades",
                 "--tol-cierre", "--preview"):
        assert flag in output


# --- Hallazgo 1 y 2: errores de escritura de la previsualizacion ---
#
# Arreglos finales, punto 4: estos dos tests originalmente afirmaban que un
# fallo al escribir el PNG debia salir con codigo 1 y sin escribir nada --
# exactamente el comportamiento invertido que ese punto pide corregir. El
# DXF (lo que de verdad importa) ya se escribio con exito antes de intentar
# la previsualizacion, asi que ese fallo, cosmetico, se degrada a un aviso y
# el proceso termina con codigo 0, con el DXF en disco. Se actualizan en vez
# de borrarse porque codificaban el bug, no el comportamiento correcto.


def test_preview_whose_parent_is_a_file_downgrades_to_a_warning(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 200)])
    out = tmp_path / "o.dxf"
    blocker = tmp_path / "bloqueador"
    blocker.write_text("no soy un directorio", encoding="utf-8")
    preview = blocker / "vista.png"

    code = run(base(tmp_path, source, out) + ["--preview", preview])

    assert code == 0
    assert out.exists()
    assert not preview.exists()
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "aviso:" in captured.out
    assert str(preview) in captured.out
    assert "Escrito en" in captured.out


def test_preview_in_a_missing_directory_downgrades_to_a_warning(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 200)])
    out = tmp_path / "o.dxf"
    preview = tmp_path / "no_existe" / "vista.png"

    code = run(base(tmp_path, source, out) + ["--preview", preview])

    assert code == 0
    assert out.exists()
    assert not preview.parent.exists()
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "aviso:" in captured.out
    assert str(preview) in captured.out
    assert "Escrito en" in captured.out


def test_preview_with_a_valid_path_still_writes_the_png(tmp_path):
    source = write_input(tmp_path, [(0, 0, 200), (300, 0, 150)])
    preview = tmp_path / "vista.png"

    code = run(base(tmp_path, source, tmp_path / "o.dxf") + ["--preview", preview])

    assert code == 0
    assert preview.exists()
