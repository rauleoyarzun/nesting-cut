# Sistema de nesting para optimización de cortes en placas

**Fecha:** 2026-09-17
**Estado:** Diseño aprobado, pendiente de plan de implementación

---

## 1. Problema

Acomodar manualmente (en CorelDRAW) las piezas de un mueble sobre placas de madera es lento y
deja material sin aprovechar. Existen herramientas que lo resuelven (eCut, SigmaNest, el nesting
de AutoCAD), pero son cerradas y/o pagas.

**Objetivo:** dado un archivo vectorial con las figuras a cortar, producir un archivo de salida
con esas figuras acomodadas dentro de una o más placas, usando la menor cantidad de placa posible,
respetando una separación mínima configurable entre figuras y contra el borde de la placa.

### Escala de referencia

Archivos reales del proyecto (una banqueta): 40-80 contornos por archivo, placa estándar
1830 × 2600 mm, piezas orgánicas con curvas que se entrelazan.

---

## 2. Alcance

### Dentro del alcance

- Lectura de `.dxf` (canónico), `.ai` y `.3dm`
- Escritura de `.dxf` con las piezas acomodadas + preview `.png`
- Nesting de formas irregulares con rotación y espejado
- Aprovechamiento de agujeros pasantes como área libre
- Separación configurable entre piezas y contra el borde de placa
- Múltiples placas con desborde automático
- Catálogo de materiales (tamaño de placa + restricción de veta)
- Interfaz de línea de comandos
- Verificación geométrica exacta del resultado

### Fuera del alcance (v1)

| Tema | Motivo |
|---|---|
| Lectura directa de `.cdr` | Formato binario propietario cerrado. Se resuelve exportando a DXF desde Corel |
| Mapeo color → operación de máquina | Todos los cortes se tratan igual. El color se transporta como atributo pasivo |
| Puentes / lengüetas (tabs) | Las piezas quedan sueltas al cortarse. Limitación conocida |
| Optimización del recorrido de corte | Es trabajo del CAM, no del nesting |
| Placas no estándar / retazos | Extensión natural posterior. No v1 |
| Partir piezas más grandes que la placa | Se reporta como error |
| Interfaz gráfica | Se puede montar después sobre el mismo motor |

---

## 3. Decisiones de diseño

### 3.1 DXF como formato canónico

**Decisión:** el motor trabaja sobre DXF. Los demás formatos entran por importadores que
normalizan al mismo modelo interno.

**Motivo:** el `.cdr` es RIFF binario propietario sin parser libre confiable; implementarlo sería
la mayor parte del esfuerzo total del proyecto sin aportar nada al núcleo. Corel y Rhino exportan
DXF, que además es el estándar de facto de CNC y sobrevive con capas y colores intactos.

`.ai` y `.3dm` se leen igual porque son baratos: el `.ai` exportado de Corel es AI3/PostScript en
texto plano, y `rhino3dm` es la librería oficial de McNeel.

### 3.2 Nesting por raster, con la interfaz preparada para NFP

**Decisión:** el oráculo de colisión se implementa con máscaras de bits (raster). La interfaz se
diseña para que una implementación por No-Fit Polygon (NFP) pueda reemplazarlo sin tocar el resto.

**Motivos a favor del raster:**

1. La separación entre piezas se reduce a una dilatación morfológica de la máscara, en vez de un
   offset de polígono (frágil numéricamente).
2. El aprovechamiento de agujeros sale sin código dedicado (ver §5.2).
3. Maneja concavidad y entrelazado sin geometría computacional frágil.
4. La precisión del raster no contamina la salida: solo decide *posiciones*; el archivo final
   lleva las curvas exactas.

**Para que la puerta a NFP quede realmente abierta, tres restricciones obligatorias:**

1. **El polígono exacto es siempre la fuente de verdad.** La máscara raster es un caché derivado.
   Está prohibido re-vectorizar el resultado de operaciones morfológicas.
2. **El offset de separación es responsabilidad del oráculo**, no un preproceso compartido.
   El raster dilata máscaras; el NFP haría offset de polígonos.
