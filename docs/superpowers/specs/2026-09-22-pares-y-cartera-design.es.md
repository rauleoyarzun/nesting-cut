# Pares encastrados y una cartera de combinaciones en paralelo

*[English](2026-09-22-pares-y-cartera-design.md)*

Fecha: 2026-09-22
Estado: aprobado

## 1. Qué se construye

`BANQUETA ALTA NESTING.ai` (57 piezas: seis marcos iguales de 1055×450 y
listones; placa 1220×2440 con veta libre, sep 8, borde 5, 8 posiciones)
sale en **2 placas**. Diego lo acomodó a mano en **1**, verificado.

### 1.1 Por qué falla el motor de hoy

- Ubica pieza por pieza en el mejor lugar del momento (abajo-izquierda más
  contacto) y nunca vuelve atrás. Cuando pone el primer marco no sabe que
  conviene dejarle lugar al segundo en una posición exacta.
- Los reintentos de `normal` y `lento` sólo permutan el orden de inserción.
  Seis copias idénticas permutadas dan el mismo acomodo: esos reintentos no
  exploran nada.
- Medido: forzar las orientaciones de Diego, o elegir la orientación al azar
  entre las cuatro mejores (10 semillas), sigue dando 2 placas.

### 1.2 Lo que sí funcionó (experimento del 2026-09-22)

1. Buscar las mejores maneras de encastrar **dos copias** de un marco: todas
   las posiciones relativas de golpe por FFT, 2,5 s para 16 orientaciones.
2. Fundir cada **par** en una sola pieza compuesta.
3. Ofrecerle al motor actual, sin tocarlo, esas piezas compuestas en lugar
   de los marcos sueltos.

Resultados, cada uno una pasada golosa de ~150 s a 1 mm/px:

| tipos de par para los tres pares | placas |
|---|---|
| sin pares (hoy) | 2 |
| el de caja mínima (1812×450) ×3 | 2 |
| diagonal (1511×560) ×3 | 2 |
| apilado (1055×879) ×3 | 2 |
| diagonal ×1 + apilado ×2 | 2 |
| **diagonal ×2 + apilado ×1** | **1** |
| **diagonal ×2 + apilado alternativo (1055×886) ×1** | **1** |

Dos lecciones que definen el diseño:

- **Ningún tipo de par gana solo.** La combinación ganadora mezcla dos
  tipos, que es exactamente lo que hizo Diego. Hay que probar combinaciones.
- **Probarlas en paralelo es casi gratis.** Cinco pasadas simultáneas
  tardaron lo mismo que una: el motor de hoy usa un núcleo de catorce.

### 1.3 Qué se construye

- **Piezas iguales**: el motor reconoce las copias de una misma forma,
  aunque estén dibujadas corridas, giradas o espejadas.
- **Pares**: para las formas repetidas más grandes, busca varios tipos de
  encastre de dos copias.
- **Cartera**: arma variantes (sin pares, distintas combinaciones de tipos
  de par, distintas orientaciones) y las acomoda en paralelo, una por
  núcleo. Gana la de menor `CostoLayout`, el criterio de siempre.
- **Núcleos**: un control nuevo para elegir cuántos usar.
- **"No se puede con menos placas"**: cuando el resultado iguala la cota
  mínima por área, se dice.

### 1.4 Fuera de alcance

- Grupos de tres o más copias encastradas. Los pares cubren el caso que
  falló; si aparece uno que necesite tríos, se mide primero.
- Pares de dos piezas distintas (un marco con un listón). La cartera con
  piezas sueltas ya los resuelve bien: el listón entra en el hueco.
- Cotas mínimas geométricas (como la de la columna de marcos con veta). La
  única cota que se informa es la de área.
- Acelerar una sola combinación con varios núcleos. Es la fase 2 (sección
  8), sujeta a medición.

## 2. Piezas iguales

Módulo nuevo `nesting/engine/iguales.py`.

Dos piezas son **iguales** cuando una se lleva sobre la otra con una
traslación más una orientación **permitida por la corrida**: los ángulos que
la veta deja y el espejo sólo si está habilitado. La regla depende de la
corrida a propósito: con la veta respetada, un marco dibujado girado 90° no
es igual a otro dibujado acostado, porque llevarlo al otro rompería la veta.

- Una **huella** rápida descarta casi todo: área neta, perímetro, cantidad
  de agujeros y área de cada agujero, redondeados a 0,01 mm.
- Entre piezas con la misma huella se confirma con geometría exacta: se
  prueba cada orientación permitida y se alinea por el vértice inferior
  izquierdo de la caja. Si el área de la diferencia simétrica queda por
  debajo de 1 mm², son iguales, y se guarda la transformación `g` que lleva
  cada pieza sobre la representante de su clase.
