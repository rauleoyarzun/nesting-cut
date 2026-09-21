# Recortes de placa, y cuatro ajustes de interfaz

*[English](2026-09-21-recortes-y-ajustes-design.md)*

Fecha: 2026-09-21
Estado: aprobado

## 1. Qué se construye

Cinco cosas, una grande y cuatro chicas.

**La grande: recortes.** Poder decir "me sobran dos pedazos de 600x800" y que
el acomodo los use antes de abrir una placa nueva. Un recorte no es un
material: no se guarda en el catálogo, no tiene nombre, y vive nada más que
mientras el programa está abierto. Es lo que quedó de un trabajo anterior y
está apoyado contra la pared.

**Las cuatro chicas**, todas de interfaz:

- La resolución arranca en 1 mm/px en vez de 2.
- Los ángulos se eligen por cantidad de posiciones (4, 8 ó 16) en vez de
  tipearse uno por uno.
- La solapa `Revisión` pasa a la izquierda, y `Previsualización` se llama
  `Resultado`.
- La rueda del mouse deja de saltar por una escalera fija: el zoom pasa a ser
  continuo y proporcional al gesto.

### Fuera de alcance, a propósito

- **Guardar los recortes.** Se pierden al cerrar el programa, y así tiene que
  ser: un recorte que quedó anotado tres semanas después ya se cortó, se
  perdió o se traspapeló, y un catálogo que miente sobre el material que hay
  es peor que no tener catálogo.
- **Un inventario de sobrantes.** Este trabajo no descuenta, no lleva saldo y
  no registra qué quedó después de cortar. Sólo acepta una lista para la
  corrida que viene.
- **Elegir a mano en qué placa va cada pieza.** El motor sigue decidiendo solo.
- **Recortes de forma irregular.** Un recorte es un rectángulo. Un pedazo en L
  se carga como el rectángulo más grande que entra adentro.

## 2. Las decisiones, y por qué

### 2.1 Un recorte no es un material

El catálogo describe lo que se compra: una medida de placa que se repite
igual cada vez que se pide. Un recorte es lo contrario -- una unidad, una
medida, y cuando se cortó dejó de existir. Meterlos en el mismo lugar
obligaría a inventar un campo "cantidad" en el catálogo que no significa nada
para un material de verdad, y a limpiar a mano entradas muertas.

Por eso los recortes son un parámetro de la corrida, al lado de `copias` y
`separación`, y no una entrada del catálogo.

### 2.2 Cuando se acaban los recortes, se sigue con placas del Material

El Material elegido no deja de importar: define la veta, y su placa es la que
se abre cuando los recortes no alcanzan. El plan de placas es entonces
"primero estos recortes, después placas nuevas hasta que sobren".

La alternativa -- limitarse a los recortes y fallar si no entra -- se
descartó. El caso real es "usá lo que sobró y lo que falte sacalo de una placa
nueva", no "decime si me alcanza".

### 2.3 El objetivo es menos placas **nuevas**, no menos placas

Es la decisión que más cambia el comportamiento del motor, y la que tiene la
trampa más fácil de pisar.

`CostoLayout` hoy ordena por cantidad de placas antes que por nada. Si un
recorte contara como una placa, el motor preferiría saltearse un recorte de
600x800 y meter todo en una placa nueva -- una placa contra dos -- que es
exactamente lo contrario de lo que se pide. Un recorte es material que ya
está pago: llenarlo no cuesta nada.

Entonces el primer campo del costo pasa a contar **sólo las placas del
Material**. Sin recortes, ese número es idéntico al de hoy, así que ninguna
corrida existente cambia de resultado.

### 2.4 Los recortes se consumen de mayor a menor

El motor los ordena solo por área, de mayor a menor, sin importar en qué
orden se cargaron. Si el recorte chico fuera primero, una pieza mediana que
sólo entra en el grande podría quedar varada porque el grande se llenó de
piezas que también entraban en el chico.