3. **El banco de pruebas existe desde el principio**, para que la comparación entre motores sea
   con números medidos (% de aprovechamiento y segundos).

Aproximadamente el 85% del código es agnóstico al motor: I/O, extracción de piezas, aplanado,
estrategia de búsqueda, reporte y verificación.

### 3.3 Modelo de pieza

- Un **contorno exterior cerrado** = el perímetro de corte de una pieza.
- Todo lo contenido dentro viaja **rígidamente** con ella (misma traslación, rotación y espejado).
- Dos contornos exteriores separados **no** viajan juntos: son piezas independientes.
- **Regla de contención par/impar por profundidad:**
  - nivel 0 → contorno exterior de una pieza
  - nivel 1 → agujero (libera material)
  - nivel ≥ 2 → **pieza independiente**, se reubica en otro lado (no queda anidada donde estaba
    dibujada)

  Esta regla describe cómo se **interpreta el dibujo de entrada**. No limita la **colocación**:
  el motor sí puede terminar poniendo una pieza dentro del agujero de otra (§5.2), simplemente no
  asume que la anidación dibujada por el usuario deba conservarse.

### 3.4 El color es un atributo pasivo

Todos los contornos son corte pasante a los efectos geométricos. El motor **nunca** interpreta el
color ni la capa.

Sin embargo, el archivo de salida **debe preservar los colores y capas originales** de cada
entidad. Esto se obtiene gratis por la decisión de §3.5.

### 3.5 Aplanar para decidir, transformar los originales para escribir

**Este es el principio rector de la arquitectura.**

El motor aplana curvas a polilíneas y rasteriza para calcular *dónde* va cada pieza. El resultado
de todo ese proceso es una tupla por pieza: `(placa, x, y, ángulo, espejada)`. Esa transformación
rígida se aplica al final sobre las **entidades originales** — splines, arcos, colores, capas.

Consecuencias:
- No hay pérdida de fidelidad geométrica en la salida.
- La preservación de color y capa no requiere código dedicado.
- El aplanado puede ser tan grueso como convenga sin degradar el resultado.

### 3.6 Rotación gobernada por el material

Un solo parámetro unifica los casos: **`tolerancia_veta`** (en grados). Los ángulos permitidos son
los que caen dentro de ±`tolerancia_veta` respecto de 0° o 180°.

| Valor | Efecto | Caso de uso |
|---|---|---|
| `180` | Rotación libre | MDF (la veta es irrelevante) |
| `5` | Solo 0° / 180°, corte cruzado bloqueado | Multilaminado, fenólico |

Vive en el catálogo de materiales junto al tamaño de placa.

**Espejado:** habilitado por defecto. Como todo es corte pasante y el material es homogéneo, una
pieza espejada dada vuelta es la pieza original. Es densidad extra sin costo. Flag `--sin-espejo`
para apagarlo.

El espejado es **siempre compatible con la restricción de veta**: reflejar una pieza no cambia la
dirección de su eje de veta, solo el sentido. Por lo tanto `--sin-espejo` y `tolerancia_veta` son
independientes entre sí.

### 3.7 Contrato de entrada: una figura = una pieza

El archivo de entrada **es** la lista de materiales: cada contorno exterior es una pieza a cortar.
No hay tabla de cantidades ni necesidad de nombrar piezas.

Un multiplicador global `--copias N` nestea N veces todo el contenido del archivo. Así se dibuja
una banqueta y se piden cinco.

### 3.8 Criterio de optimización multi-placa

1. **Minimizar la cantidad de placas.**
2. Alcanzado ese mínimo, **compactar la última placa** todo lo posible, para que el sobrante quede
   en una pieza grande y aprovechable en vez de recortes dispersos.

---

## 4. Arquitectura

### 4.1 Flujo de datos

