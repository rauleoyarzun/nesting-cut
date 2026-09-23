"""Las reglas de los parámetros, que comparten la CLI y la API."""

import pytest

from nesting.model.material import Material
from nesting.params import (
    FLAG_POR_CAMPO,
    NestParams,
    ParamsInvalidosError,
    Recorte,
    ReglaRota,
    a_config,
    a_supply,
    mensaje_cli,
    validar,
)

MDF = Material("mdf18", 1830.0, 2600.0, grain_tolerance=180.0)
FENOLICO = Material("fenolico18", 1220.0, 2440.0, grain_tolerance=5.0)


def p(**cambios):
    return NestParams(material="mdf18", **cambios)


def test_los_valores_por_omision_son_validos():
    validar(p())


@pytest.mark.parametrize(
    "cambio, campo, regla",
    [
        ({"copias": 0}, "copias", ">= 1"),
        ({"copias": -3}, "copias", ">= 1"),
        ({"sep": -0.1}, "sep", ">= 0"),
        ({"borde": -1.0}, "borde", ">= 0"),
        ({"tol_cierre": 0.0}, "tol_cierre", "> 0"),
        ({"tol_cierre": -1.0}, "tol_cierre", "> 0"),
        ({"resolucion": 0.0}, "resolucion", "> 0"),
        ({"resolucion": -2.0}, "resolucion", "> 0"),
    ],
)
def test_cada_regla_nombra_su_campo_y_su_regla(cambio, campo, regla):
    with pytest.raises(ParamsInvalidosError) as capturado:
        validar(p(**cambio))

    assert capturado.value.rota.campo == campo
    assert capturado.value.rota.regla == regla
    assert capturado.value.rota.valor == next(iter(cambio.values()))


def test_la_separacion_cero_es_valida():
    """Cortar pegado es una decisión legítima del usuario, no un error."""
    validar(p(sep=0.0))


def test_el_borde_cero_es_valido():
    validar(p(borde=0.0))


def test_el_mensaje_de_la_cli_nombra_el_flag_y_el_valor():
    """La CLI tiene que seguir diciendo exactamente lo que decía.

    Ese texto es contrato: hay tests de la CLI que lo verifican, y lo lee
    gente en una terminal donde 'sep' a secas no significa nada.
    """
    with pytest.raises(ParamsInvalidosError) as capturado:
        validar(p(sep=-1.0))

    assert mensaje_cli(capturado.value.rota) == "--sep tiene que ser >= 0, se recibió -1.0"


def test_todo_campo_con_regla_tiene_su_flag():
    """Un campo sin flag haría reventar a `mensaje_cli` con KeyError justo
    cuando el usuario ya se equivocó, que es el peor momento."""
    for campo in ("copias", "sep", "borde", "tol_cierre", "resolucion"):
        assert campo in FLAG_POR_CAMPO


def test_a_config_traduce_los_nombres_al_motor():
    """La interfaz habla en español y el motor en inglés. La traducción vive
    en un solo lugar para que no se desincronice."""
    config = a_config(p(sep=3.0, borde=7.0, espejo=False, resolucion=1.5, esfuerzo="lento"))

    assert config.sep == 3.0
    assert config.margin == 7.0
    assert config.mirror is False
    assert config.resolution == 1.5
    assert config.effort == "lento"
    assert config.angles == (0.0, 90.0, 180.0, 270.0)


def test_a_config_no_valida_por_su_cuenta():
    """`a_config` traduce, no juzga. Validar es un paso aparte y explícito,
    así el que llama no puede creer que traducir ya lo protegió."""
    config = a_config(p(sep=-5.0))
    assert config.sep == -5.0


def test_la_tolerancia_de_cierre_por_omision_sale_de_una_sola_fuente():
    """Dos literales con el mismo valor se despegan en silencio el día que
    alguien recalibre la constante, y nada lo avisa hasta que la CLI y la
    interfaz acomodan distinto el mismo archivo."""
    from nesting.pipeline import DEFAULT_CHAIN_TOL

    assert NestParams(material="mdf18").tol_cierre == DEFAULT_CHAIN_TOL


def test_importar_los_parametros_no_arrastra_el_motor():
    """`params.py` existe para que se puedan validar parámetros sin cargar
    el motor -- lo dice su propio docstring. Importar geometría desde acá
    hacía que importar los parámetros tardara 35 veces más, y nada lo
    avisaba: el módulo seguía funcionando, sólo que pesado.
    """
    import subprocess
    import sys

    codigo = (
        "import sys; import nesting.params; "
        "pesados = [m for m in ('shapely', 'ezdxf', 'rhino3dm', 'scipy') if m in sys.modules]; "
        "print(','.join(pesados))"
    )
    salida = subprocess.run(
        [sys.executable, "-c", codigo], capture_output=True, text=True, check=True
    ).stdout.strip()

    assert salida == "", f"nesting.params arrastró: {salida}"


def test_la_resolucion_por_omision_es_uno():
    assert NestParams(material="mdf18").resolucion == 1.0


def test_sin_recortes_el_plan_es_una_sola_placa_infinita():
    plan = a_supply(NestParams(material="mdf18"), MDF)

    assert plan.scraps == ()
    assert plan.sheet(0) == plan.sheet(5) == MDF.stock_sheet()
    assert plan.material_name == "mdf18"