No hay control en pantalla para cambiar este orden. Sería un control más para
una decisión que el motor toma mejor.

Un recorte más grande que la placa del Material se acepta sin chistar: es raro
pero no es un error, y rechazarlo obligaría a explicar una regla que no
protege de nada.

### 2.5 Un recorte donde no entró nada no existe

Hoy, que una placa quede vacía es fatal: significa que hay una pieza que no
entra en ninguna parte. Con recortes eso deja de ser cierto -- un recorte de
200x300 puede no aceptar ni la pieza más chica, y eso es normal.

Un recorte vacío se saltea y desaparece del resultado: no aparece como
"Placa 3 -- 0%" en la previsualización, no ocupa un rectángulo vacío en el
DXF, y no entra en el promedio de aprovechamiento. Una placa **del Material**
vacía sigue siendo el error duro de siempre, y es el que produce el mensaje
de "esta pieza no entra en una placa vacía".

El bucle termina igual: los recortes son finitos, así que saltearlos lleva
tarde o temprano a una placa del Material, donde o entra algo o se levanta el
error.

### 2.6 La veta cruzada es por recorte

Un pedazo de 600x800 de fenólico puede tener la veta a lo largo del 600 o del
800, según cómo salió de la placa madre. Es información que sólo tiene quien
está mirando el pedazo.

Cada recorte trae entonces una casilla `veta cruzada`. Marcada, el eje de veta
de esa placa corre a lo ancho en vez de a lo alto, y las orientaciones
permitidas se calculan contra ese eje. Las orientaciones dejan de calcularse
una vez por corrida y pasan a calcularse **por placa**.

En un material de veta libre (MDF) la casilla no cambiaría nada, así que sale
deshabilitada cuando el Material elegido tiene veta libre. Una casilla que se
puede marcar y no hace nada enseña que la interfaz miente.

### 2.7 `discard_plate_outline` sigue mirando sólo la placa del Material

Esa función tira los rectángulos que alguien dibujó del tamaño exacto de la
placa para previsualizar en su CAD. Extenderla a las medidas de los recortes
parece consistente y es una trampa: una pieza real de 600x800 desaparecería
sin aviso el día que se carga un recorte de 600x800. Con 1830x2600 el choque
es improbable; con medidas de recorte, que son medidas de pieza, es probable.

Queda como está, y el spec lo dice para que no se "arregle" después.

### 2.8 La recuperación pasa a comparar costos en vez de razonarlos

`_recuperar_de_la_ultima_placa` acepta su resultado sin compararlo, apoyada en
un argumento escrito en su docstring: si la última placa se vacía baja el
conteo de placas, que es el primer campo del costo, así que el layout nunca
empeora.

Con `placas_nuevas` ese argumento deja de valer. Si la última placa es un
**recorte** y se vacía, `placas_nuevas` no baja -- nunca contó ese recorte --
y la "última placa" pasa a ser otra, con posiblemente más material arriba:
`material_ultima` sube y el layout se acepta siendo peor.

Se arregla con una guarda explícita al final de la función: se devuelve el
layout recuperado sólo si su `CostoLayout` no es peor que el de entrada. Es
una comparación barata, y cambia una garantía razonada por una verificada.

### 2.9 El zoom de la rueda pasa a continuo; los botones no

El zoom salta por nueve escalones fijos y **cada evento de rueda avanza un
escalón entero**. Un gesto de trackpad manda decenas de eventos, así que un
toque va de 25% a 600% sin escala intermedia.

La rueda pasa a multiplicar el zoom por un factor exponencial en `deltaY`,
acotado entre 0,1 y 6: un toquecito mueve poco, un gesto largo mueve mucho, y
el gesto es reversible. Los botones `+` y `-` y el doble clic siguen con la
escalera de siempre, que es donde los números redondos sirven.

`deltaY` se normaliza por `deltaMode`: Firefox reporta líneas y no píxeles, y
sin normalizar el mismo gesto daría un salto distinto en cada navegador.