```
archivo (.dxf/.ai/.3dm)
  │
  ├─ lectura ──────────►  entidades crudas  (geometría + color + capa)
  │                              │
  │                    aplanado (Bézier/arco/spline → polilínea)
  │                              │
  │                    encadenado (unir tramos sueltos en contornos cerrados)
  │                              │
  │                    árbol de contención (¿qué es pieza, qué es agujero?)
  │                              ▼
  │                           Piezas  ──── × copias
  │                              │
  │                    ┌─────────▼─────────┐
  │                    │      PACKER       │ ◄── material + configuración
  │                    │   (multi-placa)   │
  │                    └─────────┬─────────┘
  │                              ▼
  │                         Colocaciones
  │                    (placa, x, y, ángulo, espejo)
  │                              │
  │                    verificación geométrica exacta
  │                              │
  └──── entidades originales ────┤
                                 ▼
                    ┌────────────┴────────────┐
                    ▼                         ▼
              resultado.dxf             preview.png
```

### 4.2 Módulos

```
io/          dxf_reader · ai_reader · rhino_reader · dxf_writer · preview
geometry/    flatten · chaining · nesting_tree · transform · verify
model/       Part · Sheet · Placement · Material
engine/      oracle (INTERFAZ) · raster_oracle · strategy · packer
config/      materials.yaml
cli.py
bench/       banco de pruebas sobre archivos reales
```

### 4.3 Fronteras principales

**`engine/oracle.py` — la costura del motor.** Dos operaciones:

```
posiciones_factibles(pieza, ángulo, estado_placa) → candidatos
marcar(pieza, ángulo, posición)                   → estado_placa'
```

`raster_oracle` la implementa con bitmaps y devuelve candidatos como bitmap. Un futuro
`nfp_oracle` la implementaría con polígonos y devolvería regiones poligonales. Misma firma,
distinta representación interna. El offset de separación vive adentro del oráculo.

**`io/` ↔ el resto.** Todos los lectores devuelven la misma estructura. Agregar un formato es un
archivo nuevo, sin cambios en el motor.

### 4.4 Modelo de entidad intermedio

Todos los lectores normalizan a las mismas primitivas, con forma de DXF para que el escritor sea
trivial:

`Línea` · `Arco` · `Círculo` · `Elipse` · `Bézier cúbica` · `Polilínea`

Cada una con su **color y capa de origen**.

### 4.5 Dos módulos de `geometry/` que parecen detalle y no lo son

- **`chaining`** — los DXF exportados desde Corel traen los contornos partidos en decenas de
  `LINE`/`ARC`/`SPLINE` sueltos, no como polilíneas cerradas. Hay que reconstruir los ciclos
  uniendo extremos por tolerancia. **Es el caso normal, no el excepcional.**
- **`nesting_tree`** — análisis de contención con la regla par/impar de §3.3.

Son el código más aburrido del proyecto y donde se esconden los bugs que después parecen
"el nesting anda mal".

---

## 5. El motor de nesting

### 5.1 Dos máscaras por pieza, por ángulo

| Máscara | Definición | Uso |
|---|---|---|
| `ocupada` | Material real: contorno exterior **menos** agujeros | Se estampa en la placa al colocar |
| `holgura` | `ocupada` dilatada por la separación `sep` | Se usa para testear colisión |

**Regla de colisión:**

```
placa_ocupada  =  unión de las `ocupada` de las piezas ya colocadas   (SIN dilatar)

pieza entra  ⟺  pieza.holgura  ∩  placa_ocupada  =  ∅
```

Dilatar **solo la pieza que se mueve** y testear contra material **sin dilatar** hace que la
separación se cuente exactamente una vez. Dilatar ambas daría `2 × sep` de separación real y
desperdicio invisible: es el bug clásico de este enfoque.

**Borde de placa:** parámetro independiente. `pieza.ocupada` debe caber dentro del rectángulo de
placa **erosionado** por `borde`.

**Rotación:** las máscaras se re-rasterizan desde el polígono exacto en cada ángulo. **No** se
rota el bitmap (introduce artefactos acumulativos).

### 5.2 Los agujeros salen sin código dedicado

Las tres propiedades deseadas se derivan de la definición de §5.1:

1. **El agujero es área libre** → su región nunca entra en `placa_ocupada`.
2. **Se respeta la separación contra la pared del agujero** → el material del borde del agujero sí
   está en `placa_ocupada`, así que la `holgura` de la pieza chica choca contra él.
