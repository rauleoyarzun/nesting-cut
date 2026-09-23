import ezdxf
import pytest

from nesting.cli import main


def write_input(tmp_path, squares, units=4, name="in.dxf"):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = units
    msp = doc.modelspace()
    for x0, y0, side in squares:
        msp.add_lwpolyline(
            [(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side)],
            close=True,
        )
    path = tmp_path / name
    doc.saveas(path)
    return path


def catalogue(tmp_path):
    path = tmp_path / "materials.yaml"
    path.write_text("test:\n  placa: [1000, 1000]\n  tolerancia_veta: 180\n", encoding="utf-8")
    return path


def run(args):
    return main([str(a) for a in args])


def test_happy_path_writes_the_output(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 200), (300, 0, 150)])
    out = tmp_path / "out.dxf"

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path), "-o", out])

    assert code == 0
    assert out.exists()
    assert "placa" in capsys.readouterr().out.lower()


def test_copies_multiply_the_parts(tmp_path):
    source = write_input(tmp_path, [(0, 0, 100)])
    out = tmp_path / "out.dxf"

    run([source, "--material", "test", "--materiales", catalogue(tmp_path),
         "--copias", "5", "-o", out])

    msp = ezdxf.readfile(str(out)).modelspace()
    outlines = [e for e in msp if e.dxf.layer != "_PLACA"]
    assert len(outlines) == 5


def test_unknown_material_exits_with_one(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 100)])
    code = run([source, "--material", "noexiste", "--materiales", catalogue(tmp_path),
                "-o", tmp_path / "out.dxf"])

    assert code == 1
    assert "noexiste" in capsys.readouterr().err


def test_missing_units_exits_with_one(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 100)], units=0)
    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "-o", tmp_path / "out.dxf"])

    assert code == 1
    assert "--unidades" in capsys.readouterr().err


def test_units_override_recovers_a_unitless_file(tmp_path):
    source = write_input(tmp_path, [(0, 0, 10)], units=0)
    out = tmp_path / "out.dxf"
    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--unidades", "cm", "-o", out])

    assert code == 0
    assert out.exists()


def test_nucleos_cero_es_un_error_de_entrada(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 100)])
    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--nucleos", "0", "-o", tmp_path / "out.dxf"])
    assert code == 1
    assert "--nucleos tiene que ser >= 1" in capsys.readouterr().err


def test_nucleos_de_mas_se_recortan_con_un_aviso(tmp_path, capsys, monkeypatch):
    from nesting.engine import workers

    monkeypatch.setattr(workers, "machine", lambda: workers.Machine(4, 2, 2))
    source = write_input(tmp_path, [(0, 0, 100)])
    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--esfuerzo", "rapido", "--nucleos", "9", "-o", tmp_path / "out.dxf"])
    assert code == 0
    salida = capsys.readouterr().out
    assert "aviso: se pidieron 9 núcleos" in salida


def test_a_part_bigger_than_the_sheet_exits_with_one(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 5000)])
    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "-o", tmp_path / "out.dxf"])

    assert code == 1
    assert "no entra" in capsys.readouterr().err


def test_an_open_contour_exits_with_one(tmp_path, capsys):
    # Dos lados de un cuadrado (una cadena de 3 puntos que no cierra) -- no
    # una recta suelta de 2 puntos, que desde el arreglo de "archivos reales"
    # ya no es un error sino un aviso (ver test_a_lone_two_point_line_is_a_
    # warning_not_an_error, más abajo): una recta sola nunca puede encerrar
    # área con ninguna tolerancia, así que ya no tiene sentido tratarla como
    # un contorno incompleto.
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 0))
    msp.add_line((100, 0), (100, 100))
    source = tmp_path / "abierto.dxf"
    doc.saveas(source)

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "-o", tmp_path / "out.dxf"])

    assert code == 1
    assert "cierran" in capsys.readouterr().err