### 2.10 Resolución 1 mm/px por omisión, con su costo escrito

Pedido explícito. Cuadruplica los píxeles del raster, así que las corridas van
a tardar bastante más y a comer más memoria.

Los tiempos que documenta `packer.py` -- 48 s sobre el archivo de referencia,
450 s sobre `banqueta final raulo.ai` a 5 copias -- se midieron a 2,0 mm/px.
Esa nota se actualiza para decir a qué resolución se midió y que el valor por
omisión ya no es ese. No se vuelve a correr el barrido: medirlo de nuevo es un
trabajo aparte, y dejar la nota mintiendo en silencio es peor que dejarla
diciendo qué no cubre.

## 3. Arquitectura

### 3.1 `Sheet` y `SheetSupply`

Archivo nuevo, `src/nesting/model/sheet.py`:

```python
@dataclass(frozen=True)
class Sheet:
    width: float
    height: float
    grain_tolerance: float
    cross_grain: bool = False
    scrap: bool = False

    @property
    def area(self) -> float: ...


@dataclass(frozen=True)
class SheetSupply:
    """Qué placa es cada una, en orden. Los recortes se agotan; la del
    Material no."""
    stock: Sheet
    scraps: tuple[Sheet, ...] = ()

    def sheet(self, index: int) -> Sheet:
        return self.scraps[index] if index < len(self.scraps) else self.stock
```

`allowed_angles` se muda de `material.py` a `sheet.py` y pasa a tomar un
`Sheet`. Con `cross_grain=True` la distancia se mide contra el eje a 90
grados: `_distance_to_grain_axis(angle - 90.0)`, que el `% 180` de adentro ya
normaliza.

`Material` no cambia -- sigue siendo la entrada del catálogo -- y gana
`stock_sheet()`, que devuelve su `Sheet` con `scrap=False` y
`cross_grain=False`.

### 3.2 El packer

`_pack_once` y `pack` reciben `SheetSupply` donde hoy reciben `Material`.

El bucle de placas lleva dos contadores, y ahí está la sutileza: el índice en
el plan y el índice en el resultado **dejan de coincidir** en cuanto se
saltea un recorte.

```
siguiente = 0            # próxima placa del plan
usadas: list[Sheet] = []  # las que de verdad recibieron algo

while remaining:
    hoja = supply.sheet(siguiente); siguiente += 1
    oracle.reset(hoja.width, hoja.height, config)
    choices = orientations(hoja, config)      # por placa, no por corrida

    # las colocaciones se arman contra len(usadas), que es el índice que
    # esta placa VA A TENER si termina recibiendo algo
    ...

    if placed_count == 0:
        if hoja.scrap:
            continue                          # el recorte no sirve, se saltea
        _raise_too_large(still_pending[0], hoja, config, choices)

    result.placements.extend(las_de_esta_placa)
    usadas.append(hoja)
```

`PackResult` gana `sheets: list[Sheet]`. Es el cambio que deja de obligar a
todo lo de abajo a adivinar la medida de cada placa, y `sheets_used` pasa a
ser `len(sheets)`. `utilization[i]` se calcula contra `sheets[i].area`, no
contra un área única.

`orientations(sheet, config)` reemplaza a `orientations(material, config)`.

`_raise_too_large` pasa a recibir el `Sheet` y, aparte, el nombre del
material: un `Sheet` no tiene nombre, y el mensaje que ve el usuario --
"el área útil de la placa mdf18 es ..." -- lo necesita. Se levanta siempre
contra la placa del Material, nunca contra un recorte, así que el nombre
siempre corresponde.

### 3.3 El costo del layout

```python
@dataclass(frozen=True, order=True)
class CostoLayout:
    placas_nuevas: int      # cuántas placas del Material se abrieron
    material_ultima: float  # área de pieza en la última placa usada, en mm²
    alto_ultima: float      # hasta dónde llega el material en esa placa, en mm
```

`placas_nuevas = sum(1 for s in result.sheets if not s.scrap)`. La "última
placa" sigue siendo literalmente la última del resultado.

