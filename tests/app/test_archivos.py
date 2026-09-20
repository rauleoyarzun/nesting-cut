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


@pytest.mark.parametrize(
    "nombre", ["dibujo.cdr", "foto.png", "notas.txt", "sin_extension"]
)
def test_una_extension_que_el_programa_no_lee_se_rechaza_temprano(deposito, nombre):
    """Rechazar acá le dice al usuario 'este formato no' de una. Dejarlo
    pasar lo hace fallar adentro del lector con un mensaje sobre sintaxis."""
    with pytest.raises(ExtensionNoSoportadaError, match="dxf"):
        deposito.registrar_subida(nombre, b"lo que sea")


def test_la_extension_no_distingue_mayusculas(deposito):
    fuente = deposito.registrar_subida("ROBOT.AI", b"%!PS-Adobe")
    assert fuente.nombre == "ROBOT.AI"


def test_un_cdr_rechazado_menciona_corel(deposito):
    """Cuando el usuario sube un .cdr, el mensaje le explica qué hacer."""
    with pytest.raises(ExtensionNoSoportadaError, match="CorelDRAW"):
        deposito.registrar_subida("dibujo.cdr", b"lo que sea")


def test_otras_extensiones_rechazadas_no_mencionan_corel(deposito):
    """El consejo sobre CorelDRAW es específico para .cdr, no para cualquier
    extensión rechazada. Un usuario con un .png no necesita que le hablemos
    de CorelDRAW."""
    with pytest.raises(ExtensionNoSoportadaError) as exc_info:
        deposito.registrar_subida("foto.png", b"lo que sea")
    assert "CorelDRAW" not in str(exc_info.value)


def test_byte_nulo_en_nombre_se_rechaza_temprano(deposito):
    """Un nombre con byte nulo causaría ValueError al escribir. Rechazarlo
    temprano con mensaje en español evita que el usuario vea un traceback."""
    with pytest.raises(ValueError, match="carácter nulo"):
        deposito.registrar_subida("a\x00b.dxf", b"contenido")


def test_registrar_local_rechaza_extension_no_soportada(deposito, tmp_path):
    """La validación de extensión ocurre en ambas puertas. Si alguien
    rompiera la paridad en un refactor, este test lo detectaría."""
    # Crear un archivo real con extensión no soportada
    archivo = tmp_path / "documento.txt"
    archivo.write_text("contenido")

    with pytest.raises(ExtensionNoSoportadaError):
        deposito.registrar_local(archivo)


@pytest.mark.parametrize("nombre_peligroso,nombre_esperado", [
    ("../../afuera.dxf", "afuera.dxf"),
    ("../../../etc/passwd.dxf", "passwd.dxf"),
    ("/etc/passwd.dxf", "passwd.dxf"),
    ("carpeta/archivo.dxf", "archivo.dxf"),
    ("carpeta\\archivo.dxf", "archivo.dxf"),
    ("..\\..\\afuera.dxf", "afuera.dxf"),
    ("C:\\x.dxf", "x.dxf"),
    ("\\\\servidor\\compartido\\x.dxf", "x.dxf"),
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


def test_un_byte_nulo_tampoco_pasa_por_la_puerta_de_escritorio(deposito, tmp_path):
    """Hoy no revienta, pero por casualidad: `Path.is_file()` se traga el
    ValueError del byte nulo y devuelve False, así que el pedido muere como
    "no existe" antes de llegar a la validación. Si alguien reordena esas
    dos líneas, la excepción cruda vuelve. Este test lo fija.
    """
    with pytest.raises((ValueError, FileNotFoundError)) as capturado:
        deposito.registrar_local(str(tmp_path / "a\x00b.dxf"))

    assert "null byte" not in str(capturado.value), (
        "se escapó la excepción cruda de Python, en inglés"
    )


def test_toda_fuente_tiene_su_carpeta_propia(deposito, tmp_path):
    """El análisis deja ahí la imagen de revisión, y una ruta local no se
    copia a ningún lado: sin una carpeta propia, el camino de escritorio --
    el único que el usuario corre -- se quedaba sin dónde dejarla."""
    origen = tmp_path / "robot.ai"
    origen.write_text("%!PS-Adobe", encoding="utf-8")

    local = deposito.registrar_local(origen)
    subida = deposito.registrar_subida("robot.ai", b"%!PS-Adobe")

    for fuente in (local, subida):
        assert fuente.carpeta.is_dir()
        assert deposito.carpeta in fuente.carpeta.parents or fuente.carpeta.parent == deposito.carpeta
        assert fuente.carpeta.name == fuente.id


def test_dos_fuentes_no_comparten_carpeta(deposito, tmp_path):
    """Dos archivos que se llaman igual no pueden pisarse la revisión: la
    imagen del segundo mostraría los descartes del primero."""
    origen = tmp_path / "robot.ai"
    origen.write_text("%!PS-Adobe", encoding="utf-8")

    a = deposito.registrar_local(origen)
    b = deposito.registrar_local(origen)

    assert a.carpeta != b.carpeta


def test_limpiar_se_lleva_tambien_las_carpetas_de_las_fuentes(deposito, tmp_path):
    origen = tmp_path / "robot.ai"
    origen.write_text("%!PS-Adobe", encoding="utf-8")
    fuente = deposito.registrar_local(origen)

    deposito.limpiar()

    assert not fuente.carpeta.exists()
    assert origen.is_file(), "limpiar borró el archivo del usuario, que no es suyo"