- Resultado: `list[Clase]`, cada una con su pieza representante y, por
  miembro, `(part_id, g)`.

## 3. Pares

Módulo nuevo `nesting/engine/pares.py`.

### 3.1 Qué clases se emparejan

Las clases con **dos o más** miembros cuya pieza ocupa al menos el **2% del
área útil** de la placa, hasta **dos clases**, las de pieza más grande
primero. Un listón emparejado casi no gana lugar y sí multiplica
combinaciones.

### 3.2 Tipos de par

Se fija la copia A en la identidad. Para cada orientación permitida de la
copia B:

- `A.occupied` se correlaciona con `B.clearance` por FFT, usando las mismas
  máscaras del `MaskCache` de la corrida. Los desplazamientos con cero
  superposición son los encastres posibles.
- De cada desplazamiento se calcula el área de la caja del par a partir de
  las cajas en píxeles, sin rasterizar nada más.
- Se toman los mejores por área de caja, **con supresión de vecinos**: dos
  candidatos de la misma orientación a menos de 200 mm uno del otro son el
  mismo encastre, y un tipo cuya pieza compuesta tiene la misma forma que
  la de uno ya guardado tampoco cuenta como nuevo. El experimento mostró que
  sin supresión los doscientos mejores son todos el mismo y el par en
  diagonal no aparece; al escribir el plan se midió que con 60 mm los seis
  tipos de normal salían de una sola familia corrida de a 60 mm y el
  apilado recién aparecía séptimo.

Cada candidato se confirma con geometría exacta: la separación real entre A
y B tiene que ser al menos `sep` y **menos de `2·sep`**. El tope garantiza
que el puente de 3.3 no le quita lugar a nadie: en un hueco de menos de dos
separaciones no entra ninguna pieza. Además, el par tiene que entrar en el
área útil de la placa en alguna orientación permitida.

Se guardan hasta `TIPOS_POR_CLASE` tipos: **6 en normal, 10 en lento**.

**Cuando la corrida respeta la veta:** la orientación de B relativa a A
tiene que ser 0° ó 180°, y la del par entero también se limita a lo que la
veta permite. Así cada miembro termina en un ángulo permitido. Con recortes
de veta cruzada vale lo mismo: la composición de dos ángulos del eje de la
veta sigue en el eje.

**Sin espejo:** B no puede ser espejada, y la clase no puede haber usado
espejo en `g`, por la regla de 2.

### 3.3 La pieza compuesta

Un par se convierte en una `Part` común, para que el oráculo, las máscaras y
el empacador no se enteren de nada:

- `outer` = A ∪ B ∪ un **puente**: el segmento entre los dos puntos más
  cercanos de A y B, engrosado a 1 mm. El experimento mostró que el cierre
  morfológico (dilatar y erosionar) no sirve: dos marcos que se tocan por
  una esquina se vuelven a separar al erosionar.
- `holes` = los agujeros de A y B, que siguen disponibles para los listones.
- El resultado tiene que ser un solo polígono. Si no lo es, el candidato se
  descarta.
- La compuesta lleva una tabla de miembros `(part_id, t)`, donde `t` es la
  transformación de ese miembro dentro del par (`g` compuesta con la
  identidad para A, y con la relativa para B).

### 3.4 Desarmar

Cada colocación de una compuesta con transformación `T` se convierte en una
colocación por miembro, con `T ∘ t`. La composición vive en
`nesting/geometry/transform.py` (`componer`), junto a `apply_point`, que es
la única definición de qué hace una transformación. El ángulo resultante es
`T.ángulo + (−t.ángulo si T.espejo, si no t.ángulo)`, el espejo es
`T.espejo xor t.espejo`, y la traslación es `apply_point(T, (t.dx, t.dy))`.

Se desarma **antes** de verificar, y el verificador de siempre revisa las
piezas reales. Una compuesta nunca llega a `verify`, al DXF ni a la
previsualización.

## 4. La cartera

Módulo nuevo `nesting/engine/cartera.py`. `pack()` pasa a delegar en él.

### 4.1 Variantes

Una **variante** es una lista de piezas (sueltas y compuestas), un orden de
inserción y, opcionalmente, una perturbación de orientaciones. Se generan
**en un orden fijo** que depende sólo de las piezas, la config y la semilla:

1. **Base**: la pasada de hoy, sin pares y por área.
2. **Combinaciones de pares**: para cada clase emparejable con `n` miembros,
   se prueba cada cantidad de pares `p` de `⌊n/2⌋` a 1, y cada multiconjunto
   de `p` tipos. Los miembros que sobran van sueltos. Con dos clases se
   combinan entre sí. El orden es por área total de cajas, de menor a mayor,
   y los empates por índice de tipo.