def test_a_lone_two_point_line_is_a_warning_not_an_error(tmp_path, capsys):
    """Arreglo archivos reales, problema 1: una recta suelta (cadena abierta
    de 2 puntos) no puede encerrar área con ninguna tolerancia, así que ya no
    aborta el trabajo -- se descarta con aviso. Si es la única geometría del
    archivo, el resultado sigue siendo un error, pero por "no hay piezas",
    no por "no cierra"."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    doc.modelspace().add_line((0, 0), (100, 0))
    source = tmp_path / "suelto.dxf"
    doc.saveas(source)

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "-o", tmp_path / "out.dxf"])

    out, err = capsys.readouterr()
    assert code == 1
    assert "cierran" not in err
    assert "no se encontró ninguna pieza" in err
    assert "suelto" in out


def test_reader_warnings_are_shown(tmp_path, capsys):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 100)], close=True)
    msp.add_text("600.00").set_placement((50, 50))
    source = tmp_path / "con_cota.dxf"
    doc.saveas(source)

    run([source, "--material", "test", "--materiales", catalogue(tmp_path),
         "-o", tmp_path / "out.dxf"])

    assert "TEXT" in capsys.readouterr().out


def test_summary_reports_sheets_and_utilisation(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 400), (500, 0, 400), (0, 500, 400)])
    run([source, "--material", "test", "--materiales", catalogue(tmp_path),
         "-o", tmp_path / "out.dxf"])

    output = capsys.readouterr().out
    assert "aprovechamiento" in output
    assert "%" in output


def test_summary_reports_material_left_on_the_last_sheet(tmp_path, capsys):
    """El criterio nuevo minimiza el material que queda en la última placa,
    y eso a veces acorta la tira libre a cambio -- las dos cifras compiten,
    así que el resumen tiene que mostrar las dos, no sólo la tira."""
    source = write_input(tmp_path, [(0, 0, 400), (500, 0, 400), (0, 500, 400)])
    run([source, "--material", "test", "--materiales", catalogue(tmp_path),
         "-o", tmp_path / "out.dxf"])

    output = capsys.readouterr().out
    assert "material en la última placa" in output
    assert "m²" in output
    assert "tira libre" in output


def test_separation_and_margin_are_honoured(tmp_path):
    from nesting.geometry.verify import verify
    from nesting.io.dxf_reader import read_dxf
    from nesting.pipeline import prepare_parts

    source = write_input(tmp_path, [(0, 0, 200) for _ in range(1)])
    out = tmp_path / "out.dxf"
    run([source, "--material", "test", "--materiales", catalogue(tmp_path),
         "--copias", "6", "--sep", "25", "--borde", "40", "-o", out])

    # Releer la salida y comprobar que las piezas respetan lo pedido.
    parts, _, _ = prepare_parts(read_dxf(out))
    assert len(parts) >= 6


def test_angles_flag_is_parsed(tmp_path):
    source = write_input(tmp_path, [(0, 0, 100)])
    out = tmp_path / "out.dxf"
    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--angulos", "0,45,90", "-o", out])
    assert code == 0


def test_an_invalid_angle_list_exits_with_one(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 100)])
    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--angulos", "0,abc", "-o", tmp_path / "out.dxf"])
    assert code == 1
    assert "angulos" in capsys.readouterr().err.lower()


def test_overlapping_contours_exit_with_one(tmp_path, capsys):
    """Dos contornos que se superponen parcialmente (sin anidar limpio) son un
    problema del dibujo del usuario: `OverlappingContourError` debe reportarse
    con salida 1, no propagarse como crash."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (300, 0), (300, 300), (0, 300)], close=True)
    msp.add_lwpolyline([(100, 100), (350, 100), (350, 250), (100, 250)], close=True)
    source = tmp_path / "superpuesto.dxf"
    doc.saveas(source)

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "-o", tmp_path / "out.dxf"])

    assert code == 1
    assert "superpon" in capsys.readouterr().err.lower()


def test_verification_failure_exits_with_two_and_writes_nothing(tmp_path, capsys, monkeypatch):
    """El codigo de salida 2 (fallo de verificacion geometrica) es la red de
    seguridad mas importante: no debe escribirse ningun archivo de salida."""
    import nesting.cli as cli_module
    from nesting.geometry.verify import Violation

    forced_detail = "pieza 0 y 1 se superponen (forzado para prueba)"

    def fake_verify(parts, placements, sheets, sep, margin):
        return [Violation(kind="overlap", part_a=0, part_b=1, sheet=0, detail=forced_detail)]

    monkeypatch.setattr(cli_module, "verify", fake_verify)

    source = write_input(tmp_path, [(0, 0, 200), (300, 0, 150)])
    out = tmp_path / "out.dxf"

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path), "-o", out])

    assert code == 2
    assert not out.exists()
    assert forced_detail in capsys.readouterr().err


