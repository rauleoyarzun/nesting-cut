# Interfaz gráfica para el sistema de nesting

Fecha: 2026-09-19
Estado: aprobado

## 1. Qué se construye

Una interfaz gráfica sobre el motor que ya existe, que se distribuye como
programa de escritorio para Windows y Mac, y que el día que se quiera publicar
en la web se despliega **sin rehacer la interfaz**.

El alcance de esta primera versión es **lo que ya hace la CLI, bien
presentado**. No suma capacidades al motor salvo las dos que la interfaz
necesita para no mentir (avance y cancelación).

### Fuera de alcance, a propósito

- **Cantidades por pieza.** Hoy `--copias` repite el archivo entero. Poder
  pedir 4 de una pieza y 2 de otra es la función que más se extraña en la vida
  real, pero toca el motor además de la interfaz y queda para después.
- **Acomodar a mano.** Arrastrar una pieza y que el motor respete dónde quedó.
  Es lo que hace eCut y exige verificación de colisiones en vivo.
- **Instalador (.msi / setup.exe).** Se suma después sin tocar el programa.
- **Tests automáticos de la interfaz.** Lista de verificación manual en esta
  primera vuelta; montar Playwright ahora sería más infraestructura que
  producto.
- **La versión web en sí.** Esta spec la deja alcanzable, no la construye.

## 2. Las decisiones, y por qué

### 2.1 El motor se queda en Python. Lo que se comparte es la interfaz.

`numpy`, `scipy`, `shapely` y `rhino3dm` son bibliotecas compiladas. Correr el
motor en el navegador no es viable. Por lo tanto lo que viaja entre escritorio
y web no es el motor: es la interfaz, y sólo si está hecha en HTML/CSS/JS
hablándole a una API HTTP.

Una interfaz nativa (Qt, wxPython) daría un mejor programa de escritorio y
**cerraría el camino web por completo**. Se descarta por eso, no por otra
cosa.

### 2.2 La API es por trabajos, no pedido-respuesta.

Medido sobre `files/robot_raaulo.ai`: `rapido` 34 s, `lento` 3 min 54 s,
`lento` con 8 ángulos 9 min 5 s. Eso no entra en un request HTTP.

En escritorio con un solo usuario se podría resolver con un hilo y listo. Se
elige igual la forma "mandá el trabajo, preguntá cómo va, tomá el resultado"
porque es la que necesita la web, y retrofitearla después es reescribir. Hoy
no cuesta nada.

### 2.3 Ventana nativa con webview, no el navegador del sistema.

Se evaluó levantar el servidor y abrir Chrome en `localhost`: cero
dependencias nuevas e idéntico en las dos plataformas.

Se descarta porque pierde **los diálogos nativos de archivo**. En un navegador
sólo se puede subir contenido y bajar a Descargas; no hay "Guardar como". Para
una herramienta de corte, donde el DXF va a una carpeta de trabajo junto al
resto del proyecto, esa diferencia se siente en cada uso. Además la barra de
direcciones delata que no es un programa, y si se cierra la pestaña el
servidor queda corriendo invisible.

Se evaluó Tauri (ejecutables mucho más chicos, actualización automática) y se
descarta por ahora: suma Rust y una cadena de compilación entera a un proyecto
que hoy es Python puro, y el Python empaquetado hay que armarlo igual.

### 2.4 Dirección visual: D · Moderno.

Elegida entre cuatro maquetadas en
<https://claude.ai/artifact/SmUpS9U8sNKfRSuesnbEEs>.

Es la más accesible para alguien que no viene de CAD, y la única de las cuatro
que el día que se publique en la web no va a parecer una app de escritorio
metida en un navegador.

**Tokens:**

| | |
|---|---|
| Fondo | `#F4F6F8` |
| Panel | `#FFFFFF` |
| Fondo del dibujo | `#EDF0F4` |
| Texto | `#111827` |
| Texto secundario | `#606B7B` |
| Bordes | `#E2E6EC`, 1 px |
| Acento | `#047857` |
| Texto sobre acento | `#FFFFFF` |
| Radio | 10 px (botones 8 px) |
| Alto de control | 44 px |
| Sombra de panel | `0 1px 2px rgba(17,24,39,.06), 0 4px 12px rgba(17,24,39,.05)` |
| Tipografía | Plus Jakarta Sans |
| Placa / piezas | relleno `#FFFFFF` / `#E7EDF3`, trazo `#A9B4C2` / `#3F5468` |

