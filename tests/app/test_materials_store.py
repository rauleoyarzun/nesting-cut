"""El catálogo de materiales que el usuario edita."""

import pytest

from nesting.model.material import Material
from nesting_app import materials_store as store


@pytest.fixture(autouse=True)
def catalogo_aislado(tmp_path, monkeypatch):
    """Cada test con su propia carpeta de datos, nunca la del usuario real."""
    monkeypatch.setattr(store.rutas, "_base_de_datos", lambda: tmp_path / "nesting")
    return tmp_path


def melamina():
    return Material(name="melamina18", sheet_w=1830.0, sheet_h=2750.0,
                    grain_tolerance=store.VETA_LIBRE)


def test_la_primera_vez_se_copia_el_catalogo_que_trae_el_programa():
    """Un catálogo vacío obligaría al usuario a tipear sus cuatro materiales
    antes de poder hacer nada. Arranca con los que ya conocemos."""
    materiales = store.leer()

    assert "mdf18" in materiales
    assert materiales["mdf18"].sheet_w == 1830.0
    assert materiales["mdf18"].sheet_h == 2600.0


def test_el_archivo_queda_en_la_carpeta_de_datos_no_adentro_del_programa():
    ruta = store.ruta_catalogo()

    assert ruta.name == "materials.yaml"
    assert ruta.parent == store.rutas.carpeta_datos()
    assert ruta.is_file()


def test_agregar_y_releer():
    store.agregar(melamina())

    materiales = store.leer()
    assert materiales["melamina18"].sheet_h == 2750.0
    assert materiales["melamina18"].grain_tolerance == store.VETA_LIBRE


def test_agregar_uno_que_ya_existe_se_rechaza():
    """Sin esto, agregar 'mdf18' pisaría en silencio las medidas de un
    material que el usuario ya estaba usando en trabajos anteriores."""
    with pytest.raises(store.MaterialDuplicadoError, match="mdf18"):
        store.agregar(Material("mdf18", 100.0, 100.0, store.VETA_LIBRE))


def test_editar_cambia_las_medidas():
    store.editar("mdf18", Material("mdf18", 1830.0, 2750.0, store.VETA_LIBRE))

    assert store.leer()["mdf18"].sheet_h == 2750.0


def test_editar_puede_renombrar():
    store.editar("mdf18", Material("mdf18mm", 1830.0, 2600.0, store.VETA_LIBRE))

    materiales = store.leer()
    assert "mdf18mm" in materiales
    assert "mdf18" not in materiales


def test_renombrar_encima_de_otro_material_se_rechaza():
    """Sin esto, renombrar 'mdf15' a 'mdf18' borraría las medidas de mdf18
    sin decir una palabra, y el usuario se entera cuando corta mal una
    placa."""
    with pytest.raises(store.MaterialDuplicadoError, match="mdf18"):
        store.editar("mdf15", Material("mdf18", 100.0, 100.0, store.VETA_LIBRE))

    materiales = store.leer()
    assert materiales["mdf18"].sheet_w == 1830.0, "mdf18 quedó pisado"
    assert "mdf15" in materiales, "mdf15 desapareció"


def test_editar_uno_que_no_existe_se_queja():
    with pytest.raises(store.MaterialDesconocidoError, match="fantasma"):
        store.editar("fantasma", melamina())


def test_el_mensaje_de_editar_uno_que_no_existe_esta_bien_puntuado():
    """El mensaje traía dos oraciones pegadas sin espacio y con minúscula
    después del punto: "...para verla al día.revisá la lista actual.". Este
    test agarra esa forma concreta de puntuación rota (un punto seguido
    directo de una minúscula), no cualquier defecto de redacción."""
    import re

    with pytest.raises(store.MaterialDesconocidoError) as info:
        store.editar("fantasma", melamina())

    assert not re.search(r"\.[a-záéíóúñ]", str(info.value))


def test_borrar():
    store.borrar("mdf15")

    assert "mdf15" not in store.leer()
    assert "mdf18" in store.leer()


def test_borrar_uno_que_no_existe_se_queja():
    with pytest.raises(store.MaterialDesconocidoError, match="fantasma"):
        store.borrar("fantasma")


def test_el_mensaje_de_borrar_uno_que_no_existe_esta_bien_puntuado():
    import re

    with pytest.raises(store.MaterialDesconocidoError) as info:
        store.borrar("fantasma")

    assert not re.search(r"\.[a-záéíóúñ]", str(info.value))


def test_se_puede_borrar_hasta_el_ultimo():
    """Quedarse sin materiales es un estado válido y recuperable: está el
    botón de restaurar. Prohibirlo sería tratar al usuario de tonto."""
    for nombre in list(store.leer()):
        store.borrar(nombre)

    assert store.leer() == {}


def test_restaurar_vuelve_al_catalogo_original():
    store.borrar("mdf18")
    store.agregar(melamina())

    store.restaurar()

    materiales = store.leer()
    assert "mdf18" in materiales
    assert "melamina18" not in materiales


def test_un_catalogo_corrupto_se_queja_nombrando_el_archivo():
    """El usuario puede haber editado el YAML a mano. El mensaje tiene que
    decirle dónde está el archivo para que pueda arreglarlo o borrarlo."""
    store.leer()
    store.ruta_catalogo().write_text("esto: [no cierra\n", encoding="utf-8")

    with pytest.raises(ValueError, match="materials.yaml"):
        store.leer()


def test_restaurar_arregla_un_catalogo_corrupto():
    """Es la salida que se le ofrece al usuario cuando el archivo está roto,
    así que tiene que funcionar justamente en ese estado."""
    store.leer()
    store.ruta_catalogo().write_text("esto: [no cierra\n", encoding="utf-8")

    store.restaurar()

    assert "mdf18" in store.leer()


def test_la_veta_tiene_dos_valores_y_ninguno_es_un_numero_suelto():
    """La interfaz muestra dos opciones con nombre, no un campo de grados.
    Estos son los dos valores que esas opciones escriben."""
    assert store.VETA_LIBRE == 180.0
    assert store.VETA_RESPETAR == 5.0