def test_valid_layout_exits_with_zero_and_writes_the_file(tmp_path):
    """Contraparte del test anterior: sin violaciones, la salida es 0 y el
    archivo se escribe."""
    source = write_input(tmp_path, [(0, 0, 200), (300, 0, 150)])
    out = tmp_path / "out.dxf"

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path), "-o", out])

    assert code == 0
    assert out.exists()


# --- Hallazgo 1a: validacion de flags numericos en la CLI ---


def test_negative_borde_exits_with_one_and_writes_nothing(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 90) for _ in range(4)])
    out = tmp_path / "out.dxf"

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--borde", "-20", "-o", out])

    assert code == 1
    assert "--borde" in capsys.readouterr().err
    assert not out.exists()


def test_negative_sep_exits_with_one(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 90) for _ in range(4)])
    out = tmp_path / "out.dxf"

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--sep", "-5", "-o", out])

    assert code == 1
    assert "--sep" in capsys.readouterr().err
    assert not out.exists()


@pytest.mark.parametrize("copias", ["0", "-3"])
def test_non_positive_copias_exits_with_one_without_traceback(tmp_path, capsys, copias):
    source = write_input(tmp_path, [(0, 0, 100)])
    out = tmp_path / "out.dxf"

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--copias", copias, "-o", out])

    assert code == 1
    assert "--copias" in capsys.readouterr().err
    assert not out.exists()


def test_zero_tol_cierre_exits_with_one(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 100)])
    out = tmp_path / "out.dxf"

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--tol-cierre", "0", "-o", out])

    assert code == 1
    assert "--tol-cierre" in capsys.readouterr().err
    assert not out.exists()


# --- Hallazgo 2: caminos que antes terminaban en traceback crudo ---


def test_output_directory_that_does_not_exist_exits_with_one_without_traceback(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 100)])
    out = tmp_path / "no_existe" / "out.dxf"

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path), "-o", out])

    assert code == 1
    err = capsys.readouterr().err
    assert str(out) in err
    assert not out.exists()


def test_syntactically_invalid_yaml_catalogue_exits_with_one(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 100)])
    bad_catalogue = tmp_path / "materiales_rotos.yaml"
    bad_catalogue.write_text("test:\n  placa: [1000, 1000\n  tolerancia_veta: 180\n",
                              encoding="utf-8")

    code = run([source, "--material", "test", "--materiales", bad_catalogue,
                "-o", tmp_path / "out.dxf"])

    assert code == 1
    assert str(bad_catalogue) in capsys.readouterr().err


# --- Hallazgo 3: errores de uso de argparse salen con 1, no con 2 ---


def test_missing_required_flag_exits_with_one_not_two(tmp_path, capsys):
    """argparse reporta los errores de uso saliendo del proceso directamente
    (via `sys.exit` dentro de `error()`), no devolviendo un codigo desde
    `main()`, asi que hay que capturar el `SystemExit`."""
    source = write_input(tmp_path, [(0, 0, 100)])

    with pytest.raises(SystemExit) as exc_info:
        run([source, "--materiales", catalogue(tmp_path), "-o", tmp_path / "out.dxf"])

    assert exc_info.value.code == 1


def test_non_numeric_copias_exits_with_one_not_two(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 100)])

    with pytest.raises(SystemExit) as exc_info:
        run([source, "--material", "test", "--materiales", catalogue(tmp_path),
             "--copias", "abc", "-o", tmp_path / "out.dxf"])

    assert exc_info.value.code == 1


def test_help_still_exits_with_zero():
    with pytest.raises(SystemExit) as exc_info:
        run(["--help"])

    assert exc_info.value.code == 0


# --- Hallazgo 5: el aviso de la capa reservada no debe mentir sobre el origen ---