Sin recortes, `placas_nuevas == sheets_used` y los otros dos campos no
cambian de definición: el costo es idéntico al de hoy, campo por campo.

`_compact_last_sheet` reempaca la última placa contra
`SheetSupply(stock=esa_hoja)`. Sigue comparando sólo `.alto_ultima`, que es lo
único que esa pasada puede mejorar.

`_recuperar_de_la_ultima_placa` reempaca cada placa anterior contra
`SheetSupply(stock=result.sheets[placa])`, usa el área de esa placa para el
aprovechamiento, y termina con la guarda de la sección 2.8.

El `Resultado` de `corredor.py` gana `recortes_usados: int` -- cuántas de
`resultado.sheets` eran recortes. Sin ese campo la pantalla no puede escribir
"2 recortes + 1 nueva" sin volver a contar por su cuenta algo que el motor ya
sabe.

### 3.4 `verify`, DXF y preview

`verify()` es la regla más dura del motor: si falla, no se escribe nada. Pasa
a recibir `sheets: Sequence[Sheet]` y a chequear cada colocación contra **su**
placa, no contra una medida global. Es el cambio más importante de los tres:
una pieza que se sale de un recorte de 600x800 tiene que dar violación aunque
entre holgada en una placa de 1830x2600.

`write_dxf` y `write_preview` hoy ubican la placa `i` en
`i * (sheet_w + gap)`. Pasan a acumular el offset: `sum(anchos anteriores) +
(i + 1) * gap`. El preview además toma el alto del lienzo de la placa más
alta, y dibuja cada rectángulo con su propia medida.

### 3.5 Parámetros, API y CLI

En `nesting/params.py`:

```python
@dataclass(frozen=True)
class Recorte:
    ancho: float
    alto: float
    cantidad: int = 1
    veta_cruzada: bool = False

NestParams.recortes: tuple[Recorte, ...] = ()
NestParams.resolucion: float = 1.0      # era 2.0
```

`validar()` suma tres reglas con la forma que ya tiene (`ReglaRota` con
`campo`, `regla`, `valor`): `ancho > 0`, `alto > 0`, `cantidad >= 1`. El campo
se nombra con su posición -- `recorte 2: ancho` -- para que el error diga cuál
de la lista.

Una función nueva en el mismo archivo arma el plan:

```python
def a_supply(p: NestParams, material: Material) -> SheetSupply
```

Expande cada recorte a `cantidad` copias, les pone la `grain_tolerance` del
material y su `cross_grain`, marca `scrap=True`, ordena por área de mayor a
menor, y las pone delante de `material.stock_sheet()`.

En `nesting_app/api.py`, `ParamsEntrada` suma `recortes: list[RecorteEntrada]`
(vacía por omisión) y su `resolucion` por omisión pasa a 1.0. Pydantic sigue
chequeando sólo tipos; los rangos los pone `validar()`, que es el mismo código
que corre la CLI.

En la CLI, `--recorte ANCHOxALTO[xCANTIDAD][,cruzada]`, repetible. Ejemplos:
`--recorte 600x800`, `--recorte 600x800x2`, `--recorte 600x800x2,cruzada`. Un
formato mal escrito da un error de parseo que muestra el formato esperado.

### 3.6 La pantalla

**`index.html`:**

- Debajo del selector de Material, un bloque `Recortes` con su botón de info y
  un enlace `Agregar`. El enlace abre una fila inline con cuatro controles:
  ancho, alto, cantidad, y la casilla `veta cruzada`. Abajo, la lista de los
  cargados, cada uno con su medida y una `✕`.
- En Opciones avanzadas, antes del campo de ángulos, un desplegable
  `Posiciones`: `4 — 0, 90, 180, 270`, `8 — cada 45°`, `16 — cada 22,5°`,
  `Personalizado`. Arranca en 4. El campo de texto de ángulos queda, oculto,
  y sólo aparece con `Personalizado`.
