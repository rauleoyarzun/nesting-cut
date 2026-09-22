# Veta por corrida, y posiciones que la respetan

*[English](2026-09-22-veta-por-corrida-design.md)*

Fecha: 2026-09-22
Estado: aprobado

## 1. Qué se construye

Hoy la veta vive sólo en el catálogo. Elegir multilam18 fija "respetar la
veta" sin que la pantalla lo diga, y el motor descarta en silencio todo
ángulo que no sea 0° o 180°: quien elige "8 posiciones" cree que se prueban
ocho y se prueban dos.

Lo encontró un trabajo real (`BANQUETA ALTA NESTING.ai`, multilam18, sep 8,
borde 5, 8 posiciones): el programa dio 2 placas, y un acomodo a mano entró
en 1 girando cuatro marcos 90°. Ese acomodo rompe la veta; con la veta
respetada, 1 placa es imposible (la columna de seis marcos más apretada a 0°
y 180° mide 2530 mm contra 2430 útiles). El programa no se equivocó: no
avisó.

Dos cambios:

1. **La veta se ve y se cambia por corrida.** Un control nuevo en la
   pantalla principal, que arranca con el valor del material y se puede
   cambiar sin tocar el catálogo.
2. **Las posiciones obedecen a la veta.** Con la veta respetada, Posiciones
   queda fija en 0° y 180°; si el usuario tenía otra cosa elegida, un cartel
   se lo dice en el momento del conflicto y le deja elegir.

### Fuera de alcance

- Tolerancias de veta intermedias (por ejemplo 15°). La interfaz sigue
  hablando en dos palabras, "respetar" y "no importa", igual que el
  catálogo.
- Guardar la elección por corrida. Se pierde al cambiar de material, a
  propósito (ver 2.2).

## 2. Las decisiones, y por qué

### 2.1 La veta es un parámetro de la corrida con valor por omisión

El catálogo dice lo que el material *suele* necesitar. Un trabajo concreto
puede no necesitarlo: piezas que no se ven, un fenólico usado de base. Por
eso la veta se comporta como los recortes: es de esta corrida, no del
catálogo. El catálogo sólo da el valor inicial.

### 2.2 Cambiar de material reinicia la veta

Elegir otro material vuelve el control al valor de ese material. Arrastrar
un "no importa" de un MDF a un multilam sería justamente el error silencioso
que este trabajo corrige.

### 2.3 El cartel aparece apenas hay conflicto, no al acomodar

Hay conflicto cuando la veta queda en "respetar" y las posiciones elegidas
incluyen algún ángulo que la veta no permite. Eso puede pasar por tres
caminos: elegir un material con veta, pasar el control a "respetar", o tipear
ángulos personalizados. En los tres el cartel sale en ese momento: enterarse
al tocar Acomodar, después de cargar todo, es enterarse tarde.

El cartel ofrece dos salidas y ninguna es "cancelar", porque no hay un estado
neutro al que volver:

> **Este material respeta la veta**
> Sólo se puede girar a 0° y 180°. Tenías elegidas 8 posiciones.
> [Usar 0° y 180°]   [No me importa la veta]

- **Usar 0° y 180°** deja la veta en "respetar" y fija Posiciones.
- **No me importa la veta** pasa el control a "no importa" y conserva las
  posiciones que había.

Cuatro posiciones (0, 90, 180, 270) también es conflicto: 90 y 270 se
descartarían. El cartel dice cuántas posiciones había, sea cual sea.

### 2.4 Con la veta respetada, Posiciones se bloquea y recuerda

El desplegable muestra "2 — 0° y 180°", deshabilitado, con una línea debajo:
"El material respeta la veta". Lo que el usuario tenía antes se guarda, y al
pasar la veta a "no importa" el desplegable vuelve a ese valor. La lista de
Ángulos personalizada también se guarda y vuelve.

### 2.5 La veta cruzada de los recortes mira el control, no el material

La casilla "Veta cruzada" ya se apaga en materiales libres. Pasa a apagarse
cuando el *control* dice "no importa", sea por el material o por elección.

## 3. Motor, API y CLI

- `NestParams` gana `veta: Literal["respetar", "libre"] | None = None`.
  `None` significa "la del material".
- Una función nueva en `nesting.params`, `tolerancia_de_veta(p, material)`,
  devuelve los grados que valen para la corrida: los del material si `veta`
  es `None`, `VETA_RESPETAR` o `VETA_LIBRE` si no. Las dos constantes se
  mudan de `nesting_app.materials_store` a `nesting.model.material`, porque
  el motor no puede importar la interfaz.
- `a_supply` usa esa tolerancia para la placa del material y para cada
  recorte.
- `validar` rechaza una corrida cuyo conjunto de ángulos quede vacío después
  de filtrar por veta, con un mensaje que dice qué ángulos se pidieron y
  cuáles permite la veta. Hoy eso termina en un `PartTooLargeError` que
  habla de medidas, no de ángulos. `validar` necesita la tolerancia para
  esto, así que recibe el material como argumento opcional; sin material no
  hace esa comprobación.
- `ParamsEntrada` gana `veta: Literal["respetar", "libre"] | None = None`.
- La CLI gana `--veta {respetar,libre}`, por omisión la del material, y
  arma su plan de placas con `a_supply` en vez de a mano, para que la regla
  viva en un solo lugar.
- La ruta de materiales ya devuelve `veta` por material; el JavaScript la usa
  como valor inicial del control.

## 4. Pantalla

- Control nuevo debajo de Material, con su botón de información:
  **Veta** · ( ) Respetar — sólo 0° y 180° · ( ) No importa.
- El texto de información de Posiciones y de Ángulos pierde la frase "si el
  material respeta la veta, sólo se usan 0° y 180°": ahora la pantalla lo
  muestra en vez de explicarlo.
- El cartel usa el mismo componente que `cartel-unidades` y `cartel-error`.

## 5. Pruebas

- `tolerancia_de_veta`: `None` devuelve la del material; `respetar` y
  `libre` pisan a cualquiera de los dos.
- `a_supply`: la tolerancia llega igual a la placa del material y a los
  recortes.
- `validar` con material: rechaza `angulos=(90,)` con veta respetada y lo
  acepta con veta libre; sin material no lo mira.
- CLI: `--veta libre` sobre multilam18 deja girar 90° (una pieza que sólo
  entra acostada entra); `--veta respetar` sobre mdf18 no.
- API: `veta` viaja hasta `NestParams`; omitirlo da `None`.
- Interfaz (los tests de `tests/app` que ya leen el JavaScript): cambiar de
  material reinicia el control; el conflicto muestra el cartel en los tres
  caminos; cada botón del cartel deja el estado que dice 2.3; volver a "no
  importa" restaura Posiciones y Ángulos.