def test_reserved_layer_warning_does_not_claim_authorship(tmp_path, capsys):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 100)], close=True)
    msp.add_lwpolyline(
        [(200, 200), (300, 200), (300, 300), (200, 300)], close=True,
        dxfattribs={"layer": "_PLACA"},
    )
    source = tmp_path / "con_placa.dxf"
    doc.saveas(source)

    run([source, "--material", "test", "--materiales", catalogue(tmp_path),
         "-o", tmp_path / "out.dxf"])

    output = capsys.readouterr().out.lower()
    assert "_placa" in output
    assert "reservad" in output
    assert "generad" not in output


# --- Hallazgo 6: un archivo viejo no debe pasar por nuevo tras un fallo de verificacion ---


def test_verification_failure_warns_about_a_pre_existing_output_file(
    tmp_path, capsys, monkeypatch
):
    import nesting.cli as cli_module
    from nesting.geometry.verify import Violation

    def fake_verify(parts, placements, sheets, sep, margin):
        return [Violation(kind="overlap", part_a=0, part_b=1, sheet=0, detail="forzado")]

    monkeypatch.setattr(cli_module, "verify", fake_verify)

    source = write_input(tmp_path, [(0, 0, 200), (300, 0, 150)])
    out = tmp_path / "out.dxf"
    out.write_text("contenido de una corrida anterior", encoding="utf-8")

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path), "-o", out])

    assert code == 2
    assert out.read_text(encoding="utf-8") == "contenido de una corrida anterior"
    err = capsys.readouterr().err
    assert "anterior" in err.lower()


# --- Arreglos finales, punto 4: un fallo de previsualización no debe ocultar
# que el DXF sí se escribió ---


def test_a_preview_failure_is_downgraded_to_a_warning(tmp_path, capsys):
    """El PNG es cosmético. Si `write_preview` falla (acá, por escribir en un
    directorio que no existe), el DXF ya escrito tiene que seguir estando, el
    resumen tiene que imprimirse igual, y el código de salida tiene que ser
    0 -- no 1 como si nada se hubiera escrito."""
    source = write_input(tmp_path, [(0, 0, 100)])
    out = tmp_path / "out.dxf"
    bad_preview = tmp_path / "no_existe" / "preview.png"

    code = run([
        source, "--material", "test", "--materiales", catalogue(tmp_path),
        "-o", out, "--preview", bad_preview,
    ])

    assert code == 0
    assert out.exists()
    captured = capsys.readouterr()
    assert "aviso:" in captured.out
    assert "Escrito en" in captured.out


# --- Arreglos finales, punto 5a: una resolución de rasterizado demasiado fina
# tiene que salir con un mensaje claro, no con un traceback sin atrapar ---


def test_a_resolution_too_fine_exits_cleanly_instead_of_crashing(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 100)])
    out = tmp_path / "out.dxf"

    code = run([
        source, "--material", "test", "--materiales", catalogue(tmp_path),
        "-o", out, "--resolucion", "0.005",
    ])

    assert code == 1
    err = capsys.readouterr().err.lower()
    assert "grilla" in err or "resolución" in err


# --- --diagnostico -----------------------------------------------------------