- `value="1"` en el campo de resolución.
- Las dos solapas se dan vuelta en el DOM: primero `Revisión`, después la que
  ahora dice `Resultado`. Los ids (`tab-revision`, `tab-preview`) y el nombre
  del archivo del servidor (`preview.png`) **no se tocan**: renombrarlos es
  churn en cinco archivos sin nada a cambio.

**`app.js`:**

- `estado.recortes`, una lista de `{ancho, alto, cantidad, veta_cruzada}`. Es
  estado de la sesión: sobrevive a cambiar de archivo (`registrar()` no la
  toca) y se pierde al cerrar. `parametros()` la manda como `recortes`.
- Una función chica dibuja la lista desde `estado.recortes`; agregar y quitar
  la modifican y vuelven a dibujar. Sin framework, igual que el resto.
- Al cambiar de Material se consulta su veta y la casilla `veta cruzada` se
  deshabilita si es libre. El dato ya viene en `/api/materiales`.
- `angulosDelCampo()` pasa a `angulosElegidos()`: si `Posiciones` es un
  número, devuelve `[i * 360/n for i in range(n)]`; si es `Personalizado`,
  parsea el texto como hoy, con la misma validación y el mismo error debajo
  del campo.
- El `wheel` deja de llamar a `acercar()` y pasa a:
  `zoom = clamp(anterior * Math.exp(-normalizado * SENSIBILIDAD), 0.1, 6)`,
  conservando el mismo ajuste de scroll que mantiene el punto bajo el cursor.
  `acercar()` queda para los botones.
  `normalizado` es `deltaY` llevado a píxeles: por 16 si `deltaMode` es 1
  (líneas, Firefox), por 100 si es 2 (páginas), tal cual si es 0.
  `SENSIBILIDAD = 0.0015` es el punto de partida -- con eso una muesca de
  rueda típica (100 px) mueve el zoom un 16%, y un gesto de trackpad
  completo recorre el rango sin pasarse. Es un número de tacto: se ajusta
  probándolo, y el test sólo verifica que la rueda no use `PASOS_ZOOM`.
- `terminar()` escribe el reparto: `3 placas (2 recortes + 1 nueva)`, o
  `2 placas` cuando no hubo recortes.

**`info.js`:** un globo nuevo para `Recortes` y uno para `Posiciones`. El de
Resolución cambia de texto: hoy nombra 2 mm/px como valor por omisión.

## 4. Cómo se ve

```
Material                        Agregar o editar
[ mdf18                              v ]

Recortes                                Agregar
  600 x 800 mm  x2                            ✕
  450 x 1200 mm  x1  · veta cruzada           ✕
```

Con la fila de carga abierta:

```
Recortes
  [ ancho ] x [ alto ] mm   x [ 2 ]
  [ ] veta cruzada          Agregar   Cancelar
```

Al terminar, en la barra de abajo:

```
3 placas (2 recortes + 1 nueva) · 78,4% aprovechado · sobrante 412 mm ...
```

## 5. Tests

**Motor** (`tests/engine/`, `tests/model/`):

- Un recorte que entra se llena antes que la placa del Material.
- Un recorte donde no entra ninguna pieza se saltea y **no aparece** en
  `result.sheets` ni en `utilization`.
- Una pieza que no entra en ninguna placa sigue levantando `PartTooLargeError`,
  y el mensaje nombra la placa del Material, no el último recorte.
- Sin recortes, `layout_cost` da exactamente lo mismo que antes del cambio
  (campo por campo) sobre un escenario fijo.
- `placas_nuevas` no cuenta recortes: un layout de tres recortes y cero placas
  nuevas cuesta menos que uno de una placa nueva.
- `cross_grain` rota el eje: en un material de veta 5 grados, un recorte
  cruzado permite 90/270 y prohíbe 0/180.
- La guarda de 2.8: un caso armado donde vaciar el último recorte sube
  `material_ultima` y la recuperación **devuelve el layout de entrada**.
