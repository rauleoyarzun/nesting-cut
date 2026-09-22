# Tiempo estimado, antes y durante el acomodo

*[English](2026-09-22-tiempo-estimado-design.md)*

Fecha: 2026-09-22
Estado: aprobado

## 1. Qué se construye

Un acomodo puede tardar de segundos a más de diez minutos: `BANQUETA ALTA
NESTING.ai` con 8 posiciones y giro libre tardó 651 s; con veta, 126 s. Hoy
la barra dice cuántas piezas van, pero no cuánto falta, y antes de arrancar
no dice nada. Quien elige 8 posiciones no sabe que acaba de quintuplicar la
espera.

Dos cifras:

1. **Mientras corre:** "Faltan aprox. 9 min · termina ~17:42", que se afina
   a medida que avanza.
2. **Antes de arrancar:** "Tarda aprox. 10 min" al lado de Acomodar, que se
   recalcula al cambiar las opciones que pesan.

### Fuera de alcance

- Un historial de corridas para aprender la velocidad de la máquina. La
  prueba en vivo (3.2) alcanza y no deja archivos en la carpeta del usuario.
- La estimación en la CLI.

## 2. La unidad de trabajo es la consulta

Una **consulta** es una llamada a `Oracle.best_placement(part, angle,
mirror)`: dónde entra esta pieza, en esta orientación, en esta placa. Casi
todo el tiempo de `pack` se va en eso, y cada consulta cuesta del mismo
orden sobre una misma placa y resolución.

Contar piezas ubicadas, como hace hoy la barra, engaña: una pieza que no
entra en la placa 1 gasta sus consultas igual y las vuelve a gastar en la
placa 2; y las fases finales (recuperación, compactación) no ubican piezas
nuevas pero son una parte grande del tiempo.

### 2.1 Qué informa el motor

`Avance` gana dos campos:

- `consultas_hechas: int` -- acumuladas desde que empezó `pack`, sin
  reiniciarse entre intentos ni entre fases.
- `consultas_previstas: int` -- la mejor previsión del total en ese momento.

La previsión se construye por fases y se corrige a medida que se sabe más:

- **Al arrancar:** por cada intento, `piezas × orientaciones` en la primera
  placa, más las pendientes que se vuelven a consultar en placas
  siguientes, con la cantidad de placas estimada por área (área de piezas
  sobre área útil, dividido un aprovechamiento típico de 0,4). Más una
  pasada por cada placa anterior a la última para la recuperación, y una
  pasada sobre la última placa para la compactación.
- **Al terminar el primer intento:** ya se sabe cuántas consultas costó un
  intento real; los intentos restantes se prevén iguales, y la cantidad
  real de placas reemplaza a la estimada.
- **Al entrar en recuperación y en compactación:** se conocen las placas y
  sus piezas, así que la previsión de esas fases pasa a ser exacta como cota
  superior.

`consultas_previstas` nunca queda por debajo de `consultas_hechas`.

El formato es independiente de las fases: el motor nuevo (pares encastrados,
orientaciones diversas) suma sus propias consultas previstas y el estimador
no necesita saber qué fase es.

### 2.2 Las fases finales avisan

Hoy `_recuperar_de_la_ultima_placa` avisa por pieza, y `_compact_last_sheet`
no avisa. Las dos pasan a emitir `Avance` con las consultas, igual que la
pasada golosa. La compactación, además, pasa a ser cancelable.

## 3. Las dos cifras

### 3.1 Mientras corre

Lo calcula el servidor (`nesting_app.jobs`), que tiene el reloj:

    segundos_por_consulta = transcurrido / consultas_hechas
    restante = segundos_por_consulta × (consultas_previstas - consultas_hechas)

con un promedio móvil exponencial sobre `segundos_por_consulta`, para que una
consulta lenta aislada no mueva el número.

El estado del trabajo gana `restante_s: float | None`. Es `None` durante los
primeros 5 segundos o las primeras 20 consultas, lo que pase último: antes de
eso no hay datos.

La pantalla muestra:

- con `None`: "Calculando el tiempo…"
- si no: "Faltan aprox. 9 min · termina ~17:42"

Redondeo, para no fingir una precisión que no hay:

| restante | se muestra |
|---|---|
| más de 10 min | de a 5 min |
| de 2 a 10 min | de a 1 min |
| menos de 2 min | "menos de 2 min" |

Estabilidad: el número mostrado baja libremente, pero sólo sube si el valor
nuevo se sostiene por 5 segundos. Un número que salta de 8 a 12 y vuelve a 8
es peor que uno que se queda en 8.

La hora de finalización se calcula en la pantalla con el reloj local, a
partir del restante ya redondeado.

### 3.2 Antes de arrancar

Ruta nueva `POST /api/estimar`, con la fuente y los parámetros. Devuelve
`{"segundos": float}` o `{"segundos": null}` si no se puede estimar (el
archivo no se leyó, o los parámetros no validan).

    segundos = segundos_por_consulta_medido × consultas_previstas_al_arrancar × FACTOR_LLENO

- `segundos_por_consulta_medido` sale de una prueba real: una consulta con la
  pieza más grande del archivo, en su primera orientación, sobre una placa
  vacía del material elegido, a la resolución elegida. Incluye rasterizar
  esa máscara. Tarda menos de un segundo, y así el número vale en cualquier
  máquina.
- `consultas_previstas_al_arrancar` es la misma previsión de 2.1.
- `FACTOR_LLENO` corrige que una consulta sobre una placa con piezas cuesta
  más que sobre una vacía (la búsqueda exacta recorre más candidatos). Es
  una constante, calibrada con los archivos del bench y documentada con sus
  mediciones donde vive.

La pantalla muestra "Tarda aprox. 10 min" al lado de Acomodar, con el mismo
redondeo de 3.1, y la recalcula 400 ms después del último cambio en
Posiciones, Ángulos, espejo, Esfuerzo, Resolución, Material, Veta, Copias o
Recortes. Mientras calcula deja el valor anterior; si la ruta devuelve
`null`, no muestra nada.

## 4. Pruebas

- Motor: `consultas_hechas` es monótona y termina igual al número real de
  llamadas a `best_placement` (contadas con un oráculo espía);
  `consultas_previstas >= consultas_hechas` en todo aviso; la compactación
  avisa y se cancela.
- Previsión: después del primer intento, el error de la previsión contra el
  total real es menor al 25% sobre los archivos del bench.
- Estimador de `jobs`: `None` antes de 5 s / 20 consultas; la cuenta con
  consultas y reloj falsos; el promedio móvil.
- Redondeo y estabilidad: tabla de casos en JavaScript (los tests de
  `tests/app`).
- `/api/estimar`: devuelve un número para una fuente leída, `null` sin
  fuente o con parámetros inválidos.
- Calibración: `bench/calibrate.py` gana la medición de `FACTOR_LLENO`, y un
  test verifica que la estimación previa cae dentro de ×2 del tiempo real
  sobre un archivo chico.
