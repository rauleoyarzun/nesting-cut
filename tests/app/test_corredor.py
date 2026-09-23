"""El corredor: de un archivo de entrada a un DXF acomodado."""

import time

import ezdxf
import pytest

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import initial_forecast
from nesting.model.material import Material
from nesting.model.part import Part
from nesting.model.sheet import SheetSupply
from nesting.params import NestParams, Recorte
from nesting_app import corredor, materials_store
from nesting_app.archivos import Deposito
from nesting_app.jobs import Estado, Registro


@pytest.fixture(autouse=True)
def catalogo_aislado(tmp_path, monkeypatch):
    from nesting_app import materials_store, rutas

    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")
    materials_store.leer()


@pytest.fixture
def deposito(tmp_path):
    return Deposito(tmp_path / "fuentes")


def dxf_con_contorno_de_placa(tmp_path):
    """El mismo archivo que usa el test de más abajo para el descarte: trae
    dibujado, además de una pieza, el rectángulo del tamaño de la placa."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (1830, 0), (1830, 2600), (0, 2600)], close=True)
    msp.add_lwpolyline([(2000, 0), (2100, 0), (2100, 100), (2000, 100)], close=True)
    ruta = tmp_path / "con_placa.dxf"
    doc.saveas(ruta)
    return ruta


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


def test_analizar_deja_la_revision_dibujada(tmp_path, deposito):
    """El pedido original del usuario: saber CUÁLES son los que se
    descartaron. Mientras esa imagen sólo la escribía `acomodar`, había que
    esperar hasta nueve minutos para verla -- y para ese entonces la decisión
    de corregir el archivo original ya no servía de nada."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (200, 0), (200, 200), (0, 200)], close=True)
    msp.add_line((400, 400), (412, 400))
    ruta = tmp_path / "sucio.dxf"
    doc.saveas(ruta)
    fuente = deposito.registrar_local(ruta)

    corredor.analizar(fuente, unidades=None, tol_cierre=0.1)

    imagen = fuente.carpeta / corredor.NOMBRE_DIAGNOSTICO
    assert imagen.is_file()
    assert imagen.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", "no es un PNG"