3. **Anidamiento recursivo** → una pieza dentro del agujero de una pieza que está dentro de otro
   agujero funciona sin caso especial.

Esta propiedad es la razón principal por la que el raster le gana al NFP en este proyecto: con NFP
haría falta implementar *inner-fit polygons* por cada agujero.

### 5.3 Búsqueda de posición

Evaluar posición por posición es inviable (millones de candidatos por pieza). Se evalúan **todas
las posiciones a la vez** mediante correlación por FFT:

```
correlación( placa_ocupada , pieza.holgura )  →  solapamiento en CADA posición
```

Las posiciones con solapamiento `0` son exactamente las factibles.

**Resolución:** 1 mm/px por defecto, configurable con `--resolucion`. Sobre una placa de
1830 × 2600 son ~4,8 M de puntos. El error de discretización queda absorbido por el margen de
separación y **siempre hacia el lado conservador**.

**Optimización:** se correlaciona solo sobre la **región activa** de la placa (área usada +
tamaño de la pieza), no sobre la placa entera. Con la placa mayormente vacía, las correlaciones
son pequeñas.

### 5.4 Puntaje de posición

Que la pieza entre no alcanza; hay que elegir bien entre las posiciones factibles:

```
puntaje  =  w₁ · (abajo-izquierda)  +  w₂ · (contacto)
```

- **abajo-izquierda** — empuja todo hacia una esquina; concentra el sobrante en un bloque grande.
- **contacto** — mide cuánto perímetro de la pieza queda apoyado contra material ya colocado. Se
  obtiene con una segunda correlación usando la `holgura` ensanchada una banda extra: donde esa
  banda solapa mucho, la pieza está encajada.

**El término de contacto es el que produce el entrelazado** entre piezas curvas. Sin él, el
bottom-left apila y deja huecos.

### 5.5 Orden, ángulos y multi-placa

- **Orden de inserción:** área descendente. Las piezas grandes definen la estructura; las chicas
  rellenan intersticios y agujeros.
- **Ángulos:** para cada pieza se prueban todos los ángulos permitidos por el material, y las
  versiones espejadas si corresponde. Se elige el mejor `(ángulo, posición)`.
- **Multi-placa:** se llena la placa 1 hasta que no entre nada más, se abre la 2, etc. Luego se
  aplica el criterio de §3.8.

### 5.6 Niveles de esfuerzo

Lo que compra el tiempo extra son reintentos con distinto orden de inserción, quedándose con el
mejor resultado.

| `--esfuerzo` | Comportamiento |
|---|---|
| `rapido` | 1 pasada golosa, determinística |
| `normal` *(default)* | ~10 reintentos con órdenes perturbados, se queda con el mejor |
| `lento` | Búsqueda dirigida (recocido simulado) sobre orden + ángulos |

**Los tiempos concretos de cada nivel se calibran con mediciones del banco de pruebas (§7.3), no
se fijan por estimación.** La estimación inicial de referencia es ~15-30 s por pasada, pero
depende fuertemente de la cantidad y tamaño de las piezas.

### 5.7 Verificación geométrica exacta

Después de empacar, y **antes de escribir el archivo**, se verifica sobre los polígonos exactos
(no sobre bitmaps):

- Ningún par de piezas colocadas se solapa.
- Ninguna distancia entre piezas es menor que `sep`.
- Ninguna pieza excede el área útil de su placa.

Si alguna verificación falla, el programa **reporta el problema y falla**, en vez de escribir un
DXF silenciosamente incorrecto.

Esta verificación cumple tres funciones: red de seguridad en producción, oráculo de los tests
(§7), y árbitro de la comparación entre motores el día que exista una implementación NFP.

### 5.8 Gestión de memoria

Las máscaras se cachean por `(pieza, ángulo, espejado)`. Con muchos ángulos permitidos el caché
crece linealmente; se almacenan bit-empaquetadas y se descartan por LRU si hace falta.

---

## 6. Entrada, salida y errores

### 6.1 Lectores

