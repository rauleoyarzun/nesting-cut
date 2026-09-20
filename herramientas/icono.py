"""Dibuja el ícono del programa y genera todo lo que hace falta de él.

    python herramientas/icono.py            # regenera todos los archivos
    python herramientas/icono.py comparar   # lo muestra sobre varios fondos

El ícono se dibuja acá, con código, en vez de guardarse sólo como binario:
un .ico no se puede corregir ni entender mirándolo, y este tiene tres
colores y una composición que van a querer ajustarse alguna vez.

Composición: piezas distintas que encastran y llenan el cuadrado, separadas
por una ranura -- el `sep` del programa. Elegida entre cuatro propuestas por
ser la única que a 32 px seguía leyéndose como piezas que encajan.

DOS DIBUJOS, NO UNO. A 16 y 32 px las cinco piezas de la versión grande se
convierten en puré: quedan bloques de dos o tres píxeles separados por
ranuras de menos de uno. Para esos tamaños se dibuja una composición de tres
piezas, con la misma idea y la misma paleta. Es lo que hace que un ícono se
vea bien chico en vez de sólo escalar mal.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[1]

ACENTO = (4, 120, 87)       # --acento
ACENTO_CLARO = (16, 163, 114)
TEXTO = (17, 24, 39)        # --texto
LIENZO = (237, 240, 244)    # --lienzo
BORDE = (226, 230, 236)

E = 8
"""Se dibuja a 8x y se baja con LANCZOS: Pillow no antialiasea polígonos, y
a tamaño final los bordes salen escalonados."""

UMBRAL_SIMPLE = 48
"""De acá para abajo se usa la composición de tres piezas."""

# Cada pieza es (puntos en fracción del lado, color). Las fracciones dejan
# ranuras visibles entre piezas: son parte del dibujo, no un descuido.
DETALLADO = [
    ([(.18, .18), (.52, .18), (.52, .34), (.34, .34), (.34, .52), (.18, .52)], ACENTO),
    ([(.56, .18), (.82, .18), (.82, .48), (.56, .48)], ACENTO_CLARO),
    ([(.18, .56), (.44, .56), (.44, .82), (.18, .82)], TEXTO),
    ([(.48, .52), (.82, .52), (.82, .82), (.48, .82), (.48, .66), (.38, .66),
      (.38, .52)], ACENTO_CLARO),
    ([(.38, .38), (.52, .38), (.52, .48), (.38, .48)], TEXTO),
]

SIMPLE = [
    ([(.16, .16), (.56, .16), (.56, .56), (.16, .56)], ACENTO),
    ([(.62, .16), (.84, .16), (.84, .84), (.62, .84)], ACENTO_CLARO),
    ([(.16, .62), (.56, .62), (.56, .84), (.16, .84)], TEXTO),
]


def composicion(lado: int):
    """Cuál de los dos dibujos le toca a este tamaño.

    Existe como función propia para poder verificarla: comparar los píxeles
    de dos renders no alcanza, porque el remuestreo ya los hace distintos
    aunque la bifurcación no exista.
    """
    return SIMPLE if lado <= UMBRAL_SIMPLE else DETALLADO


def dibujar(lado: int) -> Image.Image:
    """El ícono a `lado` píxeles, ya antialiaseado."""
    L = lado * E
    im = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, L - 1, L - 1], radius=int(L * .22), fill=LIENZO)
    d.rounded_rectangle([0, 0, L - 1, L - 1], radius=int(L * .22),
                        outline=BORDE, width=max(1, int(L * .012)))
    for puntos, color in composicion(lado):
        d.polygon([(x * L, y * L) for x, y in puntos], fill=color)
    return im.resize((lado, lado), Image.LANCZOS)


TAMANOS_ICO = [256, 128, 64, 48, 32, 16]
"""Los seis que Windows saca del .ico según el contexto: el escritorio usa
uno, la barra de tareas otro, el Alt-Tab otro. Con uno solo adentro, Windows
reescala y se ve mal en todos los demás."""


def generar() -> None:
    destinos = {
        "ico": RAIZ / "packaging" / "icono.ico",
        "icns": RAIZ / "packaging" / "icono.icns",
        "favicon": RAIZ / "src" / "nesting_app" / "web" / "icono.png",
        "maestro": RAIZ / "docs" / "imagenes" / "icono.png",
    }
    for ruta in destinos.values():
        ruta.parent.mkdir(parents=True, exist_ok=True)

    # El .ico lleva cada tamaño DIBUJADO, no reescalado desde el grande: es
    # la única forma de que los chicos usen la composición simplificada.
    capas = [dibujar(n) for n in TAMANOS_ICO]
    capas[0].save(destinos["ico"], format="ICO",
                  sizes=[(n, n) for n in TAMANOS_ICO],
                  append_images=capas[1:])
    print(f"  {destinos['ico'].relative_to(RAIZ)}  ({', '.join(map(str, TAMANOS_ICO))} px)")

    dibujar(1024).save(destinos["maestro"])
    print(f"  {destinos['maestro'].relative_to(RAIZ)}  (1024 px)")

    dibujar(64).save(destinos["favicon"])
    print(f"  {destinos['favicon'].relative_to(RAIZ)}  (64 px, la pestaña)")

    if sys.platform == "darwin" and shutil.which("iconutil"):
        _icns(destinos["icns"])
    else:
        print(f"  {destinos['icns'].relative_to(RAIZ)}: se saltea "
              "(hace falta `iconutil`, que es de macOS)")


def _icns(destino: Path) -> None:
    """`iconutil` es la herramienta de macOS; Pillow no escribe .icns bien.

    Los nombres de adentro del .iconset no son decorativos: `iconutil` los
    exige exactos y falla si falta alguno de los que espera.
    """
    with tempfile.TemporaryDirectory() as tmp:
        conjunto = Path(tmp) / "icono.iconset"
        conjunto.mkdir()
        for base in (16, 32, 128, 256, 512):
            dibujar(base).save(conjunto / f"icon_{base}x{base}.png")
            dibujar(base * 2).save(conjunto / f"icon_{base}x{base}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(conjunto), "-o", str(destino)],
                       check=True, capture_output=True)
    print(f"  {destino.relative_to(RAIZ)}  (16 a 1024 px, con @2x)")


def comparar() -> Path:
    """Lo dibuja sobre varios fondos y a varios tamaños.

    El fondo del ícono es claro, así que sobre una barra de tareas clara casi
    no tiene contorno. Esta hoja es para mirar ese riesgo antes de decidir.
    """
    fondos = [("claro", (255, 255, 255)), ("gris", (203, 208, 214)),
              ("oscuro", (28, 32, 38))]
    lados = [128, 64, 48, 32, 16]
    M, PASO = 28, 150
    hoja = Image.new("RGB", (M * 2 + PASO * len(lados), M * 2 + 150 * len(fondos)))
    d = ImageDraw.Draw(hoja)
    for f, (_, color) in enumerate(fondos):
        y0 = M + f * 150
        d.rectangle([0, y0 - 14, hoja.width, y0 + 136], fill=color)
        for i, lado in enumerate(lados):
            im = dibujar(lado)
            hoja.paste(im, (M + i * PASO + (128 - lado) // 2,
                            y0 + (128 - lado) // 2), im)
    salida = RAIZ / "docs" / "imagenes" / "icono-contraste.png"
    salida.parent.mkdir(parents=True, exist_ok=True)
    hoja.save(salida)
    return salida


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("accion", nargs="?", default="generar",
                        choices=["generar", "comparar"])
    args = parser.parse_args(argv)
    if args.accion == "comparar":
        print(comparar())
        return 0
    print("generando:")
    generar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
