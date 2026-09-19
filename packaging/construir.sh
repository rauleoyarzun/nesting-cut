#!/usr/bin/env bash
# Arma el ejecutable y lo verifica antes de comprimirlo.
#
# El paso de verificación no es opcional: un paquete al que le falta un
# recurso o un módulo oculto se ve perfecto acá y falla en la máquina del
# que lo recibe.
set -euo pipefail

cd "$(dirname "$0")/.."
RAIZ="$PWD"

echo "== limpiando =="
rm -rf build dist

echo "== construyendo =="
.venv/bin/pyinstaller --noconfirm --distpath dist --workpath build packaging/nesting.spec

echo "== verificando el paquete =="
if [[ "$OSTYPE" == "darwin"* ]]; then
  ./dist/Nesting/Nesting --autotest
else
  ./dist/Nesting/Nesting.exe --autotest
fi

echo "== comprimiendo =="
PLATAFORMA="$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
cd dist && zip -qr "Nesting-${PLATAFORMA}.zip" Nesting && cd "$RAIZ"

echo
du -sh dist/Nesting
ls -lh dist/*.zip
