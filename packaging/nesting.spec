# -*- mode: python ; coding: utf-8 -*-
"""Cómo se arma el ejecutable.

Modo CARPETA, no archivo único: el modo de archivo único se autodescomprime
en cada arranque, y con 300 MB de scipy y rhino3dm eso son varios segundos
de nada cada vez que alguien abre el programa.
"""

import sys
from pathlib import Path

RAIZ = Path(SPECPATH).parent

# El .ico y el .icns los genera `herramientas/icono.py` a partir del mismo
# dibujo. PyInstaller acepta uno u otro según la plataforma y se queja si le
# dan el que no corresponde, así que se elige acá.
#
# En macOS hoy no se ve en ningún lado: este .spec arma una CARPETA, no un
# .app, y el Finder saca el ícono del bundle. Se declara igual para que esté
# listo el día que se arme un .app, y porque no cuesta nada.
ICONO = str(RAIZ / "packaging" / ("icono.ico" if sys.platform == "win32" else "icono.icns"))

# Los recursos que `rutas.recurso()` va a buscar. Que falte alguno rompe el
# programa recién cuando el usuario lo abre, por eso existe `--autotest`.
datos = [
    (str(RAIZ / "materials.yaml"), "."),
    (str(RAIZ / "src" / "nesting_app" / "web"), "web"),
]

# scipy y rhino3dm cargan cosas que PyInstaller no ve siguiendo imports.
ocultos = [
    "scipy._lib.array_api_compat.numpy.fft",
    "scipy.special._special_ufuncs",
    "rhino3dm._rhino3dm",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]

a = Analysis(
    [str(RAIZ / "src" / "nesting_app" / "desktop.py")],
    pathex=[str(RAIZ / "src")],
    datas=datos,
    hiddenimports=ocultos,
    excludes=["tkinter", "matplotlib", "pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Nesting",
    console=False,
    disable_windowed_traceback=False,
    icon=ICONO,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, name="Nesting",
)