def test_la_cantidad_se_expande_a_una_placa_por_unidad():
    params = NestParams(material="mdf18", recortes=(Recorte(600.0, 800.0, cantidad=3),))
    plan = a_supply(params, MDF)

    assert len(plan.scraps) == 3
    assert all(h.width == 600.0 and h.height == 800.0 for h in plan.scraps)
    assert all(h.scrap for h in plan.scraps)


def test_los_recortes_se_ordenan_de_mayor_a_menor():
    """Si el chico fuera primero, una pieza mediana que sólo entra en el
    grande podría quedar varada porque el grande se llenó de piezas que
    también entraban en el chico."""
    params = NestParams(
        material="mdf18",
        recortes=(Recorte(300.0, 300.0), Recorte(900.0, 900.0), Recorte(600.0, 600.0)),
    )
    plan = a_supply(params, MDF)

    assert [h.width for h in plan.scraps] == [900.0, 600.0, 300.0]


def test_los_recortes_heredan_la_veta_del_material():
    params = NestParams(material="fenolico18", recortes=(Recorte(600.0, 800.0),))
    plan = a_supply(params, FENOLICO)

    assert plan.scraps[0].grain_tolerance == 5.0
    assert plan.scraps[0].cross_grain is False


def test_la_veta_cruzada_viaja_al_plan():
    params = NestParams(
        material="fenolico18", recortes=(Recorte(600.0, 800.0, veta_cruzada=True),)
    )
    assert a_supply(params, FENOLICO).scraps[0].cross_grain is True


def test_un_recorte_mas_grande_que_la_placa_se_acepta():
    params = NestParams(material="mdf18", recortes=(Recorte(3000.0, 3000.0),))
    assert a_supply(params, MDF).scraps[0].width == 3000.0


@pytest.mark.parametrize("recorte, campo, regla", [
    (Recorte(0.0, 800.0), "recorte 1: ancho", "> 0"),
    (Recorte(600.0, -1.0), "recorte 1: alto", "> 0"),
    (Recorte(600.0, 800.0, cantidad=0), "recorte 1: cantidad", ">= 1"),
])
def test_validar_rechaza_un_recorte_invalido(recorte, campo, regla):
    with pytest.raises(ParamsInvalidosError) as capturado:
        validar(NestParams(material="mdf18", recortes=(recorte,)))

    assert capturado.value.rota.campo == campo
    assert capturado.value.rota.regla == regla


def test_el_error_dice_cual_de_la_lista():
    params = NestParams(
        material="mdf18", recortes=(Recorte(600.0, 800.0), Recorte(0.0, 800.0))
    )
    with pytest.raises(ParamsInvalidosError) as capturado:
        validar(params)

    assert capturado.value.rota.campo == "recorte 2: ancho"


def test_mensaje_cli_no_se_rompe_con_un_campo_que_no_tiene_flag():
    """Los recortes no vienen de la CLI, así que no tienen flag. Un
    `FLAG_POR_CAMPO[campo]` crudo levantaría KeyError si alguien llegara
    igual hasta acá."""
    rota = ReglaRota("recorte 1: ancho", "> 0", 0.0)
    assert "recorte 1: ancho" in mensaje_cli(rota)


# --- la veta de la corrida -------------------------------------------------

from nesting.model.material import VETA_LIBRE, VETA_RESPETAR
from nesting.params import tolerancia_de_veta


def test_sin_veta_manda_la_del_material():
    assert tolerancia_de_veta(NestParams(material="mdf18"), MDF) == 180.0
    assert tolerancia_de_veta(NestParams(material="fenolico18"), FENOLICO) == 5.0


@pytest.mark.parametrize("material", [MDF, FENOLICO])
def test_respetar_pisa_a_cualquier_material(material):
    params = NestParams(material=material.name, veta="respetar")
    assert tolerancia_de_veta(params, material) == VETA_RESPETAR


@pytest.mark.parametrize("material", [MDF, FENOLICO])
def test_libre_pisa_a_cualquier_material(material):
    params = NestParams(material=material.name, veta="libre")
    assert tolerancia_de_veta(params, material) == VETA_LIBRE


def test_la_veta_de_la_corrida_llega_a_la_placa_del_material():
    params = NestParams(material="fenolico18", veta="libre")
    assert a_supply(params, FENOLICO).stock.grain_tolerance == VETA_LIBRE


def test_la_veta_de_la_corrida_llega_a_los_recortes():
    params = NestParams(
        material="mdf18", veta="respetar", recortes=(Recorte(600.0, 800.0),)
    )
    plan = a_supply(params, MDF)

    assert plan.scraps[0].grain_tolerance == VETA_RESPETAR
    assert plan.stock.grain_tolerance == VETA_RESPETAR


def test_sin_veta_el_plan_queda_igual_que_antes():
    """El contrato de todo el plan: sin tocar la veta, nada cambia."""
    params = NestParams(material="fenolico18", recortes=(Recorte(600.0, 800.0),))
    plan = a_supply(params, FENOLICO)

    assert plan.stock == FENOLICO.stock_sheet()
    assert plan.scraps[0].grain_tolerance == FENOLICO.grain_tolerance


def test_las_constantes_de_veta_viven_en_el_modelo():
    """El motor no puede importar la interfaz, así que las constantes que
    usa `tolerancia_de_veta` tienen que vivir de este lado. La interfaz las
    reexporta para no romper a quien ya las usaba."""
    from nesting_app import materials_store

    assert materials_store.VETA_LIBRE is VETA_LIBRE
    assert materials_store.VETA_RESPETAR is VETA_RESPETAR