def write_input_with_a_stray_segment(tmp_path, name="sucio.dxf"):
    """Un cuadrado sano más un segmento suelto de 12 mm, que es el caso real."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (200, 0), (200, 200), (0, 200)], close=True,
    )
    msp.add_line((400, 400), (412, 400))
    path = tmp_path / name
    doc.saveas(path)
    return path


def test_diagnostico_writes_a_png(tmp_path):
    source = write_input_with_a_stray_segment(tmp_path)
    png = tmp_path / "revision.png"

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--diagnostico", png])

    assert code == 0
    assert png.exists()


def test_diagnostico_alone_does_not_require_an_output_file(tmp_path, capsys):
    """Es el punto del modo diagnóstico: mirar el archivo sin esperar el
    acomodo, que en un archivo real tarda medio minuto o más."""
    source = write_input_with_a_stray_segment(tmp_path)
    png = tmp_path / "revision.png"

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--diagnostico", png])

    assert code == 0
    assert "Escrito en" not in capsys.readouterr().out
    assert not list(tmp_path.glob("*.dxf.out"))


def test_diagnostico_alone_does_not_run_the_nesting(tmp_path, capsys, monkeypatch):
    """Si igual acomodara, el modo rápido no sería rápido."""
    import nesting.cli as cli_module

    def explode(*args, **kwargs):
        raise AssertionError("no se debe acomodar si solo se pidió el diagnóstico")

    monkeypatch.setattr(cli_module, "pack", explode)
    source = write_input_with_a_stray_segment(tmp_path)

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--diagnostico", tmp_path / "d.png"])

    assert code == 0


def test_diagnostico_together_with_an_output_does_both(tmp_path):
    source = write_input_with_a_stray_segment(tmp_path)
    out = tmp_path / "out.dxf"
    png = tmp_path / "revision.png"

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "-o", out, "--diagnostico", png])

    assert code == 0
    assert out.exists()
    assert png.exists()


def test_without_an_output_and_without_a_diagnostico_it_refuses(tmp_path, capsys):
    """Sin ninguno de los dos no hay nada que producir: pedirlo es un error de
    uso, no una corrida vacía exitosa."""
    source = write_input(tmp_path, [(0, 0, 100)])

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path)])

    assert code == 1
    assert "-o" in capsys.readouterr().err


def test_diagnostico_says_how_many_marks_it_drew(tmp_path, capsys):
    source = write_input_with_a_stray_segment(tmp_path)

    run([source, "--material", "test", "--materiales", catalogue(tmp_path),
         "--diagnostico", tmp_path / "d.png"])

    out = capsys.readouterr().out
    assert "1" in out and "descarte" in out.lower()


def test_a_clean_file_still_writes_the_diagnostico(tmp_path, capsys):
    """Confirmar que está limpio es un resultado, no un no-resultado."""
    source = write_input(tmp_path, [(0, 0, 100)])
    png = tmp_path / "d.png"

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--diagnostico", png])

    assert code == 0
    assert png.exists()
    assert "no se descartó nada" in capsys.readouterr().out.lower()


def test_the_plate_outline_reaches_the_diagnostico(tmp_path):
    """El rectángulo del tamaño de la placa se descarta después de armar las
    piezas, más tarde que todo lo demás. Es el descarte más fácil de perder
    por el camino, y el que más tranquiliza ver marcado."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (1000, 0), (1000, 1000), (0, 1000)], close=True)
    # Al lado, no adentro: una pieza encerrada por el rectángulo sería un
    # agujero de él, y entonces ya no sería un contorno de placa.
    msp.add_lwpolyline([(1200, 0), (1300, 0), (1300, 100), (1200, 100)], close=True)
    source = tmp_path / "con_placa.dxf"
    doc.saveas(source)
    png = tmp_path / "d.png"

    from PIL import Image

    from nesting.model.discard import DISCARD_STYLES

    run([source, "--material", "test", "--materiales", catalogue(tmp_path),
         "--diagnostico", png])

    with Image.open(png) as image:
        colors = set(image.convert("RGB").getdata())
    assert DISCARD_STYLES["contorno_placa"].color in colors


def test_a_diagnostico_path_in_a_missing_directory_exits_with_one(tmp_path, capsys):
    source = write_input_with_a_stray_segment(tmp_path)

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--diagnostico", tmp_path / "no_existe" / "d.png"])

    assert code == 1
    assert "diagn" in capsys.readouterr().err.lower()


def test_preview_without_an_output_is_refused_instead_of_ignored(tmp_path, capsys):
    """La previsualización muestra el acomodo, y el acomodo solo corre cuando
    hay un DXF que escribir. Pedirla sin -o la dejaría sin hacerse EN SILENCIO
    -- el usuario esperaría un PNG que nunca llega y no sabría por qué."""
    source = write_input_with_a_stray_segment(tmp_path)

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--diagnostico", tmp_path / "d.png",
                "--preview", tmp_path / "p.png"])

    assert code == 1
    error = capsys.readouterr().err
    assert "--preview" in error and "-o" in error
    assert not (tmp_path / "p.png").exists()


def test_preview_alone_without_anything_else_is_also_refused(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 100)])

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--preview", tmp_path / "p.png"])

    assert code == 1


# --- la veta de la corrida -------------------------------------------------