def test_analizar_de_nuevo_redibuja_la_revision(tmp_path, deposito):
    """La tolerancia de cierre es un control de la pantalla: cambiarla cambia
    qué se descarta. Si la imagen quedara de la corrida anterior, el usuario
    estaría mirando los descartes de una tolerancia que ya no es la suya."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (200, 0), (200, 200), (0, 200)], close=True)
    ruta = tmp_path / "limpio.dxf"
    doc.saveas(ruta)
    fuente = deposito.registrar_local(ruta)
    imagen = fuente.carpeta / corredor.NOMBRE_DIAGNOSTICO

    corredor.analizar(fuente, unidades=None, tol_cierre=0.1)
    primera = imagen.stat().st_mtime_ns
    imagen.write_bytes(b"basura")

    corredor.analizar(fuente, unidades=None, tol_cierre=0.5)

    assert imagen.read_bytes() != b"basura", "la revisión quedó de la vez anterior"
    assert primera  # el primer análisis sí la había escrito


def test_si_no_se_puede_dibujar_la_revision_el_analisis_igual_contesta(
    tmp_path, deposito, monkeypatch
):
    """Las cuentas del análisis son la respuesta; la imagen es una ayuda.
    Perder las dos porque no se pudo escribir un PNG sería peor que
    quedarse sin la imagen, así que el fallo se cuenta como aviso."""
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)]))

    def explota(*args, **kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr(corredor, "write_diagnostic", explota)

    analisis = corredor.analizar(fuente, unidades=None, tol_cierre=0.1)

    assert analisis.piezas == 1
    assert any("no se pudo dibujar la revisión" in a for a in analisis.avisos)


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


def test_acomodar_informa_el_material_que_queda_en_la_ultima_placa(tmp_path, deposito):
    """Las dos cifras que compiten van juntas: cuánto material quedó en la
    última placa y qué tira libre dejó. El criterio nuevo puede acortar la
    tira para bajar el material, así que el usuario tiene que ver las dos."""
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)]))
    salida = tmp_path / "t"
    salida.mkdir()

    resultado = corredor.acomodar(fuente, params(), lambda a: True, salida)

    assert resultado.material_ultima_placa_m2 > 0.0
    assert resultado.sobrante_mm > 0.0


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
    fuente = deposito.registrar_local(dxf_con_contorno_de_placa(tmp_path))
    salida = tmp_path / "t"
    salida.mkdir()

    resultado = corredor.acomodar(fuente, params(), lambda a: True, salida)

    assert resultado.placas == 1


def test_el_contorno_de_placa_genera_un_aviso(tmp_path, deposito):
    """El aviso del rectángulo descartado sólo puede generarse adentro de
    `acomodar()` -- necesita las medidas del material -- y es lo que le
    explica al usuario, en la revisión, por qué ese rectángulo no aparece
    como pieza."""
    fuente = deposito.registrar_local(dxf_con_contorno_de_placa(tmp_path))
    salida = tmp_path / "t"
    salida.mkdir()

    resultado = corredor.acomodar(fuente, params(), lambda a: True, salida)

    assert any("rectángulo" in a and "placa" in a for a in resultado.avisos), (
        f"esperaba un aviso sobre el contorno descartado, avisos={resultado.avisos!r}"
    )


def test_el_aviso_del_contorno_de_placa_llega_hasta_el_trabajo(tmp_path, deposito):
    """El aviso solo se puede generar adentro de `acomodar()` -- necesita
    las medidas del material, que `analizar()` ni siquiera conoce --, así
    que este es el único punto donde puede probarse que de verdad llega
    hasta `Trabajo.avisos`, que es lo que la interfaz puede leer."""
    fuente = deposito.registrar_local(dxf_con_contorno_de_placa(tmp_path))
    registro = Registro(tmp_path / "trabajos")
    try:
        trabajo = registro.crear(fuente, params(), corredor.acomodar)
        fin = time.monotonic() + 10
        while trabajo.estado not in (Estado.LISTO, Estado.ERROR, Estado.CANCELADO):
            if time.monotonic() > fin:
                raise AssertionError(f"el trabajo quedó en {trabajo.estado}")
            time.sleep(0.01)

        assert trabajo.estado == Estado.LISTO
        assert any("rectángulo" in a and "placa" in a for a in trabajo.avisos), (
            f"esperaba que el aviso llegara a trabajo.avisos, "
            f"avisos={trabajo.avisos!r}"
        )
    finally:
        registro.cerrar()


def test_un_esfuerzo_desconocido_no_pierde_los_avisos_ya_calculados(
    tmp_path, deposito
):
    """`pack()` puede fallar por muchos motivos (esfuerzo desconocido, pieza
    demasiado grande, resolución inválida) y ninguno de ellos tiene por qué
    pasar por `_con_avisos` a mano: el envoltorio único de `acomodar()` los
    tiene que atrapar a todos. Este es el caso más barato de armar, con un
    archivo que además trae el rectángulo de la placa para probar que ese
    aviso -- que sólo se genera adentro de `acomodar()` -- no se pierde."""
    fuente = deposito.registrar_local(dxf_con_contorno_de_placa(tmp_path))
    salida = tmp_path / "t"
    salida.mkdir()

    with pytest.raises(Exception) as capturado:
        corredor.acomodar(
            fuente,
            NestParams(material="mdf18", esfuerzo="no-existe-este-esfuerzo"),
            lambda a: True,
            salida,
        )

    avisos = getattr(capturado.value, "avisos", ())
    assert any("rectángulo" in a and "placa" in a for a in avisos), (
        f"esperaba que el aviso del contorno de placa viajara colgado del "
        f"error, avisos={avisos!r}"
    )


def test_write_preview_que_falla_no_impide_terminar_bien(tmp_path, deposito, monkeypatch):
    """Igual que en la CLI: si falla la previsualización, el DXF -- lo que
    de verdad va a la fresadora -- ya se escribió con éxito, así que abortar
    acá le haría creer al usuario que no salió nada."""
    def preview_roto(*a, **k):
        raise ValueError("no se pudo dibujar la previsualización")

    monkeypatch.setattr(corredor, "write_preview", preview_roto)
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200), (300, 0, 150)]))
    salida = tmp_path / "t"
    salida.mkdir()

    resultado = corredor.acomodar(fuente, params(), lambda a: True, salida)

    assert (salida / "salida.dxf").is_file()
    assert not (salida / "preview.png").exists()
    assert any("previsualización" in a for a in resultado.avisos), (
        f"esperaba un aviso explicando que la previsualización falló, "
        f"avisos={resultado.avisos!r}"
    )


def dxf_contorno_abierto(tmp_path):
    """Tres lados de un cuadrado, como líneas sueltas: el contorno no
    cierra, con un hueco bien por encima de cualquier `tol_cierre` de
    prueba."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    msp = doc.modelspace()
    c = [(0, 0), (200, 0), (200, 200), (0, 200)]
    for i in range(3):
        msp.add_line(c[i], c[i + 1])
    ruta = tmp_path / "abierto.dxf"
    doc.saveas(ruta)
    return ruta