3. **Perturbaciones de orden**: las de hoy (`_perturb` sobre `by_area`).
4. **Perturbaciones de orientación** (lento): para las piezas del decil
   superior de área, elegir al azar, con la semilla, entre las tres
   orientaciones de mejor puntaje en vez de la mejor. Se aplica también
   sobre la mejor combinación de pares encontrada.

### 4.2 Cuántas se evalúan

Sea `N` la cantidad de núcleos elegida (sección 6).

| esfuerzo | variantes evaluadas | pares |
|---|---|---|
| rápido | 1 (base) | no |
| normal | base + una tanda | 6 tipos por clase |
| lento | base + tres tandas | 10 tipos por clase, más perturbaciones de orientación |

Una **tanda** son `max(N, 12)` variantes: nunca menos de 12, aunque haya
menos núcleos, y entonces se evalúan en varias vueltas de `N`. Decisión del
usuario: el resultado no puede depender de la máquina. Sobre la banqueta la
combinación ganadora sale octava, y con tandas de `N` una computadora de 4
núcleos no la encontraba ni en lento. Con el mínimo, toda máquina de hasta 12
núcleos prueba exactamente las mismas variantes; una de 4 tarda unas tres
veces más en normal, y el tiempo estimado lo avisa antes de arrancar.

Las tandas se llenan en el orden de 4.1: primero combinaciones de pares,
después perturbaciones de orden y, en lento, de orientación. Si no hay
clases emparejables, las tandas se llenan con perturbaciones.

**Garantía de monotonía**: con el mismo `N` y la misma semilla, las
variantes de normal son un prefijo de las de lento, y rápido es un prefijo
de normal. Por eso `lento ≤ normal ≤ rápido` sigue valiendo por
construcción, como hoy. Con distinto `N` la garantía no aplica, y así se
documenta: más núcleos exploran más.

### 4.3 Cuándo no se busca

Si la base ya da `placas_nuevas == cota_minima` (5.1), no se evalúa nada
más: no hay nada que ganar en placas, y el resto del criterio (material en
la última) sólo se mejora con la recuperación y la compactación de siempre.
Así, un trabajo que entra holgado en una placa no paga ni un segundo de más.

### 4.4 Paralelo

- `concurrent.futures.ProcessPoolExecutor` con contexto `spawn` en todas
  las plataformas, para que macOS, Windows y Linux se comporten igual.
  `multiprocessing.freeze_support()` va al principio de `desktop.main` y de
  `cli.main`, porque PyInstaller lo exige.
- Cada proceso arma su propio `MaskCache` y su oráculo. Recibe las piezas,
  la config, el plan de placas y la variante, y devuelve `PackResult` más
  `CostoLayout`.
- **Cortar lo que ya perdió**: un valor compartido guarda el menor
  `placas_nuevas` de las variantes terminadas. Una variante que abre una
  placa más que ese número se abandona, porque nunca podría ganar. El
  resultado no depende de cuándo termina cada proceso: sólo se cortan
  variantes estrictamente peores.
- **Desempate determinista**: entre costos iguales gana la de menor índice
  de variante. El resultado no depende del orden de llegada.
- La recuperación (`_recuperar_de_la_ultima_placa`) y la compactación
  (`_compact_last_sheet`) corren sólo sobre la ganadora, en el proceso
  principal y todavía con compuestas. Se desarma al final.

### 4.5 Avance, cancelación y tiempo estimado

- Cada proceso manda por una `multiprocessing.Queue` sus consultas hechas.
  El principal las suma y emite `Avance` con `consultas_hechas` y
  `consultas_previstas` (spec de tiempo estimado, 2.1). La previsión de una
  tanda es la suma de sus variantes, y como corren en paralelo el
  estimador divide por el rendimiento conjunto medido, no por el de un
  núcleo.
- El texto de avance pasa a decir "Probando combinaciones 5 de 12 · placa
  mínima hasta ahora: 1", en lugar del conteo de piezas del intento, que en
  paralelo deja de tener sentido.
- **Cancelar**: un `multiprocessing.Event` compartido; cada proceso lo mira
  en su aviso y levanta `Cancelado`. El principal cierra el pool con
  `cancel_futures=True` y levanta `Cancelado`. No queda ningún proceso
  vivo.

## 5. Confianza: la cota mínima

### 5.1 La cota

`cota_minima = ⌈área neta de las piezas / área útil de la placa del
Material⌉`, con área útil `(ancho − 2·borde) × (alto − 2·borde)`. Se
calcula sólo sin recortes; con recortes no se informa, porque la cuenta
honesta con placas de distinto tamaño no es esa.

### 5.2 Qué se muestra

- Si `placas == cota_minima`: "**No se puede con menos placas.**" en el
  resultado, y la misma línea en la salida de la CLI.
- Si no, nada. Que el área permita menos placas no quiere decir que
  entren: la banqueta con veta tiene cota 1 y el mínimo real es 2.