El acento es `#047857` y no `#059669` porque el segundo da 3,4:1 contra blanco
y no alcanza para texto chico.

**Cifras tabulares.** Toda medida en pantalla lleva
`font-variant-numeric: tabular-nums`. La interfaz es una grilla de medidas que
se comparan entre sí, y en cifras proporcionales `1830` y `1220` no alinean.
Plus Jakarta Sans las trae, así que no hace falta cambiar de familia.

### 2.5 Empaquetado: carpeta comprimida, no archivo único.

PyInstaller en modo carpeta, distribuida como zip. El modo de archivo único se
autodescomprime **en cada arranque**, y con 300 MB son varios segundos cada
vez que se abre el programa.

El `.exe` de Windows **no se puede compilar desde Mac**: PyInstaller no cruza
plataformas. Lo arma GitHub Actions.

## 3. Arquitectura

```
src/nesting/          el motor de hoy. Un solo cambio: el callback de avance.
src/nesting/cli.py    sigue funcionando igual. No es un camino que se abandona.
src/nesting/params.py los parámetros de una corrida, con su validación
src/nesting_app/      nuevo
    api.py            las rutas HTTP
    jobs.py           el registro de trabajos y el hilo que los corre
    materials_store.py  el catálogo editable en la carpeta del usuario
    archivos.py       la puerta de plataforma: escritorio contra web
    rutas.py          dónde están los datos, congelado o no
    desktop.py        levanta el servidor y abre la ventana
    web/              index.html, app.js, app.css
```

**`nesting_app` conoce a `nesting`, nunca al revés.** El motor no sabe que
existe una interfaz, igual que hoy no sabe que existe una CLI.

Bibliotecas nuevas: `fastapi`, `uvicorn`, `pywebview`.

## 4. La API

```
POST   /api/archivos            sube un archivo (web) → {fuente_id}
POST   /api/archivos/local      registra una ruta local (escritorio) → {fuente_id}
POST   /api/analizar            {fuente_id} → piezas, descartes, unidades
POST   /api/trabajos            {fuente_id, parámetros} → {id}
GET    /api/trabajos/{id}       estado, avance, avisos, resultado
POST   /api/trabajos/{id}/cancelar
GET    /api/trabajos/{id}/salida.dxf
GET    /api/trabajos/{id}/preview.png
GET    /api/trabajos/{id}/diagnostico.png
GET    /api/materiales          y POST, PUT, DELETE
POST   /api/materiales/restaurar
```

### 4.1 Estados de un trabajo

`pendiente` → `corriendo` → `listo` | `cancelado` | `error`

### 4.2 El avance se mide en piezas, dentro de un intento

Cuántas placas van a hacer falta **no se sabe de antemano**: el motor las
descubre mientras trabaja. "Placa 2 de 3" sería inventado.

Cuántas piezas hay sí se sabe desde el principio. Pero `pack()` corre varias
pasadas completas y se queda con la mejor —1 en `rapido`, 3 en `normal`, 12 en
`lento`, según `EFFORT_RESTARTS`— y **cada pasada reinicia el conteo**. Un
porcentaje que retrocede es peor que no tener ninguno.

El avance honesto lleva las dos cosas, y la cantidad de intentos se sabe desde
el arranque porque sale de `EFFORT_RESTARTS[esfuerzo]`:

> *intento 2 de 3 · ubicadas 61 de 93 · placa 1*

La barra se llena con `piezas_ubicadas / piezas_totales` y se reinicia visible
en cada intento, que es lo que de verdad está pasando.

Después de los intentos hay un paso más, `_compact_last_sheet`, que se informa
como *"compactando la última placa"* sin barra: es una sola pasada corta y
fingir un porcentaje ahí sería inventar otra vez.

### 4.3 Cancelar es cooperativo

Se levanta una bandera y el motor sale limpio en el próximo punto de corte,
que es el mismo callback del avance. No se mata el hilo.

### 4.4 La puerta de plataforma

| | Escritorio | Web |
|---|---|---|
| Abrir | diálogo nativo, devuelve una ruta | `<input type=file>`, sube |
| Guardar | "Guardar como" nativo | descarga |

Los dos caminos terminan en un `fuente_id` que el resto del sistema usa sin
preguntar de dónde salió. **Es el único lugar del código que sabe dónde está
corriendo.**