def test_analizar_traduce_el_flag_de_la_cli_al_control_de_la_interfaz(tmp_path, deposito):
    """`nesting/pipeline.py` manda a `--tol-cierre`, que es lo correcto para
    quien lo lee desde una terminal (`tests/test_pipeline.py` y
    `tests/test_cli.py` verifican justamente eso, sin tocar). Pero ese mismo
    mensaje, mostrado tal cual en la interfaz gráfica, manda a un flag que
    ahí no existe: el control se llama "Tolerancia de cierre". La
    traducción tiene que pasar del lado de la aplicación, sin que el motor
    deje de nombrar su propio flag."""
    fuente = deposito.registrar_local(dxf_contorno_abierto(tmp_path))

    with pytest.raises(Exception) as capturado:
        corredor.analizar(fuente, unidades=None, tol_cierre=0.1)

    mensaje = str(capturado.value)
    assert "--tol-cierre" not in mensaje
    assert "Tolerancia de cierre" in mensaje


def test_acomodar_tambien_traduce_el_flag_de_la_cli(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_contorno_abierto(tmp_path))
    salida = tmp_path / "t"
    salida.mkdir()

    with pytest.raises(Exception) as capturado:
        corredor.acomodar(fuente, params(), lambda a: True, salida)

    assert "--tol-cierre" not in str(capturado.value)


def test_acomodar_con_un_material_que_desaparecio_de_la_cola_da_un_error_del_usuario(
    tmp_path, deposito
):
    """La API prechequea que el material exista al crear el trabajo, pero
    ese chequeo y esta lectura -- que corre después, en el hilo trabajador --
    no son atómicos: el material puede borrarse de la pantalla de
    materiales mientras el trabajo espera en la cola. Antes, `materiales[...]`
    crudo tiraba un `KeyError`, que `jobs.ERRORES_DEL_USUARIO` excluye a
    propósito por ambiguo -- así que esto terminaba clasificado como "se
    rompió el programa", con el repr pelado de una clave de diccionario."""
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)]))
    salida = tmp_path / "t"
    salida.mkdir()

    with pytest.raises(materials_store.MaterialDesconocidoError) as capturado:
        corredor.acomodar(
            fuente,
            NestParams(material="fantasma", esfuerzo="rapido"),
            lambda a: True,
            salida,
        )

    assert "fantasma" in str(capturado.value)


def test_el_resultado_cuenta_cuantos_recortes_se_usaron(tmp_path, deposito):
    """El reparto lo cuenta el motor, que ya sabe qué placa fue cada una.
    Si lo recontara la pantalla, serían dos fuentes de verdad para el mismo
    número."""
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200), (300, 0, 200)]))
    salida = tmp_path / "t"
    salida.mkdir()

    resultado = corredor.acomodar(
        fuente,
        params(recortes=(Recorte(700.0, 700.0),), resolucion=4.0),
        lambda a: True,
        salida,
    )

    assert resultado.placas == 1
    assert resultado.recortes_usados == 1


def test_sin_recortes_el_reparto_es_cero(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)]))
    salida = tmp_path / "t"
    salida.mkdir()

    resultado = corredor.acomodar(
        fuente, params(resolucion=4.0), lambda a: True, salida
    )

    assert resultado.recortes_usados == 0