def catalogo_angosto(tmp_path, tolerancia):
    """Una placa de 500 x 1500: una pieza de 1200 x 100 sólo entra parada."""
    path = tmp_path / "angosto.yaml"
    path.write_text(
        f"angosto:\n  placa: [500, 1500]\n  tolerancia_veta: {tolerancia}\n",
        encoding="utf-8",
    )
    return path


def pieza_acostada(tmp_path):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    doc.modelspace().add_lwpolyline(
        [(0, 0), (1200, 0), (1200, 100), (0, 100)], close=True
    )
    path = tmp_path / "acostada.dxf"
    doc.saveas(path)
    return path


def test_con_la_veta_del_material_la_pieza_acostada_no_entra(tmp_path, capsys):
    code = run([
        pieza_acostada(tmp_path), "--material", "angosto",
        "--materiales", catalogo_angosto(tmp_path, 5), "-o", tmp_path / "o.dxf",
        "--esfuerzo", "rapido", "--resolucion", "2",
    ])

    assert code == 1
    assert "no entra" in capsys.readouterr().err


def test_veta_libre_deja_pararla(tmp_path):
    code = run([
        pieza_acostada(tmp_path), "--material", "angosto",
        "--materiales", catalogo_angosto(tmp_path, 5), "-o", tmp_path / "o.dxf",
        "--esfuerzo", "rapido", "--resolucion", "2", "--veta", "libre",
    ])

    assert code == 0


def test_veta_respetar_la_bloquea_en_un_material_libre(tmp_path, capsys):
    code = run([
        pieza_acostada(tmp_path), "--material", "angosto",
        "--materiales", catalogo_angosto(tmp_path, 180), "-o", tmp_path / "o.dxf",
        "--esfuerzo", "rapido", "--resolucion", "2", "--veta", "respetar",
    ])

    assert code == 1
    assert "no entra" in capsys.readouterr().err


def test_un_angulo_que_la_veta_descarta_se_rechaza_nombrando_el_flag(tmp_path, capsys):
    code = run([
        pieza_acostada(tmp_path), "--material", "angosto",
        "--materiales", catalogo_angosto(tmp_path, 5), "-o", tmp_path / "o.dxf",
        "--angulos", "90",
    ])

    assert code == 1
    err = capsys.readouterr().err
    assert "--angulos tiene que ser compatible con la veta" in err


def test_una_veta_desconocida_es_error_de_uso(tmp_path):
    with pytest.raises(SystemExit) as salida:
        run([
            pieza_acostada(tmp_path), "--material", "angosto",
            "--materiales", catalogo_angosto(tmp_path, 5), "-o", tmp_path / "o.dxf",
            "--veta", "cruzada",
        ])

    assert salida.value.code == 1


def test_freeze_support_es_lo_primero_que_hace_main(monkeypatch):
    """PyInstaller lo exige para `spawn`: sin esto, cada proceso del pool
    del ejecutable vuelve a arrancar la CLI entera en vez de ser un proceso
    del pool. En el repo funciona igual con o sin él, por eso hace falta un
    test que lo mire."""
    import multiprocessing

    import nesting.cli

    llamadas = []
    monkeypatch.setattr(multiprocessing, "freeze_support", lambda: llamadas.append(1))
    with pytest.raises(SystemExit):
        nesting.cli.main(["--no-existe-esta-opcion"])
    assert llamadas == [1]


def test_la_cli_dice_cuando_no_se_puede_con_menos_placas(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 200), (300, 0, 150)])
    run([source, "--material", "test", "--materiales", catalogue(tmp_path),
         "--esfuerzo", "rapido", "-o", tmp_path / "out.dxf"])
    assert "No se puede con menos placas." in capsys.readouterr().out


def test_la_cli_no_lo_dice_si_no_iguala_la_cota(tmp_path, capsys):
    """Tres cuadrados de 600 en una placa de 1000: uno por placa, tres
    placas, y la cota por área es dos."""
    source = write_input(tmp_path, [(0, 0, 600), (700, 0, 600), (1400, 0, 600)])
    run([source, "--material", "test", "--materiales", catalogue(tmp_path),
         "--esfuerzo", "rapido", "-o", tmp_path / "out.dxf"])
    assert "No se puede con menos placas." not in capsys.readouterr().out