### 4.5 Un trabajo a la vez

En escritorio corre un solo hilo trabajador. Un trabajo mandado mientras otro
corre queda en `pendiente`; la interfaz además deshabilita "Acomodar" mientras
hay uno en curso, así que en la práctica la cola no se usa — pero la API la
respeta igual, porque en la web sí se va a usar.

Para la web se cambia el hilo único por una cola con varios procesos **sin
tocar la API**, que es el punto de haberla diseñado así.

### 4.6 Archivos temporales

Cada `fuente_id` y cada trabajo tienen su carpeta bajo el directorio temporal
del sistema. Se borran al cerrar el programa, y al arrancar se limpia lo que
haya quedado de una corrida anterior que terminó mal.

Un DXF de salida vive ahí hasta que el usuario aprieta "Guardar DXF", que lo
copia al destino que eligió. **Cerrar el programa sin guardar pierde el
resultado**, y la interfaz avisa antes de cerrar si hay uno sin guardar.

## 5. Las pantallas

Ventana de 1100 × 720, redimensionable, mínimo 960 × 640.

### 5.1 Principal

Una sola ventana, **no un asistente por pasos**: el trabajo real es iterativo
—correr, mirar, cambiar la separación, volver a correr— y un asistente obliga
a recorrerlo entero para tocar un número.

```
┌─────────────────────────────┬──────────────────────────────────┐
│  Archivo                    │                                  │
│  robot_raaulo.ai   Cambiar  │                                  │
│  93 piezas · 3 descartes ›  │        el dibujo, grande         │
│                             │                                  │
│  Material        [mdf18  ▾] │  ( Previsualización | Revisión ) │
│  Separación      [3     ]mm │                                  │
│  Borde           [10    ]mm │                                  │
│  Copias          [1     ]   │                                  │
│  Esfuerzo        [Normal ▾] │                                  │
│                             │                                  │
│  › Opciones avanzadas       │                                  │
├─────────────────────────────┴──────────────────────────────────┤
│  [ Acomodar ]   1 placa · 47,7% · sobrante 1830×708  [Guardar] │
└────────────────────────────────────────────────────────────────┘
```

Arriba, las cinco opciones que se tocan. Plegadas en "Opciones avanzadas", las
siete que no: ángulos, espejo, unidades, tolerancia de cierre, resolución,
catálogo de materiales alternativo.

**El archivo se analiza apenas se elige.** Antes de tocar un parámetro ya dice
"93 piezas · 3 descartes", y ese "3 descartes" es un link que cambia el panel
derecho a la imagen de revisión. `/api/analizar` corre en ~1 s.

**El panel derecho tiene dos solapas**, Previsualización y Revisión. Al
principio sólo está Revisión, porque todavía no se acomodó nada.

**Durante la corrida**, la barra inferior muestra el avance y un botón de
cancelar en lugar del resultado.

**"Guardar DXF" es explícito.** El archivo se arma en una carpeta de trabajo y
no va a ningún lado hasta que se aprieta guardar. Nada aparece solo en
Descargas ni al lado del archivo de entrada.

### 5.2 Materiales

Se llega desde el desplegable de material ("Administrar materiales…") y desde
la barra superior. Tabla con nombre, ancho, alto y veta; agregar, editar,
borrar; y un panel de formulario al costado.

La veta **no se muestra como un número entre 0 y 180**, porque nadie sabe qué
significa 5:

- **La veta no importa** — la pieza gira libre *(MDF)* → `tolerancia_veta: 180`
- **Respetar la veta** — sólo 0 y 180 grados *(multilaminado, fenólico)* → `5`

Se guardan en la carpeta de datos del usuario:

- Windows: `%APPDATA%\nesting\materials.yaml`
- macOS: `~/Library/Application Support/nesting/materials.yaml`

La primera vez se copia ahí el catálogo que trae el programa. Queda un botón
para restaurar ese original.

### 5.3 Las unidades dejan de ser un error

Hoy, un archivo que no declara unidades corta la corrida con
`UnknownUnitsError` y un mensaje que manda a usar `--unidades`. En una
interfaz eso no puede ser un error: es una pregunta. Aparece un cartel con los
cinco botones (mm, cm, m, in, ft) y se sigue.

## 6. Empaquetado y distribución