## 6. Núcleos

- `NestParams.nucleos: int | None = None`; `None` significa el valor por
  omisión.
- **Por omisión**: `max(1, os.cpu_count() − 2)`, con un tope por memoria:
  `⌊memoria total × 0,5 / 400 MB⌋`. Los 400 MB son el presupuesto del
  `MaskCache` (256 MB) más las grillas de placa y el propio proceso,
  medidos en la implementación y documentados donde viva la constante.
- La memoria total se lee con `os.sysconf` en macOS y Linux, y con
  `GlobalMemoryStatusEx` por `ctypes` en Windows. No se agregan
  dependencias.
- `validar` exige `nucleos >= 1`. Un valor por encima del tope se acepta y
  se recorta al tope, con un aviso.
- **Pantalla**: control nuevo debajo de Esfuerzo: **Núcleos** · [ 12 ▾ ] de
  14, con el botón de información: "Más núcleos prueban más combinaciones
  en el mismo tiempo. Dejá alguno libre si vas a usar la computadora
  mientras acomoda." El desplegable va de 1 al tope. La ruta de estado
  nueva `GET /api/sistema` devuelve `{"nucleos": 14, "tope": 12,
  "omision": 12}`.
- **CLI**: `--nucleos N`.
- El tiempo estimado previo (spec de tiempo estimado, 3.2) multiplica las
  consultas previstas de una pasada por las vueltas de cada tanda,
  `⌈max(N, 12) / N⌉`.

## 7. Pruebas

- `iguales`: una pieza y su copia trasladada, girada 90° y espejada son de
  la misma clase con la config libre; con la veta respetada la girada 90°
  no lo es; sin espejo la espejada no lo es; `g` lleva cada miembro sobre la
  representante (diferencia simétrica < 1 mm²).
- `pares`: sobre el marco de la banqueta aparecen el tipo diagonal (caja
  1511×560 ± 5 mm) y el apilado (1055×879 ± 5 mm); todo candidato cumple
  `sep ≤ separación < 2·sep`; con la veta respetada ningún candidato tiene
  B a 90°; la compuesta es un solo polígono y conserva los agujeros.
- `componer`: para transformaciones al azar, aplicar `componer(T, t)` es
  igual que aplicar `t` y después `T`.
- Desarmar: el `verify` sobre las piezas reales desarmadas no encuentra
  nada, con espejo y sin espejo.
- Cartera: las variantes salen en el mismo orden para la misma semilla; el
  resultado es el mismo con 1 y con 4 procesos para la misma lista de
  variantes (determinismo); normal es prefijo de lento; una variante con
  más placas que la mejor se corta; cancelar no deja procesos vivos.
- Cota: se informa "No se puede con menos placas" cuando corresponde, y
  nunca con recortes.
- **La prueba que importa**: `BANQUETA ALTA NESTING.ai` se copia a
  `bench/files/banqueta-alta.ai`, que **no se versiona** (`bench/files/` ya
  está en `.gitignore`: los archivos de diseño son trabajo del usuario). Con
  placa 1220×2440 libre, sep 8, borde 5, 8 posiciones, esfuerzo normal,
  1 mm/px: **1 placa**, verificada. Con multilam18 (veta): 2 placas, y sin el
  cartel de mínimo (cota 1). Es un test lento, marcado como tal, que **se
  saltea con un motivo claro si el archivo no está**, y además una fila del
  bench. Para que la suite no dependa sólo de ese archivo, un test rápido
  fabrica un caso sintético con la misma trampa: seis copias de una pieza
  en L que sólo entran en una placa si se encastran de a pares con dos tipos
  distintos.
- Empaquetado: el `--autotest` de `packaging/construir.sh` hace una corrida
  con 2 procesos, porque un `spawn` sin `freeze_support` funciona en el
  repo y se cuelga en el ejecutable.

## 8. Fase 2: acelerar una sola combinación (sujeta a medición)

Cuando la tanda ocupa todos los núcleos, repartir una combinación no suma
nada. Sí suma en rápido y en trabajos sin piezas repetidas. Dos ideas, que
se miden antes de decidir:

- **No repetir trabajo**: hoy, para cada una de las 16 orientaciones de una
  pieza, `fftconvolve` vuelve a transformar la placa, que no cambió. Si la
  transformada de la placa se reutiliza entre orientaciones (a un tamaño de
  FFT común), se gana en cualquier máquina.
- **Repartir orientaciones**: las 16 consultas de una pieza son
  independientes y se pueden repartir en hilos, si scipy libera el GIL en
  las FFT.

Criterio: se implementa lo que baje al menos un 30% el tiempo de rápido
sobre `bench/files`, con el mismo resultado byte a byte. Si ninguna llega,
se documenta la medición y no se hace.
