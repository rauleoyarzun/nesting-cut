# Un globo de ayuda por cada opción

*[English](2026-09-20-info-opciones-design.md)*

Fecha: 2026-09-20
Estado: aprobado

## 1. Qué se construye

Un ícono de información al lado de la etiqueta de cada opción del panel. Al
hacerle clic sale un globo con dos o tres oraciones que dicen qué es esa
opción y qué cambia si la movés.

El texto ya existe: está en la tabla de opciones del README. El problema es
dónde está. Nadie abre el README parado frente a la máquina, y las opciones
que más se malinterpretan -- Esfuerzo, Tolerancia de cierre, Resolución -- son
justamente las que no se explican por el nombre.

### Fuera de alcance, a propósito

- **La pantalla de Materiales.** Las dos opciones de Veta ya se explican solas
  con un `<small>` abajo de cada una. Agregarles un globo sería repetir.
- **Un tutorial, un tour o un "primeros pasos".** Esto se consulta cuando ya
  tenés la duda, no te la anticipa.
- **Traducir la interfaz.** La pantalla es en español; los globos también.

## 2. Las decisiones, y por qué

### 2.1 Un ícono por opción, no uno global

Un solo signo de pregunta arriba que abra la lista completa es más barato de
hacer y de mantener, pero obliga a entrar a una pantalla, buscar la opción
entre diez y volver. El ícono al lado de la etiqueta pone la explicación
donde está la duda, que es el mismo criterio con el que el botón del catálogo
se movió al campo Material.

### 2.2 Se abre con clic, no al pasar el mouse

Un globo que aparece solo al apoyar el puntero se escapa al moverlo, no
existe para el teclado y en un panel que scrollea queda cortado. Con clic el
globo se queda quieto mientras se lee, y el mismo botón sirve para Tab +
Enter.

Se cierra con otro clic en el ícono, con clic afuera, con Escape o si el
panel scrollea. Hay uno solo abierto a la vez.

### 2.3 El globo flota fijo, no va adentro del campo

`.panel-opciones` tiene `overflow-y: auto`. Un globo posicionado en absoluto
adentro de ese panel se recorta contra el borde justo cuando el campo está
cerca de abajo -- que es donde están las avanzadas, las que más falta hacen.
Se posiciona con `position: fixed` y coordenadas sacadas de
`getBoundingClientRect()` del ícono, y se cierra al scrollear para no quedar
flotando lejos de su campo.

La alternativa era desplegar el texto abajo del campo, empujando el resto.
Nada flota ni se recorta, pero el panel salta cada vez que se abre o se
cierra un globo y se pierde de vista lo que estabas mirando.

### 2.4 El texto vive en JavaScript, no en el HTML

Un `data-info-texto` por campo mete diez párrafos en el medio de la
estructura y hace ilegible el HTML. El mapa junto -- clave del campo a texto
-- se lee de un vistazo, se corrige de un vistazo, y permite el test que
verifica que no haya botones sin texto ni textos sin botón.

### 2.5 Archivo nuevo, no adentro de `app.js`

`app.js` tiene 724 líneas y lleva el cliente de la API, el sondeo del
trabajo, el zoom y el estado de la pantalla. Los globos no comparten nada con
eso: ni estado, ni red, ni el trabajo en curso. Van en `info.js`, al lado de
`materiales.js`, que ya sentó ese precedente.

## 3. Cómo se ve

En la misma línea de la etiqueta, a su derecha, un círculo de trazo con una
"i" adentro, gris como el texto secundario:

```
Separación  (i)
┌──────────────────────────┐
│ 5                     mm │
└──────────────────────────┘
```

Cuando el campo ya tiene una acción a la derecha, el ícono queda pegado a la
etiqueta y la acción sigue contra el margen:

```
Material  (i)          Agregar o editar
```

El ícono es un SVG de trazo, como todos los de la interfaz. No hay emoji: el
test `test_no_hay_emojis_en_la_interfaz` lo prohíbe, y en una herramienta de
taller un signo que se dibuja distinto en cada sistema queda fuera de lugar.

El globo es una caja blanca de ~280 px con el borde y la sombra que ya usan
los paneles, sin título: adentro va sólo el texto.

## 4. Qué opción lleva globo, y qué dice

| Opción | Texto |
|---|---|
| Archivo | El dibujo con los contornos de las piezas. Acepta `.dxf`, `.ai` (los de texto plano) y `.3dm` de Rhino; `.cdr` no, hay que exportarlo antes. |
| Material | La placa de la que vas a cortar: de acá salen el ancho, el alto y si hay que respetar la veta. Si te falta una medida, "Agregar o editar" abre el catálogo. |
| Separación | Los milímetros mínimos que quedan entre una pieza y la de al lado. Poné al menos el diámetro de la fresa, o el corte de una se come el borde de la otra. |
| Borde | El margen que se deja libre contra el filo de la placa. Sirve para las grampas y para que una placa astillada no arruine una pieza. |
| Copias | Cuántas veces se repite el contenido entero del archivo. Si el archivo trae 12 piezas y ponés 3, acomoda 36. |
| Esfuerzo | Cuántas veces intenta acomodar antes de quedarse con la mejor. Más esfuerzo nunca da un resultado peor, pero tarda más: Normal alcanza casi siempre. |
| Ángulos | Las rotaciones que puede probar en cada pieza, separadas por comas. Menos ángulos es más rápido; sumar 45 suele ganar lugar en piezas largas. Si el material respeta la veta, sólo se usan 0 y 180. |
| Tolerancia de cierre | Cuánto puede separarse la punta de un contorno de su principio y todavía contar como cerrado. Si te descarta piezas que a ojo están cerradas, subila. |
| Resolución | Cuántos milímetros mide cada píxel con el que el programa "ve" la placa. Más fino acomoda apenas mejor y tarda mucho más; 2 mm es buen punto. |
| Permitir espejadas | Deja dar vuelta la pieza como un guante, no sólo rotarla. Gana lugar, pero si el material tiene una cara buena o el dibujo es asimétrico, apagalo. |