| Formato | Librería | Notas |
|---|---|---|
| **DXF** | `ezdxf` | Explota bloques (`INSERT`). Lee unidades de `$INSUNITS` |
| **AI** | propia (~200 líneas) | AI3/PostScript: operadores `m` `L` `C` `v` `y` `s` `f`. Color desde `K`/`G`. Unidades en puntos → mm (× 25,4/72) |
| **3DM** | `rhino3dm` | Curvas Nurbs/Arc/Polyline. Color desde la capa. Proyecta a XY y valida planaridad |

**Unidades: todo se normaliza a milímetros al leer.** Si un DXF no declara unidades, el programa
**no adivina**: exige `--unidades mm|cm|in`. Una unidad mal inferida arruina una placa entera.

### 6.2 Salida

**DXF:** un solo archivo, placas en fila horizontal separadas por un margen, cada una con su
rectángulo de contorno en una capa `_PLACA`. Sobre cada placa, las entidades originales con la
transformación rígida aplicada, con color y capa intactos.

**Preview PNG:** las placas renderizadas con su porcentaje de aprovechamiento.

**Resumen por consola:**

```
Placa 1/3   aprovechamiento 87,4%
Placa 2/3   aprovechamiento 85,1%
Placa 3/3   aprovechamiento 41,9%   ← sobrante útil ~1830×1080
─────────────────────────────────
60 piezas · 3 placas · 71,5% total · 4m 12s
```

### 6.3 Manejo de errores

Regla general: **avisar y seguir** cuando el problema es cosmético; **fallar fuerte** cuando puede
arruinar material.

| Situación | Respuesta |
|---|---|
| Contornos partidos en tramos sueltos | Se encadenan por tolerancia. Caso normal |
| Contorno que no cierra | **Error** con coordenadas del hueco y distancia faltante. Flag `--tol-cierre` |
| Líneas duplicadas superpuestas | Se deduplican, con aviso y conteo |
| `TEXT`, `DIMENSION`, `HATCH` | Se ignoran, con aviso y conteo |
| Contorno auto-intersectado | **Error** con la ubicación |
| Pieza más grande que el área útil | **Error** con identificación y medidas |
| Contorno de área cero o degenerado | Se saltea, con aviso |
| DXF sin unidades declaradas | **Error**: exige `--unidades` |

### 6.4 Configuración

```yaml
# materials.yaml
mdf18:
  placa: [1830, 2600]
  tolerancia_veta: 180      # rotación libre
multilam18:
  placa: [1220, 2440]
  tolerancia_veta: 5        # sin corte cruzado
```

### 6.5 Interfaz de línea de comandos

```bash
nest banqueta.dxf --material mdf18 --copias 5 \
     --sep 6 --borde 10 --angulos 0,90,180,270 \
     --esfuerzo normal -o resultado.dxf
```

| Flag | Default | Descripción |
|---|---|---|
| `--material` | *(requerido)* | Clave del catálogo de materiales |
| `--copias` | `1` | Multiplicador global del contenido del archivo |
| `--sep` | `5` | Separación mínima entre piezas, en mm |
| `--borde` | `10` | Margen contra el borde de la placa, en mm |
| `--angulos` | `0,90,180,270` | Ángulos candidatos, filtrados por `tolerancia_veta` |
| `--esfuerzo` | `normal` | `rapido` \| `normal` \| `lento` |
| `--sin-espejo` | *(off)* | Deshabilita el espejado de piezas |
| `--resolucion` | `1` | Resolución del raster, en mm/px |
| `--unidades` | *(auto)* | `mm` \| `cm` \| `in`. Requerido si el archivo no las declara |
| `--tol-cierre` | `0.1` | Tolerancia de encadenado de contornos, en mm |
| `-o` | *(requerido)* | Archivo DXF de salida |

---

## 7. Testing

**El verificador geométrico exacto de §5.7 es el oráculo de toda la estrategia de tests.**
Cualquier salida, de cualquier motor, con cualquier configuración, debe pasarlo.

### 7.1 Tests unitarios

Cobertura de `geometry/`: `flatten` (error de cuerda acotado), `chaining`, `nesting_tree`
(contención par/impar), `transform`.

