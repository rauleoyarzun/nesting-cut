# Arma el ejecutable de Windows y lo verifica antes de comprimirlo.
#
# Es el equivalente de construir.sh, que quedó sólo para macOS. No es un
# capricho tener dos: la verificación no se puede escribir igual en los dos
# lados, y ese paso es el que justifica todo el script.
#
# Con `console=False` en el .spec -- que es lo correcto, porque si no aparece
# una ventana negra de consola detrás del programa -- el .exe queda como
# binario de subsistema gráfico. Lanzarlo desde una shell devuelve el control
# al instante, con código 0, sin esperar a que termine y sin que su salida
# llegue a ningún lado. Un `.\Nesting.exe --autotest` a secas diría "todo
# bien" sin haber verificado absolutamente nada.
#
# `Start-Process -Wait -PassThru` sí espera y sí devuelve el código real, y
# las dos redirecciones son las que rescatan el mensaje de error: sin ellas,
# cuando falla no queda ni rastro de por qué.

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$raiz = $PWD.Path

# Desde el venv si existe (uso local), o del PATH (integración continua).
$pyinstaller = Join-Path $raiz ".venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $pyinstaller)) { $pyinstaller = "pyinstaller" }

Write-Host "== limpiando =="
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

Write-Host "== construyendo =="
& $pyinstaller --noconfirm --distpath dist --workpath build packaging\nesting.spec
if ($LASTEXITCODE -ne 0) { throw "pyinstaller salió con $LASTEXITCODE" }

Write-Host "== verificando el paquete =="
$salida = Join-Path $raiz "autotest-salida.txt"
$error_ = Join-Path $raiz "autotest-error.txt"
$proceso = Start-Process -FilePath (Join-Path $raiz "dist\Nesting\Nesting.exe") `
    -ArgumentList "--autotest" -Wait -PassThru `
    -RedirectStandardOutput $salida -RedirectStandardError $error_
foreach ($archivo in @($salida, $error_)) {
    if ((Test-Path $archivo) -and (Get-Item $archivo).Length -gt 0) {
        Get-Content $archivo | ForEach-Object { Write-Host "   $_" }
    }
}
Remove-Item $salida, $error_ -ErrorAction SilentlyContinue
if ($proceso.ExitCode -ne 0) {
    throw "el autotest falló con código $($proceso.ExitCode): al paquete le falta algo"
}

Write-Host "== comprimiendo =="
$arquitectura = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "x64" }
$zip = Join-Path $raiz "dist\Nesting-windows-$arquitectura.zip"
Compress-Archive -Path (Join-Path $raiz "dist\Nesting") -DestinationPath $zip -Force

$carpeta = (Get-ChildItem -Recurse (Join-Path $raiz "dist\Nesting") |
    Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host ""
Write-Host ("dist\Nesting  {0:N0} MB" -f $carpeta)
Write-Host ("{0}  {1:N0} MB" -f (Split-Path $zip -Leaf), ((Get-Item $zip).Length / 1MB))