def test_una_pieza_del_tamano_de_un_recorte_no_se_descarta(tmp_path, deposito):
    """`discard_plate_outline` tira los rectángulos del tamaño exacto de la
    placa, porque son la previsualización que alguien dibujó en su CAD.
    Mirar también las medidas de los recortes parece consistente y es una
    trampa: con 1830x2600 el choque es improbable, pero una medida de
    recorte ES una medida de pieza. Esta pieza de 600x800 tiene que
    sobrevivir a que haya un recorte de 600x800 cargado."""
    ruta = dxf_con(tmp_path, [])
    import ezdxf

    doc = ezdxf.readfile(str(ruta))
    doc.modelspace().add_lwpolyline(
        [(0, 0), (600, 0), (600, 800), (0, 800)], close=True
    )
    doc.saveas(ruta)

    fuente = deposito.registrar_local(ruta)
    salida = tmp_path / "t"
    salida.mkdir()

    resultado = corredor.acomodar(
        fuente,
        params(recortes=(Recorte(600.0, 800.0),), resolucion=4.0),
        lambda a: True,
        salida,
    )

    # Si se hubiera descartado, no quedaría ninguna pieza y `acomodar`
    # habría levantado "no se encontró ninguna pieza".
    assert resultado.placas == 1


def test_el_material_desaparecido_llega_al_trabajo_como_error_del_usuario_no_bug(
    tmp_path, deposito
):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)]))
    registro = Registro(tmp_path / "trabajos")
    try:
        trabajo = registro.crear(
            fuente, NestParams(material="fantasma", esfuerzo="rapido"), corredor.acomodar
        )
        fin = time.monotonic() + 10
        while trabajo.estado not in (Estado.LISTO, Estado.ERROR, Estado.CANCELADO):
            if time.monotonic() > fin:
                raise AssertionError(f"el trabajo quedó en {trabajo.estado}")
            time.sleep(0.01)

        assert trabajo.estado == Estado.ERROR
        assert trabajo.es_bug is False, (
            "un material que desapareció del catálogo no es un bug del "
            "programa, y no tiene que mostrar traceback ni pedirle al "
            "usuario que copie el detalle técnico"
        )
        assert "fantasma" in trabajo.error
    finally:
        registro.cerrar()


MDF18 = Material("mdf18", 1830.0, 2600.0, grain_tolerance=180.0)
PLAN_MDF18 = SheetSupply(stock=MDF18.stock_sheet(), material_name=MDF18.name)


def pieza_cuadrada(part_id, lado=200.0):
    return Part(
        part_id, ((0.0, 0.0), (lado, 0.0), (lado, lado), (0.0, lado)), (), (part_id,)
    )


def test_la_estimacion_es_prueba_por_prevision_por_factor(monkeypatch):
    """La fórmula de la spec, 3.2, con la prueba fijada para que el número
    sea exacto."""
    piezas = [pieza_cuadrada(i) for i in range(5)]
    cfg = NestConfig(sep=5.0, margin=10.0, effort="rapido")
    monkeypatch.setattr(corredor, "probe_query_seconds", lambda *a, **k: 0.01)

    assert corredor.estimar_segundos(piezas, PLAN_MDF18, cfg) == pytest.approx(
        0.01 * initial_forecast(piezas, PLAN_MDF18, cfg) * corredor.FACTOR_LLENO
    )


def test_la_estimacion_mide_de_verdad_si_no_se_la_fija():
    piezas = [pieza_cuadrada(i) for i in range(3)]
    cfg = NestConfig(sep=5.0, margin=10.0, effort="rapido", resolution=4.0)

    assert corredor.estimar_segundos(piezas, PLAN_MDF18, cfg) > 0


def test_sin_piezas_no_hay_estimacion():
    assert corredor.estimar_segundos([], PLAN_MDF18, NestConfig()) is None


def test_estimar_lee_la_fuente_y_devuelve_segundos(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200), (300, 0, 150)]))

    segundos = corredor.estimar(fuente, params(resolucion=4.0))

    assert isinstance(segundos, float) and segundos > 0


def test_estimar_con_un_material_que_no_existe_da_none(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)]))

    assert corredor.estimar(fuente, NestParams(material="no-existe")) is None


def test_estimar_con_parametros_invalidos_da_none(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)]))

    assert corredor.estimar(fuente, params(sep=-1.0)) is None


def test_estimar_un_archivo_sin_piezas_da_none(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, []))

    assert corredor.estimar(fuente, params()) is None


def test_estimar_un_archivo_sin_unidades_da_none(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)], unidades=0))

    assert corredor.estimar(fuente, params()) is None