Con tests basados en propiedades:
- El área de un polígono es invariante ante rotación y traslación.
- Espejar dos veces es la identidad.
- Encadenar un contorno ya cerrado no lo modifica.
- Rotar una pieza `tolerancia_veta = 180` por cualquier ángulo permitido conserva su área ocupada.

### 7.2 Tests de integración

Pipeline completo sobre casos sintéticos con respuesta conocida. Ejemplo: cuatro cuadrados de
100 mm en una placa de 220 mm con `sep = 10` y `borde = 0` → entran exactamente 4.

### 7.3 Banco de pruebas

Corre sobre los archivos reales del proyecto (`.ai`, DXF exportado del `.cdr`, `.3dm`) y mide
**% de aprovechamiento, cantidad de placas y segundos**.

Cumple tres funciones:
- Calibrar los niveles de esfuerzo de §5.6 con datos medidos.
- Detectar regresiones de calidad.
- Arbitrar la comparación raster vs NFP si se implementa el segundo motor.

### 7.4 Regresión

Con semilla fija, `--esfuerzo rapido` es determinístico. Cualquier cambio que mueva el
aprovechamiento se hace visible.

### 7.5 Foco de TDD

`chaining` y `nesting_tree`. Es el código con más casos borde y el que produce los fallos que
después se malinterpretan como "el nesting anda mal".

---

## 8. Orden de construcción

| # | Hito | Justificación |
|---|---|---|
| **1** | Modelo + `geometry/` + **verificador exacto** | Nada es confiable hasta que exista el árbitro |
| **2** | DXF lectura/escritura + empaquetado trivial (bounding box) + **banco de pruebas** | Pipeline completo end-to-end lo antes posible: ya hay DXF de salida con archivos reales, aunque nestee mal. Y ya se mide |
| **3** | `raster_oracle`: máscaras, FFT, puntaje de contacto | El motor real. Entra detrás de la interfaz; el banco cuantifica la mejora contra el hito 2 |
| **4** | Multi-placa, niveles de esfuerzo, CLI, preview | El producto |
| **5** | Lectores `.ai` y `.3dm` | Independientes del motor; se pueden hacer en paralelo |
| **6** | Calibración de esfuerzos con mediciones | Cierre con números |

**El hito 2 va antes que el 3 deliberadamente:** tener el circuito completo funcionando con un
nesting malo vale más que tener un nesting excelente sin poder abrir el archivo.

---

## 9. Dependencias

| Librería | Uso | Hito |
|---|---|---|
| `numpy` | Máscaras raster, álgebra | 1 |
| `scipy` | FFT (`fftconvolve`), morfología (`binary_dilation`) | 3 |
| `ezdxf` | Lectura y escritura DXF | 2 |
| `shapely` | Verificación geométrica exacta, análisis de contención | 1 |
| `Pillow` | Rasterizado de polígonos, preview PNG | 1 |
| `rhino3dm` | Lectura `.3dm` | 5 |
| `PyYAML` | Catálogo de materiales | 4 |

El lector `.ai` no requiere dependencias: es un parser propio de AI3/PostScript.

**Nota:** se usa `shapely` y no `pyclipper` para la verificación. `shapely` expone directamente las
consultas que hacen falta (`intersects`, `distance`, `contains`), mientras que `pyclipper` es de
nivel más bajo. `pyclipper` solo entraría si se implementa un motor NFP, por su operación
`MinkowskiDiff`.

---

## 10. Riesgos conocidos

| Riesgo | Mitigación |
|---|---|
| Los DXF de Corel vienen sucios (contornos partidos, duplicados, entidades espurias) | `chaining` robusto con tolerancia + deduplicación + filtrado explícito con aviso. Es el foco de TDD |
| El rendimiento de la búsqueda FFT no alcanza los tiempos objetivo | Correlación restringida a la región activa; resolución configurable; los niveles de esfuerzo se calibran con mediciones en vez de prometerse por anticipado |
| El puntaje de contacto necesita ajuste de pesos | El banco de pruebas mide el impacto de cada combinación de pesos sobre archivos reales |
| Las piezas anidadas dentro de agujeros se mueven al cortarse | Limitación declarada. La generación de puentes queda fuera del alcance de v1 |