- `SheetSupply.sheet(i)` devuelve recortes hasta agotarlos y después siempre
  la del Material.

**Geometría e IO:**

- `verify()` marca violación cuando una pieza se sale de **su** recorte aunque
  entraría en la placa del Material. Este es el test que importa: sin él, un
  DXF malo llega a la fresadora.
- `write_dxf` y `write_preview` con placas de anchos distintos: los
  rectángulos no se pisan y cada uno tiene su medida.
- `discard_plate_outline` **no** descarta una pieza del tamaño de un recorte.

**Parámetros y API** (`tests/test_params.py`, `tests/app/`):

- `validar()` rechaza ancho 0, alto negativo y cantidad 0, nombrando cuál de
  la lista.
- `a_supply()` expande la cantidad, ordena por área y hereda la veta del
  material.
- El default de `resolucion` es 1.0 en `NestParams` y en `ParamsEntrada`.
- `--recorte` parsea las tres formas y rechaza la basura con el formato
  esperado en el mensaje.

**Interfaz** (`tests/app/test_web_javascript.py`, con su estilo de aserciones
sobre el texto del archivo):

- `Revisión` aparece antes que `Resultado` en el HTML, y la palabra
  `Previsualización` ya no está.
- El campo de resolución tiene `value="1"`.
- Existe el desplegable de posiciones con 4, 8 y 16, y `Personalizado` revela
  el campo de texto.
- La rueda no usa `PASOS_ZOOM`, y sí normaliza `deltaMode`.
- `registrar()` no borra `estado.recortes`.
- `parametros()` manda `recortes`.
- Cada globo nuevo de `info.js` tiene su botón en el HTML y viceversa (el test
  de conjuntos iguales que ya existe lo cubre solo).

## 6. Cambios al código que ya existe

| Archivo | Qué le pasa |
|---|---|
| `src/nesting/model/sheet.py` | Nuevo. `Sheet`, `SheetSupply`, `allowed_angles`. |
| `src/nesting/model/material.py` | Pierde `allowed_angles`, gana `stock_sheet()`. |
| `src/nesting/engine/packer.py` | `SheetSupply` en vez de `Material`; bucle con dos contadores; `PackResult.sheets`; `CostoLayout.placas_nuevas`; guarda en la recuperación; nota de tiempos actualizada. |
| `src/nesting/geometry/verify.py` | Recibe `sheets` y chequea cada colocación contra la suya. |
| `src/nesting/io/dxf_writer.py` | Offsets acumulados, medida por placa. |
| `src/nesting/io/preview.py` | Offsets acumulados, alto del lienzo por la placa más alta. |
| `src/nesting/params.py` | `Recorte`, `NestParams.recortes`, `a_supply()`, tres reglas nuevas, `resolucion = 1.0`. |
| `src/nesting/cli.py` | `--recorte` repetible, default de `--resolucion`, arma el `SheetSupply`. |
| `src/nesting_app/api.py` | `RecorteEntrada`, `ParamsEntrada.recortes`, default de resolución. |
| `src/nesting_app/corredor.py` | Arma el `SheetSupply`, pasa `sheets` a `verify`/`write_dxf`/`write_preview`, `sobrante_mm` contra la última placa, reparta recortes/nuevas en el `Resultado`. |
| `src/nesting_app/web/index.html` | Bloque de recortes, desplegable de posiciones, `value="1"`, solapas dadas vuelta. |
| `src/nesting_app/web/app.js` | `estado.recortes`, lista, `angulosElegidos()`, rueda continua, reparto en `terminar()`. |
| `src/nesting_app/web/app.css` | Reglas para la lista de recortes y la fila de carga. |
| `src/nesting_app/web/info.js` | Dos globos nuevos, uno reescrito. |
| `README.md` / `README.es.md` | Fila de Recortes en la tabla de opciones, `--recorte`, nuevo default de resolución. |
| `packaging/` | Nada: el `.spec` declara la carpeta `web` entera. |
