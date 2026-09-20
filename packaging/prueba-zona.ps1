# Prueba el paquete como le llega al que lo recibe, no como queda acá.
#
# Windows le pone a todo archivo que sale de un .zip bajado con el navegador
# un flujo alternativo llamado `Zone.Identifier`, y el Explorador se lo
# propaga a cada cosa que descomprime -- incluido el .zip de adentro, y todo
# lo que salga de ése. A Python la marca no le importa; a .NET sí, y se
# niega a cargar un assembly marcado. Como la ventana la dibuja .NET, el
# programa arranca, sirve la API, y muere al abrir la ventana.
#
# La máquina que ARMA el paquete no tiene esa marca en ningún lado: sus
# archivos los acaba de escribir PyInstaller. Por eso el autotest de
# construir.ps1 pasa acá y el programa falla allá, y por eso esta prueba
# marca el paquete a mano antes de correrlo. Es la máquina del usuario, no
# la del CI, lo que hay que reproducir.
#
# Corre dos veces a propósito:
#
#   1. Con NESTING_SIN_DESMARCAR, que apaga la defensa del programa. Tiene
#      que FALLAR. Es lo que prueba que la marca es de verdad la causa y no
#      una teoría cómoda; si un día deja de fallar, Windows o .NET cambiaron
#      y la defensa dejó de hacer falta. No rompe la corrida: que el bug ya
#      no se reproduzca no es motivo para no publicar nada.
#
#   2. Sin la variable. Tiene que PASAR: el programa se desmarca a sí mismo
#      antes de tocar .NET. Esto sí corta la corrida, porque si falla es
#      exactamente lo que le va a pasar al que reciba el .zip.

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$raiz = $PWD.Path
$carpeta = Join-Path $raiz "dist\Nesting"
$exe = Join-Path $carpeta "Nesting.exe"

# El paso que llama a esto corre con `always()` para no perder información
# cuando algo anterior falló. Si lo que falló fue el armado, no hay paquete
# que probar: eso no es un error nuevo, ya está contado en el paso que lo
# armó.
if (-not (Test-Path $exe)) {
    Write-Host "no hay paquete en $carpeta; no hay nada que probar"
    exit 0
}

function Set-MarcaDeInternet {
    Get-ChildItem -Recurse -File $carpeta | ForEach-Object {
        Set-Content -Path $_.FullName -Stream Zone.Identifier `
            -Value "[ZoneTransfer]`r`nZoneId=3"
    }
}

function Invoke-Autotest {
    # La misma ceremonia que construir.ps1, y por la misma razón: con
    # `console=False` el .exe es un binario de subsistema gráfico, así que
    # lanzarlo a secas devuelve el control al instante con código 0 y sin
    # salida. `Start-Process -Wait -PassThru` espera y trae el código real;
    # las redirecciones son lo único que rescata el mensaje de error.
    $salida = Join-Path $raiz "zona-salida.txt"
    $errores = Join-Path $raiz "zona-error.txt"
    $proceso = Start-Process -FilePath $exe -ArgumentList "--autotest" `
        -Wait -PassThru -RedirectStandardOutput $salida -RedirectStandardError $errores
    foreach ($archivo in @($salida, $errores)) {
        if ((Test-Path $archivo) -and (Get-Item $archivo).Length -gt 0) {
            Get-Content $archivo | ForEach-Object { Write-Host "   $_" }
        }
    }
    Remove-Item $salida, $errores -ErrorAction SilentlyContinue
    return $proceso.ExitCode
}

Write-Host "== marcando el paquete como bajado de internet =="
Set-MarcaDeInternet

Write-Host "== sin la defensa puesta: el autotest tiene que fallar =="
$env:NESTING_SIN_DESMARCAR = "1"
$codigo = Invoke-Autotest
Remove-Item Env:\NESTING_SIN_DESMARCAR
if ($codigo -eq 0) {
    Write-Host "   OJO: pasó igual, con la defensa apagada y todo marcado."
    Write-Host "   En este Windows la marca ya no frena a .NET: el bug que"
    Write-Host "   esta prueba reproduce dejó de reproducirse."
} else {
    Write-Host "   falló con $codigo, que es lo que se espera: la marca es la causa."
}

Write-Host "== con la defensa puesta: el autotest tiene que pasar =="
# Se vuelve a marcar para que esta corrida no dependa de lo que haya hecho
# la anterior.
Set-MarcaDeInternet
$codigo = Invoke-Autotest
if ($codigo -ne 0) {
    throw "el paquete no sobrevive a la marca de internet (código $codigo): " +
          "al que reciba el .zip le va a pasar lo mismo"
}

# Que la carpeta quede como estaba, para no dejarle sorpresas a quien la
# abra después en la misma máquina.
Get-ChildItem -Recurse -File $carpeta | Unblock-File
Write-Host "el paquete sobrevive a la marca de internet"