## 5. Arquitectura

### 5.1 El HTML

Cada campo de la lista pasa a tener su etiqueta envuelta en un renglón:

```html
<div class="renglon-etiqueta">
  <span class="titulo-campo">
    <label class="etiqueta" for="sep">Separación</label>
    <button type="button" class="boton-info" data-info="sep"
            aria-label="Qué es Separación" aria-expanded="false">
      <svg viewBox="0 0 16 16" class="icono" aria-hidden="true">...</svg>
    </button>
  </span>
</div>
```

`.renglon-etiqueta` ya existe y reparte con `space-between`. Con un solo hijo
-- el `.titulo-campo` -- eso no hace nada, y en Material el segundo hijo sigue
siendo el botón del catálogo, que queda contra el margen como está hoy.

El globo es un solo nodo al final del `<body>`:

```html
<div id="globo-info" class="globo-info oculto" role="tooltip"></div>
```

Uno solo y no diez: el texto lo pone `info.js` al abrirlo, y así no hay diez
nodos escondidos que mantener sincronizados con el mapa.

`Permitir piezas espejadas` es una casilla sin `.etiqueta`: el botón va
después del texto de la casilla, fuera del `<label>` para que el clic en el
ícono no active la casilla.

### 5.2 `info.js`

Un archivo nuevo, del orden de cuarenta líneas, con tres partes:

1. `TEXTOS`: el mapa de clave de campo a texto de la tabla de arriba.
2. `abrir(boton)`: llena el globo, lo muestra, lo ubica con el rect del botón
   y pone `aria-expanded="true"` y `aria-describedby` en el botón.
3. `cerrar()`: lo esconde, deshace los dos atributos y, si el foco estaba
   adentro del globo, lo devuelve al botón.

Los escuchas se enganchan una sola vez en `document`: `click` (el botón
abre o cierra; cualquier otro lado cierra), `keydown` para Escape, y `scroll`
en captura más `resize` en la ventana para cerrar.

Se ubica a la derecha del ícono si entra en la ventana, y si no a la
izquierda; verticalmente alineado al ícono y corrido hacia arriba si se pasa
del borde de abajo.

### 5.3 El CSS

Tres reglas nuevas en `app.css`, con los tokens que ya están:

- `.titulo-campo`: flex, `align-items: baseline`, `gap: 6px`.
- `.boton-info`: botón sin fondo ni marco, 20 px, color `--texto-2`, que pasa
  a `--texto` al enfocarlo o apoyar el mouse.
- `.globo-info`: `position: fixed`, ancho máximo 280 px, fondo `--panel`,
  borde `--borde`, radio `--radio`, sombra `--sombra`, `z-index` por encima
  del panel y por debajo de los carteles.

No se agrega ningún token de color.

## 6. Accesibilidad

- El disparador es un `<button>` de verdad: llega con Tab y se activa con
  Enter o Espacio.
- Tiene `aria-label` con el nombre de la opción, porque adentro sólo hay un
  SVG con `aria-hidden`.
- Con el globo abierto, el botón lleva `aria-expanded="true"` y
  `aria-describedby="globo-info"`, así el lector de pantalla lee el texto
  como descripción del botón.
- Escape cierra y el foco vuelve al botón.
- El globo es `role="tooltip"`: no atrapa el foco ni se comporta como
  diálogo, que es lo que corresponde a un texto de ayuda.

## 7. Tests

En `tests/app/test_web_estatico.py`:

- `globo-info` entra a `IDS_OBLIGATORIOS`.
- Parametrizado por cada una de las diez claves: existe un
  `data-info="<clave>"` en el HTML.
- Cada `data-info` del HTML es un `<button>` y tiene `aria-label`.
- El botón de la casilla de espejadas está fuera del `<label>`, para que el
  clic no dé vuelta la casilla.

En `tests/app/test_web_javascript.py` (o un `test_web_info.py` al lado):

- Toda clave con texto en `info.js` tiene su botón en el HTML, y todo botón
  del HTML tiene texto: los dos conjuntos son iguales. Es el test que importa
  -- un botón huérfano abre un globo vacío y no falla en ningún otro lado.
- Ningún texto pasa de 300 caracteres. Son globos, no párrafos.
- Ningún texto está vacío ni es sólo espacios.
- `info.js` contempla `Escape`, el clic afuera y el `scroll`.
- `index.html` carga `info.js`.

El test que ya existe de emojis cubre que el ícono sea SVG y no un símbolo.

## 8. Cambios al código que ya está

| Archivo | Qué le pasa |
|---|---|
| `src/nesting_app/web/index.html` | Diez etiquetas se envuelven en `.titulo-campo` con su botón; se agrega el nodo del globo y el `<script>` de `info.js`. |
| `src/nesting_app/web/info.js` | Nuevo. |
| `src/nesting_app/web/app.css` | Tres reglas nuevas al final de la sección de campos. |
| `src/nesting_app/web/app.js` | No se toca. |
| `packaging/` | Nada: el `.spec` declara la carpeta `web` entera. |

El README no cambia: la tabla de opciones sigue siendo la referencia larga, y
los globos son la versión corta de lo mismo.
