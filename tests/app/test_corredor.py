"""El corredor: de un archivo de entrada a un DXF acomodado."""

import ezdxf
import pytest

from nesting.params import NestParams
from nesting_app import corredor
from nesting_app.archivos import Deposito


@pytest.fixture(autouse=True)
def catalogo_aislado(tmp_path, monkeypatch):
    from nesting_app import materials_store, rutas

    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")
    materials_store.leer()


@pytest.fixture
def deposito(tmp_path):
    return Deposito(tmp_path / "fuentes")


def dxf_con(tmp_path, cuadrados, unidades=4, nombre="entrada.dxf"):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = unidades
    msp = doc.modelspace()
    for x, y, lado in cuadrados:
        msp.add_lwpolyline(
            [(x, y), (x + lado, y), (x + lado, y + lado), (x, y + lado)], close=True
        )
    ruta = tmp_path / nombre
    doc.saveas(ruta)
    return ruta


def params(**cambios):
    return NestParams(material="mdf18", esfuerzo="rapido", **cambios)


def test_analizar_cuenta_las_piezas(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200), (300, 0, 150)]))

    analisis = corredor.analizar(fuente, unidades=None, tol_cierre=0.1)

    assert analisis.piezas == 2
    assert analisis.unidades == "mm"


def test_analizar_devuelve_los_descartes_dibujables(tmp_path, deposito):
    """Es lo que alimenta el link '3 descartes' de la pantalla principal."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (200, 0), (200, 200), (0, 200)], close=True)
    msp.add_line((400, 400), (412, 400))
    ruta = tmp_path / "sucio.dxf"
    doc.saveas(ruta)
    fuente = deposito.registrar_local(ruta)

    analisis = corredor.analizar(fuente, unidades=None, tol_cierre=0.1)

    assert len(analisis.descartes) == 1
    assert analisis.descartes[0]["motivo"] == "suelta"
    assert "12.000 mm" in analisis.descartes[0]["detalle"]


def test_analizar_un_archivo_sin_unidades_se_queja_de_forma_reconocible(tmp_path, deposito):
    """La interfaz atrapa justo este error para mostrar la pregunta con los
    cinco botones, así que tiene que poder distinguirlo de cualquier otro."""
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 100)], unidades=0))

    with pytest.raises(corredor.UnidadesNoDeclaradasError):
        corredor.analizar(fuente, unidades=None, tol_cierre=0.1)


def test_analizar_con_unidades_dadas_sigue_adelante(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 100)], unidades=0))

    analisis = corredor.analizar(fuente, unidades="mm", tol_cierre=0.1)

    assert analisis.piezas == 1


def test_acomodar_escribe_los_tres_archivos(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200), (300, 0, 150)]))
    salida = tmp_path / "trabajo"
    salida.mkdir()

    resultado = corredor.acomodar(fuente, params(), lambda a: True, salida)

    assert (salida / "salida.dxf").is_file()
    assert (salida / "preview.png").is_file()
    assert (salida / "diagnostico.png").is_file()
    assert resultado.placas == 1
    assert resultado.carpeta == salida


def test_acomodar_informa_el_sobrante(tmp_path, deposito):
    """Es el número que el usuario va a mirar primero: cuánta placa le queda
    entera para el próximo trabajo."""
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)]))
    salida = tmp_path / "t"
    salida.mkdir()

    resultado = corredor.acomodar(fuente, params(), lambda a: True, salida)

    assert resultado.sobrante_mm > 2000


def test_acomodar_llama_al_progreso(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200), (300, 0, 150)]))
    salida = tmp_path / "t"
    salida.mkdir()
    avances = []

    corredor.acomodar(fuente, params(), lambda a: avances.append(a) or True, salida)

    assert avances
    assert avances[0].totales == 2


def test_acomodar_respeta_las_copias(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)]))
    salida = tmp_path / "t"
    salida.mkdir()
    avances = []

    corredor.acomodar(fuente, params(copias=3), lambda a: avances.append(a) or True, salida)

    assert avances[0].totales == 3


def test_si_la_verificacion_falla_no_queda_ningun_dxf(tmp_path, deposito, monkeypatch):
    """Es la regla más dura del motor y no se ablanda acá: un layout no
    verificado no se escribe, porque ese archivo va a una fresadora."""
    from nesting.geometry.verify import Violation

    monkeypatch.setattr(
        corredor, "verify",
        lambda *a, **k: [
            Violation(
                kind="overlap", part_a=0, part_b=1, sheet=0,
                detail="las piezas 1 y 2 se pisan",
            )
        ],
    )
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)]))
    salida = tmp_path / "t"
    salida.mkdir()

    with pytest.raises(corredor.VerificacionFallidaError) as capturado:
        corredor.acomodar(fuente, params(), lambda a: True, salida)

    assert "se pisan" in capturado.value.violaciones[0]
    assert not (salida / "salida.dxf").exists()


def test_el_contorno_de_placa_se_descarta_igual_que_en_la_cli(tmp_path, deposito):
    """Los archivos reales del usuario traen dibujado el rectángulo de la
    placa. Si la interfaz no lo descartara, fallaría donde la CLI anda."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (1830, 0), (1830, 2600), (0, 2600)], close=True)
    msp.add_lwpolyline([(2000, 0), (2100, 0), (2100, 100), (2000, 100)], close=True)
    ruta = tmp_path / "con_placa.dxf"
    doc.saveas(ruta)
    fuente = deposito.registrar_local(ruta)
    salida = tmp_path / "t"
    salida.mkdir()

    resultado = corredor.acomodar(fuente, params(), lambda a: True, salida)

    assert resultado.placas == 1