- **PyInstaller en modo carpeta**, distribuida en un zip.
- **GitHub Actions** con `windows-latest` y `macos-latest`, disparado por tag.
- **El puerto se pide libre al sistema** (`port 0`), nunca uno fijo.
- **El servidor escucha sólo en `127.0.0.1`** y exige un token que la ventana
  ya trae en la URL. Sin eso, cualquier página abierta en el navegador del
  usuario podría mandarle trabajos al programa.
- **WebView2 se verifica al arrancar.** Si falta, un cartel con el link de
  descarga. Sin eso la ventana abre en blanco y no hay forma de adivinar qué
  pasó. Windows 11 lo trae siempre; Windows 10 casi siempre.
- Un `.exe` sin firmar dispara la advertencia de SmartScreen. Se acepta en
  esta versión; firmarlo cuesta plata y trámite.
- Peso estimado: 250-400 MB en disco, 100-150 MB comprimido. A medir.

## 7. Errores

| Situación | En la ventana |
|---|---|
| Unidades sin declarar | la pregunta con los cinco botones (5.3) |
| Contorno abierto | cartel con el hueco en mm y dónde está, y el campo de tolerancia de cierre a un click |
| Pieza más grande que la placa | nombra la pieza, su medida y la del área útil |
| Verificación fallida (código 2) | en rojo, con **no se escribió ningún archivo** y la lista de problemas |
| Parámetro inválido | debajo del campo que lo tiene mal |
| Catálogo de materiales corrupto | se nombra el error y se ofrece restaurar el original |

**`ChainingInvariantError` no es un error del usuario, es un bug del
programa.** Hoy revienta a propósito, sin atajar, porque significa que el
encadenador perdió geometría. En la ventana no puede disfrazarse de "revisá tu
dibujo": dice que el problema es del programa y da un detalle copiable. Lo
mismo para cualquier excepción inesperada, que además va a
`<carpeta de datos>/log.txt`.

## 8. Cambios al código que ya existe

1. **`pack()` recibe un callback de avance opcional**, que se llama al ubicar
   cada pieza con `(piezas_ubicadas, piezas_totales, placa_en_curso)` y cuyo
   valor de retorno pide abandonar. Es el único cambio al motor. La CLI no lo
   usa y su comportamiento no cambia.
2. **`_validate_numeric_args` sale de `cli.py` a `params.py`**, para que la
   CLI y la API validen con el mismo código y no con dos copias que se
   despegan.
3. **`DEFAULT_MATERIALS_PATH` deja de calcularse como
   `Path(__file__).parents[3]`**, que dentro de un ejecutable congelado no da.
   Pasa por `rutas.py`, que distingue congelado de no congelado.

Ninguno de los tres cambia el comportamiento observable de la CLI.

## 9. Tests

**Los 495 tests del motor no se tocan.** Es la prueba de que el corte entre
motor e interfaz está bien puesto: si hubiera que cambiar un test del motor
para meter una interfaz, el corte estaría mal.

Se suman:

- **La API**, con el cliente de prueba de FastAPI: el ciclo completo de un
  trabajo, cancelar a mitad de una corrida, parámetros inválidos rechazados en
  el borde, `/api/analizar`, y que un `fuente_id` inexistente no reviente.
- **El catálogo de materiales**: guardar y releer, un archivo corrupto,
  restaurar el original, y la resolución de rutas congelado y no congelado.
- **Los parámetros**, movidos de `cli.py` y ahora compartidos.
- **Una prueba sobre el ejecutable congelado.** El programa acepta
  `--autotest`: levanta el servidor, pide `/api/materiales`, y sale con cero.
  Lo corre GitHub Actions después de compilar.

Esa última ataja la clase de error que más duele: rutas que no resuelven, un
módulo que PyInstaller no encontró, `materials.yaml` que no está donde el
código lo busca. **Esos bugs no aparecen nunca en los tests normales**,
aparecen cuando el usuario abre el programa. Ya sabemos que
`DEFAULT_MATERIALS_PATH` es uno de ellos.

## 10. Lo que esta spec deja listo para la web

El día que se quiera publicar, el trabajo que queda es: desplegar el servidor,
sumar usuarios y aislamiento, cambiar el hilo único por una cola de procesos,
y aguantar el costo de CPU (cada trabajo ocupa un núcleo durante minutos).

**Nada de eso toca la interfaz.**
