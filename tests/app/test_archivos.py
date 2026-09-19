"""La puerta que iguala 'una ruta local' y 'un archivo subido'."""

import pytest

from nesting_app.archivos import (
    Deposito,
    ExtensionNoSoportadaError,
    FuenteDesconocidaError,
)


@pytest.fixture
def deposito(tmp_path):
    return Deposito(tmp_path / "trabajo")


def test_una_ruta_local_se_registra_sin_copiar_el_contenido(deposito, tmp_path):
    """En escritorio el archivo ya está en el disco del usuario. Copiarlo
    duplicaría 500 KB por cada análisis sin ganar nada."""
    origen = tmp_path / "robot.ai"
    origen.write_text("%!PS-Adobe", encoding="utf-8")

    fuente = deposito.registrar_local(origen)

    assert fuente.ruta == origen
    assert fuente.nombre == "robot.ai"
    # Verificar que es el MISMO archivo (mismo inodo), no una copia
    assert fuente.ruta.stat().st_ino == origen.stat().st_ino


def test_una_subida_se_guarda_en_la_carpeta_de_trabajo(deposito):
    fuente = deposito.registrar_subida("robot.ai", b"%!PS-Adobe")

    assert fuente.ruta.read_bytes() == b"%!PS-Adobe"
    assert fuente.ruta.parent.parent == deposito.carpeta
    assert fuente.nombre == "robot.ai"


def test_los_dos_caminos_devuelven_algo_que_se_usa_igual(deposito, tmp_path):
    """Es el punto entero del módulo: de acá para adelante nadie sabe si el
    archivo vino de un diálogo nativo o de un formulario."""
    origen = tmp_path / "a.dxf"
    origen.write_text("0\nSECTION\n", encoding="utf-8")

    local = deposito.registrar_local(origen)
    subida = deposito.registrar_subida("b.dxf", b"0\nSECTION\n")

    for fuente in (local, subida):
        assert deposito.obtener(fuente.id).ruta.is_file()


def test_cada_registro_tiene_su_propio_id(deposito):
    a = deposito.registrar_subida("x.dxf", b"a")
    b = deposito.registrar_subida("x.dxf", b"b")

    assert a.id != b.id
    assert deposito.obtener(a.id).ruta.read_bytes() == b"a"
    assert deposito.obtener(b.id).ruta.read_bytes() == b"b"


def test_un_id_que_no_existe_se_queja(deposito):
    with pytest.raises(FuenteDesconocidaError):
        deposito.obtener("no-existe")


def test_una_ruta_que_no_existe_se_queja_nombrandola(deposito, tmp_path):
    with pytest.raises(FileNotFoundError, match="fantasma.ai"):
        deposito.registrar_local(tmp_path / "fantasma.ai")


@pytest.mark.parametrize("nombre", ["dibujo.cdr", "foto.png", "notas.txt", "sin_extension"])
def test_una_extension_que_el_programa_no_lee_se_rechaza_temprano(deposito, nombre):
    """Rechazar acá le dice al usuario 'este formato no' de una. Dejarlo
    pasar lo hace fallar adentro del lector con un mensaje sobre sintaxis."""
    with pytest.raises(ExtensionNoSoportadaError, match="dxf"):
        deposito.registrar_subida(nombre, b"lo que sea")


def test_la_extension_no_distingue_mayusculas(deposito):
    fuente = deposito.registrar_subida("ROBOT.AI", b"%!PS-Adobe")
    assert fuente.nombre == "ROBOT.AI"


@pytest.mark.parametrize("nombre_peligroso,nombre_esperado", [
    ("../../afuera.dxf", "afuera.dxf"),
    ("../../../etc/passwd.dxf", "passwd.dxf"),
    ("/etc/passwd.dxf", "passwd.dxf"),
    ("carpeta/archivo.dxf", "archivo.dxf"),
    ("carpeta\\archivo.dxf", "archivo.dxf"),
    ("..\\..\\afuera.dxf", "afuera.dxf"),
])
def test_una_subida_no_puede_escribir_fuera_de_la_carpeta(deposito, nombre_peligroso, nombre_esperado):
    """Un nombre con '..' o con barras es un intento de escribir donde no
    corresponde. En la web eso llega de afuera; acá se corta siempre."""
    fuente = deposito.registrar_subida(nombre_peligroso, b"x")

    assert deposito.carpeta in fuente.ruta.parents
    assert fuente.ruta.name == nombre_esperado


def test_limpiar_borra_todo(deposito):
    deposito.registrar_subida("a.dxf", b"a")
    deposito.limpiar()

    assert not deposito.carpeta.exists()


def test_limpiar_dos_veces_no_revienta(deposito):
    """Se llama al cerrar el programa y al arrancar. Que una de las dos
    encuentre la carpeta vacía es lo normal, no un error."""
    deposito.limpiar()
    deposito.limpiar()
