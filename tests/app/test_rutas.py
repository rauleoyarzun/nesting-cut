"""Dónde están los datos y los recursos, corriendo del repo o congelado."""

import sys
from pathlib import Path

import pytest

from nesting_app import rutas


def test_la_carpeta_de_datos_se_crea_si_no_existe(tmp_path, monkeypatch):
    destino = tmp_path / "nesting"
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: destino)

    assert rutas.carpeta_datos() == destino
    assert destino.is_dir()


def test_la_carpeta_de_datos_se_puede_pedir_dos_veces(tmp_path, monkeypatch):
    destino = tmp_path / "nesting"
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: destino)

    rutas.carpeta_datos()
    assert rutas.carpeta_datos() == destino


def test_sin_congelar_los_recursos_salen_del_repo():
    """`materials.yaml` está en la raíz del proyecto, tres niveles sobre el
    paquete. Es la cuenta que hace hoy `DEFAULT_MATERIALS_PATH`."""
    assert not rutas.esta_congelado()

    catalogo = rutas.recurso("materials.yaml")
    assert catalogo.is_file()
    assert "mdf18" in catalogo.read_text(encoding="utf-8")


def test_congelado_los_recursos_salen_de_meipass(tmp_path, monkeypatch):
    """PyInstaller descomprime los recursos en `sys._MEIPASS` y NO reproduce
    la estructura del repo. La cuenta de `parents[3]` da cualquier cosa ahí,
    que es el bug que esta función existe para que no ocurra nunca.
    """
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    (tmp_path / "materials.yaml").write_text("mdf18:\n", encoding="utf-8")

    assert rutas.esta_congelado()
    assert rutas.recurso("materials.yaml") == tmp_path / "materials.yaml"


def test_un_recurso_que_no_existe_se_queja_nombrandolo():
    """Un recurso faltante en un ejecutable congelado es un error de
    empaquetado, no del usuario. El mensaje tiene que decir cuál falta para
    que quien arme el paquete sepa qué agregarle."""
    with pytest.raises(FileNotFoundError, match="no_existe.yaml"):
        rutas.recurso("no_existe.yaml")


def test_la_carpeta_web_es_un_recurso():
    """No alcanza con que sea un directorio: tiene que ser el que está
    dentro del paquete (`src/nesting_app/web`), no cualquier otro. Un test
    que sólo pide `.is_dir()` lo satisface una carpeta vacía en cualquier
    lado -- que es exactamente el bug que hubo acá."""
    assert not rutas.esta_congelado()

    web = rutas.recurso("web")

    assert web == Path(__file__).resolve().parents[2] / "src" / "nesting_app" / "web"
    assert web.is_dir()


def test_todo_lo_declarado_en_el_repo_existe():
    """Un recurso declarado en `EN_EL_REPO` y ausente del repo recién rompe
    el programa cuando alguien lo abre. Que lo detecte un test."""
    raiz = Path(__file__).resolve().parents[2]

    for relativo in rutas.EN_EL_REPO.values():
        assert (raiz / relativo).exists(), f"falta {relativo!r} en el repo"


@pytest.mark.parametrize(
    "plataforma, variable, esperado",
    [
        ("win32", "APPDATA", "nesting"),
        ("darwin", None, "nesting"),
        ("linux", None, "nesting"),
    ],
)
def test_cada_plataforma_usa_su_carpeta(plataforma, variable, esperado, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", plataforma)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    base = rutas._base_de_datos()
    assert base.name == esperado
    assert tmp_path in base.parents


def test_todo_archivo_de_la_interfaz_entra_en_el_paquete(tmp_path):
    """`package-data` con un patrón no recursivo deja afuera las subcarpetas
    sin decir una palabra: el wheel se arma bien y al programa le falta media
    interfaz recién cuando alguien lo instala y lo abre.

    Este test arma un árbol de prueba sintético en tmp_path porque verificar contra
    la carpeta real no ejercita el patrón recursivo mientras esa carpeta esté plana
    (solo tiene `.gitkeep`). El árbol incluye:
    - archivo plano visible: web/index.html (prueba `web/*`)
    - archivo plano oculto: web/.gitkeep (prueba `web/.*`)
    - archivo en subcarpeta: web/img/logo.svg (prueba `web/**/*`)
    - archivo dos niveles abajo: web/fuentes/latin/x.woff2 (prueba `web/**/*`)
    - archivo oculto en subcarpeta: web/img/.DS_Store (prueba `web/**/.*`)

    Se verifica contra el `pyproject.toml` usando glob (que es lo que setuptools usa).
    No se arma un wheel porque tarda y necesita herramientas de construcción que no son
    dependencia de los tests.
    """
    import glob
    import tomllib

    raiz = Path(__file__).resolve().parents[2]
    with (raiz / "pyproject.toml").open("rb") as f:
        patrones = tomllib.load(f)["tool"]["setuptools"]["package-data"]["nesting_app"]

    # Armar árbol sintético en tmp_path
    web = tmp_path / "web"
    web.mkdir()

    # Crear los archivos de prueba
    (web / "index.html").write_text("<html></html>")
    (web / ".gitkeep").write_text("")
    (web / "img").mkdir()
    (web / "img" / "logo.svg").write_text("<svg></svg>")
    (web / "img" / ".DS_Store").write_text("")
    (web / "fuentes").mkdir()
    (web / "fuentes" / "latin").mkdir()
    (web / "fuentes" / "latin" / "x.woff2").write_bytes(b"")

    # Recopilar todos los archivos creados
    archivos = [
        str(p.relative_to(tmp_path)) for p in web.rglob("*") if p.is_file()
    ]
    assert archivos, "el árbol sintético no tiene archivos"

    # Verificar que cada archivo lo toma al menos un patrón
    for archivo in archivos:
        coincide = False
        for patron in patrones:
            # El patrón se ancla en tmp_path, igual que setuptools lo ancla en la
            # raíz del paquete: absoluto de los dos lados, así el cwd no influye.
            ruta_patron = str(tmp_path / patron)
            archivos_encontrados = glob.glob(ruta_patron, recursive=True)
            if str(tmp_path / archivo) in archivos_encontrados:
                coincide = True
                break

        assert coincide, (
            f"{archivo} no lo toma ningún patrón de package-data: {patrones}"
        )
