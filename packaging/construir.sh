#!/usr/bin/env bash
# Arma el ejecutable de macOS y lo verifica antes de comprimirlo.
#
# El paso de verificación no es opcional: un paquete al que le falta un
# recurso o un módulo oculto se ve perfecto acá y falla en la máquina del
# que lo recibe.
#
# Windows va por packaging/construir.ps1, y no por una rama de acá. Este
# script TENÍA esa rama y estaba rota justamente en el paso que lo justifica:
# con `console=False` el .exe queda como binario de subsistema gráfico, así
# que `./dist/Nesting/Nesting.exe --autotest` devuelve el control al instante
# con código 0, sin esperar a que termine y sin recoger su salida. Decía
# "autotest ok" sin haber verificado nada. Esperar de verdad en Windows
# necesita `Start-Process -Wait -PassThru`, que no tiene equivalente acá.
set -euo pipefail

cd "$(dirname "$0")/.."
RAIZ="$PWD"

if [[ "$OSTYPE" != "darwin"* ]]; then
  echo "Este script es para macOS. En Windows: packaging/construir.ps1" >&2
  exit 1
fi

echo "== limpiando =="
rm -rf build dist

echo "== construyendo =="
.venv/bin/pyinstaller --noconfirm --distpath dist --workpath build packaging/nesting.spec

# El autotest incluye una corrida de la cartera con 2 procesos: un spawn sin
# freeze_support anda en el repo y se cuelga en el ejecutable.
echo "== verificando el paquete =="
./dist/Nesting/Nesting --autotest

echo "== comprimiendo =="
PLATAFORMA="$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
cd dist && zip -qr "Nesting-${PLATAFORMA}.zip" Nesting && cd "$RAIZ"

echo
du -sh dist/Nesting
ls -lh dist/*.zip
