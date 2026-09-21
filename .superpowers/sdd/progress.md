# Progreso — Sistema de nesting para placas

Plan: docs/superpowers/plans/2026-09-17-nesting-placas.md
Modo: subagent-driven-development, **sin git** (decisión del usuario, 2026-09-17)

Sin repo: las revisiones leen los archivos directamente en vez de un diff,
y no hay commits. Este archivo es el único registro durable de avance.

## Tareas

Task 1: completa — andamiaje, venv + pytest (2 passed). Spec ✅, calidad aprobada. Sin git (por decisión).
Task 2: completa — primitivas geometricas (Style/Line/Arc/Circle/Bezier/Polyline/Transform). 6 tests, spec OK, calidad aprobada.
  Menores pendientes p/revision final: (a) test_style_is_frozen_and_hashable usa `hash(x) is not None`, asercion debil;
  (b) no hay test de hash sobre Line/Arc/Circle/Bezier/Polyline/Transform (verificado a mano por el revisor, pero sin cubrir).
Task 3: completa — transformacion rigida unica (apply_point/apply_points/apply_entity). 15 tests, spec OK.
  Revisor verifico numericamente la matematica del arco bajo espejado, incluyendo puntos INTERMEDIOS del barrido
  y arcos que cruzan 0 grados: correcta (error ~1e-15).
  >>> ACCION PARA LA TASK 8 (lector DXF): un ARC de DXF con start=0/end=360 (circulo completo) queda colapsado
      a start=end=0 por _normalize_degrees, y se escribiria degenerado en la salida. Arreglarlo en el ORIGEN:
      el lector debe convertir un ARC de barrido 360 en un Circle. No tocar transform.py.
  Menores pendientes p/revision final: (a) mensaje de TypeError en ingles (error interno, no de usuario);
  (b) sin test de la rama de entidad no soportada.
Task 4: completa — aplanado de curvas. 23 tests (14 del brief + 9 agregados). Spec OK tras arreglos.
  CRITICO ENCONTRADO Y ARREGLADO (era un defecto del plan, no del implementador): _is_flat media distancia a la
  RECTA INFINITA p0-p3 en vez de al SEGMENTO. En una cuspide un control queda colineal pero mas alla de p3,
  el test lo daba por plano y cortaba la recursion. Medido: 0.2228 mm de desviacion real con tolerancia 0.001
  (223x). Arreglado con distancia al segmento (t recortado a [0,1]); ahora da 2.25e-05 mm. El plan en
  docs/superpowers/plans/ tambien quedo corregido para que no se reintroduzca.
  IMPORTANTE ARREGLADO: MIN_CIRCLE_SEGMENTS no se aplicaba a un Arc de barrido 360 -> colapsaba a 2 puntos.
  Ahora hay piso escalado al barrido: 360 grados da >=8, 2 grados sigue dando 1.
  Verificacion del revisor: 900 casos hostiles (cuspides rotadas, escalas 1e-3 a 1e3, tolerancias 1e-6 a 50)
  sin violaciones; y mutation testing confirmando que los tests nuevos detectan ambas regresiones.
  Menor pendiente p/revision final: al endurecer _is_flat, una curva degenerada con offsets de control >=1e8 mm
  y tolerancia <=1e-9 mm choca contra MAX_BEZIER_DEPTH=24 y viola la garantia en silencio (~30x). Fuera del
  dominio realista por 6 ordenes de magnitud (acá la tolerancia de aplanado por defecto es 0.2 mm).
Task 5: completa — encadenado de contornos. 26 tests (12 del brief + 14 agregados). Suite: 72 passed.
  El modulo que el plan habia marcado como el mas riesgoso, y lo fue: 3 rondas de arreglos, todos hallazgos reales.
  1) Bug del plan: _drop_duplicates tomaba points[len//2] como "medio", que en un tramo de 2 puntos es la cola
     -> un duplicado invertido no colisionaba. Arreglado canonicalizando la direccion antes de tomar el medio.
  2) CRITICO: _find_unused_neighbour tomaba el primer candidato del KD-tree sin desempate -> dos contornos que
     comparten un vertice (agujero tangente al borde, dos piezas que se tocan en una esquina) se fusionaban en
     un mono. Medido: 320/720 permutaciones incorrectas. Ahora 720/720.
  3) IMPORTANTE: la clave de dedup de anillos cerrados fallaba con cantidad PAR de puntos (head==tail no
     desempata direccion, y el indice medio no es punto fijo de la reversion si la longitud es par).
     Primer arreglo uso sorted(puntos), demasiado permisivo (cuadrado y mono con los mismos 4 puntos colisionaban).
     Final: forma canonica bajo el grupo DIEDRAL (min lexicografico entre rotaciones de la secuencia y de su inversa).
  4) CRITICO introducido por el arreglo 2: "preferir cerrar" ganaba a ciegas -> tramos DESAPARECIAN en silencio
     (ni contorno, ni cadena abierta, ni duplicado). Arreglado en dos partes: (a) el cierre ahora COMPITE por
     angulo como cualquier candidato, con guarda de degeneracion; (b) se agrego un INVARIANTE DE CONTABILIDAD
     que verifica que cada id de entrada quede contabilizado exactamente una vez, y lanza ChainingInvariantError
     nombrando los perdidos. Fuzz de 6000 casos: 0 violaciones, 0 falsos positivos.
  5) IMPORTANTE: la guarda de (4a) descalificaba el candidato POR COMPLETO en vez de solo como cierre -> dos
     tramos conectados quedaban en dos OpenChain inconexos con gap engañoso. Arreglado separando "puede cerrar"
     de "puede continuar".
  >>> SIMBOLO PUBLICO NUEVO: ChainingInvariantError (RuntimeError). Es un error de programacion del modulo,
      no de la entrada del usuario. ACCION PARA LA TASK 13 (CLI): decidir explicitamente que NO se atrapa,
      para que explote ruidosamente en vez de escribir geometria incompleta.
  Limitaciones documentadas (inherentes, no defectos): el orden de seleccion de semilla puede absorber una pieza
  real en una cadena abierta si un tramo espurio se elige primero; y el desempate angular es un heuristico local,
  asi que una pieza de muy pocos vertices tangente a dos piezas distintas puede ser ambigua.
Task 6: completa — arbol de contencion (Part, Placement, build_parts). 16 tests. Suite: 88 passed.
  Bug del plan arreglado: el representative_point() de un contorno EXTERIOR cae tambien dentro de todos los
  anillos anidados en el, asi que _find_parents podia elegir como padre a un hijo y _depth_of entraba en ciclo
  infinito. Arreglado con guarda de area ESTRICTAMENTE mayor, que ademas garantiza aciclicidad por construccion
  (cada salto en la cadena de padres aumenta el area). Plan corregido.
  IMPORTANTE arreglado: un contorno que se superpone PARCIALMENTE se aceptaba como agujero pleno (su punto sonda
  caia adentro) y daba un area neta sin sentido, en silencio. Medido: exterior 900 mm2 + "agujero" 375 mm2 que
  sale por un lado -> area 525, que no corresponde a ninguna resta real. Ahora se verifica contencion real con
  shapely y se lanza OverlappingContourError. Los casos legitimos siguen andando: agujero tangente que comparte
  un tramo de borde, agujero que toca en un punto, y 6 anillos concentricos.
  >>> SIMBOLO PUBLICO NUEVO: OverlappingContourError. ACCION PARA LA TASK 12/13: el pipeline debe atraparla y
      la CLI reportarla con codigo de salida 1 (es un problema del dibujo del usuario, no un bug del modulo).
  Menor pendiente p/revision final: dos contornos identicos duplicados que lleguen a build_parts quedan como dos
  piezas y el area se cuenta doble. Deberia atraparlos la deduplicacion del encadenado; no hay validacion aca.
Task 7: completa — verificador exacto (el arbitro). 18 tests. Suite: 106 passed.
  CRITICO arreglado (falso negativo en el arbitro, lo peor posible): box(margin,margin,w-margin,h-margin) con
  margin > mitad de una dimension deja los extremos invertidos, y shapely.box() los NORMALIZA EN SILENCIO ->
  franja fantasma en el centro de la placa donde cualquier pieza pasaba la verificacion. Medido: placa 200x200
  con margin=110 devolvia [] en vez de out_of_bounds. Aparece con un retazo chico o un bug de unidades aguas
  arriba. Ahora: si el area util es no positiva en cualquier eje, toda pieza es out_of_bounds, y el detail
  explica la causa real (el margen no deja area util) en vez de culpar a la pieza.
  MENOR arreglado: placed_polygon no chequeaba is_valid. Un contorno autointersectado daba geometria invalida
  y los predicados de GEOS quedaban en comportamiento no garantizado. Ahora se reporta kind="invalid_geometry".
  Verificado por el revisor: el filtro por STRtree con poligonos dilatados no descarta pares que violan
  (0 discrepancias en 20 corridas x 40 piezas contra fuerza bruta); y el manejo de touches no pierde el caso de
  dos piezas que se tocan con sep>0 (cae bien en la rama de separacion).
  >>> KIND NUEVO: "invalid_geometry", ademas de overlap/separation/out_of_bounds. La CLI lo reporta igual que
      los otros (codigo de salida 2, sin escribir archivo).

=== HITO 1 COMPLETO === El arbitro existe. 106 tests. 4 criticos y varios importantes encontrados y arreglados.
  PENDIENTE TRANSVERSAL: los mensajes en español de todo el proyecto estan sin tildes (los escribi asi en el
  plan, sin motivo). Hacer UNA pasada ortografica al final sobre todos los mensajes de cara al usuario
  (chaining, nesting_tree, verify, pipeline, material, dxf_reader, cli). No hacerlo de a pedacitos.
Task 8: completa — lector de DXF. 16 tests (15 del brief + 1 propio). Suite: 122 passed. Aprobada en la primera
  revision, sin criticos ni importantes.
  Requisito extra pedido por mi (del carry-forward de la Task 3): un ARC de barrido 360 se convierte a Circle en
  el lector, para que la normalizacion de angulos no lo colapse a start==end en la salida. Implementado y testeado.
  Dos desviaciones del implementador, ambas verificadas como correctas: la API real de ezdxf 1.4.4 no tiene
  vertices_in_wcs() para el POLYLINE antiguo (uso entity.vertices + v.dxf.location), y usa is_closed en vez de
  closed para unificar los dos tipos de polilinea. El revisor confirmo que las coordenadas quedan en WCS correcto
  probando un POLYLINE con bulges dentro de un INSERT rotado 90 grados.
  Verificado por el revisor con DXF construidos a mano: escala aplicada a puntos, radios Y los 4 puntos de control
  de cada Bezier; angulos de Arc NO escalados; INSERT anidado y con escala+rotacion propias; continuidad de cadenas
  de Bezier en SPLINE de grados 2/3/5 y en polilineas con bulges mezclados; color BYLAYER, ACI y true color;
  y el pipeline completo (4 LINE sueltas + CIRCLE -> 1 pieza con 1 agujero).
  Menor pendiente, AGRUPAR con la pasada ortografica: el mensaje de UnknownUnitsError dice "no declara unidades"
  incluso cuando el archivo SI declara una (millas, micrones, decimetros) que no esta en UNIT_SCALES. Conviene
  distinguir "no declarada" de "declarada pero no soportada (N)".
Task 9: completa — escritor de DXF. 9 tests. Suite: 131 passed. Aprobada en la primera revision.
  Contradiccion del plan arreglada: el test pasaba placements vacio y esperaba 1 rectangulo, pero el codigo con
  default=-1 daba 0 placas. Ahora default=0. Plan corregido.
  Verificado por el revisor con escritura + relectura real: fidelidad geometrica por tipo (Bezier vuelve como
  SPLINE grado 3 con los mismos puntos de control Y la misma curva muestreada); el ARCO BAJO ESPEJADO mas
  rotacion de 37 grados conserva sus extremos fisicos (el punto historicamente fragil del proyecto, verificado
  de punta a punta); el offset entre placas se compone DESPUES del espejado y la rotacion; tres Part con los
  mismos entity_ids (el caso de --copias) producen tres copias de la geometria y no una; ACI exacto y true color
  para aci=None; y _PLACA separada de la geometria de corte.
  Menor pendiente, AGRUPAR con la limpieza final: KeyError/IndexError crudos si un part_id no esta en parts o un
  entity_id esta fuera de rango. Falla seguro (no deja DXF corrupto, saveas es lo ultimo), pero sin mensaje
  accionable, a diferencia del patron del resto del proyecto.
  >>> OJO para el futuro (feature de retazos, fuera de v1): si la salida se vuelve a alimentar al pipeline sin
      filtrar, el rectangulo de _PLACA entra como contorno de nivel 0 y convierte todas las piezas en sus
      agujeros. La constante SHEET_LAYER esta exportada justo para poder filtrarlo.
Task 10: completa — catalogo de materiales. 21 tests. Suite: 152 passed.
  Dos IMPORTANTES arreglados: (a) los errores de catalogo mal formado se filtraban crudos ("could not convert
  string to float", AttributeError sobre .items()) sin nombrar material ni campo, y ese YAML lo edita el usuario
  a mano; (b) no habia validacion de rangos, asi que una placa de dimension 0 o negativa se aceptaba en silencio
  (y alimenta usable_w en verify.py, o sea el fallo aparecia lejos de la causa), y una tolerancia_veta negativa
  dejaba el material inservible rechazando TODOS los angulos incluidos 0 y 180.
  MENOR documentado: por la formula de distancia al eje de veta, cualquier tolerancia >= 90 equivale a rotacion
  libre. Quedo dicho en el docstring de Material, en allowed_angles y en la cabecera de materials.yaml.
Task 11: completa — interfaz Oracle (la costura) + ShelfOracle. 18 tests. Suite: 170 passed.
  CRITICO arreglado, y era un defecto de DISENO DEL CONTRATO que escribi yo: place(part,angle,mirror,x,y)
  recibia x e y pero ShelfOracle los IGNORABA y recalculaba el hueco. Si el llamador pasaba las coordenadas de
  otro angulo, el estado interno se desincronizaba en silencio y las piezas siguientes se superponian (el
  revisor lo reprodujo con un overlap real). Ahora: el docstring del Protocol dice explicitamente que place
  DEBE honrar (x,y), y que si una implementacion no puede representar posiciones arbitrarias tiene que VALIDAR
  y lanzar ValueError. ShelfOracle valida con PLACE_TOLERANCE y no avanza el estado si falla.
  Bug adicional encontrado por el implementador al escribir el test de secuencia mixta: la deteccion de
  "estante nuevo" comparaba el dy YA TRASLADADO contra _shelf_y, pero dy = shelf_y - by0, asi que con piezas
  espejadas o rotadas (bbox que no arranca en 0) daba falsos positivos y rompia la separacion. _next_slot ahora
  devuelve tambien el shelf_y absoluto. Plan corregido en los dos puntos.
  Oracle es ahora @runtime_checkable, asi que se puede validar con isinstance que motor esta enchufado.
  Verificado por mi: 60 piezas de tamanos dispares con rotaciones de 37 grados y espejado -> 0 violaciones.
  Menor pendiente p/revision final: el score usa -(y*1e6 + x), que asume que x nunca se acerca a 1e6. Teorico
  para placas de CNC (miles de mm), pero fragil si se relaja el supuesto.
Task 12: completa — pipeline.prepare_parts + engine.packer. 32 tests nuevos. Suite: 202 passed.
  Dos desviaciones del implementador, ambas correctas y bien documentadas: (a) _flatten_closed, porque
  flatten(Circle) no repite el primer punto y chain_contours lo veia como un contorno abierto por el ancho de
  una cuerda entera (cierra SOLO entidades intrinsecamente ciclicas, verificado); (b) DEFAULT_FLATTEN_TOL de
  0.2 a 0.02 mm, porque con 0.2 el area de un circulo de r=50 quedaba 0.5% baja y eso sesga hacia abajo el
  aprovechamiento que se le reporta al usuario.
  CRITICO arreglado en dos capas: math.cos(radians(90)) da 6.12e-17 en vez de 0, asi que con sep=0 dos piezas
  que deberian tocarse se superponian ~1e-11 mm2 y el arbitro lo marcaba. (1) transform.py ahora usa una tabla
  de valores EXACTOS para los cuartos de vuelta, que son los angulos mas comunes del sistema; rotar 4 veces por
  90 grados vuelve exactamente al punto original. (2) verify.py reporta overlap por AREA de interseccion con
  umbral de 1e-6 mm2 (antes: intersects and not touches, sin tolerancia). El umbral esta 5 ordenes por encima
  del ruido y muchos por debajo de lo fisicamente relevante, asi que no puede tapar un solapamiento real.
  IMPORTANTE arreglado: _raise_too_large tomaba min(anchos) y min(altos) de orientaciones DISTINTAS y describia
  una pieza inexistente (una de 1200x100 se reportaba como "100 x 100", que si entraba). Ahora usa una sola
  orientacion: la de lado mayor mas corto.
  IMPORTANTE arreglado: PackResult.unplaced era campo muerto (pack coloca todo o lanza PartTooLargeError).
  Eliminado por YAGNI, junto con las aserciones que lo comprobaban.
  Nota: mi prompt de revision dijo que no podia haber best_placement de otros angulos entre el ganador y su
  place. Era mas estricto que el contrato real: best_placement no muta, asi que intercalar consultas es legitimo.
  El revisor lo verifico con un espia. No era un bug.
Task 13: completa — CLI. 26 tests. Suite: 231 passed. CIRCUITO COMPLETO DE PUNTA A PUNTA FUNCIONANDO.
  Medicion de linea de base con el motor trivial sobre un DXF tipo banqueta (2 tapas redondas con 4 ranuras
  cada una + 4 patas concavas, x2 copias = 12 piezas): 13.6% de aprovechamiento, 1 placa. ESTE ES EL NUMERO
  QUE EL MOTOR RASTER TIENE QUE SUPERAR EN EL HITO 3.
  Error de proceso mio: habia corregido el test de esta tarea en el plan DESPUES de extraer el brief, asi que
  el implementador se topo con el defecto y lo resolvio distinto (haciendo que read_dxf saltee la capa _PLACA
  y lo avise, en vez de filtrar en el test). Acepte su enfoque porque cubre el flujo real de realimentar la
  propia salida. LECCION: re-extraer el brief si corrijo el plan despues de extraerlo.
  CRITICO arreglado: --borde negativo hacia que verify calculara un area util MAS GRANDE que la placa fisica,
  asi que las piezas quedaban colgando afuera y el arbitro lo aprobaba (medido: bbox x[-20,70] en una placa de
  200, codigo de salida 0). Igual con --sep negativo, que anulaba en silencio el chequeo de separacion
  (distance < sep - EPS nunca es verdadero si sep < 0). Arreglado en dos capas: validacion de rangos en la CLI
  y guarda defensiva en verify, que ahora lanza ValueError si sep o margin son negativos.
  IMPORTANTES arreglados: (a) tres caminos daban traceback crudo (--copias 0, directorio de salida inexistente,
  YAML sintacticamente invalido — esta ultima porque yaml.YAMLError no es subclase de OSError ni ValueError);
  (b) argparse salia con codigo 2 ante cualquier typo de invocacion, colisionando con el contrato de "fallo la
  verificacion" — ahora un ArgumentParser propio sale con 1, que es lo semanticamente correcto; (c) el aviso de
  la capa reservada afirmaba "generados por este mismo programa" sin haberlo verificado, y un usuario con
  geometria legitima en una capa llamada _PLACA perdia piezas con un aviso que le mentia.
  MENOR arreglado: en el camino del codigo 2, si ya existia un archivo en la ruta de salida, quedaba intacto sin
  aviso y podia mandarse a la CNC como si fuera el resultado nuevo. Ahora se advierte.
Task 14: completa — banco de pruebas. 10 tests. Suite: 241 passed.
  El revisor RECALCULO el aprovechamiento de forma independiente (area neta colocada / (area de placa x placas
  usadas)) y coincide exactamente: 13.5581% con 12 piezas y 40.6742% con 72. El denominador usa placas
  efectivamente abiertas, que es lo correcto.
  Tres IMPORTANTES arreglados, los tres sobre usar el banco con archivos REALES: (a) no habia aislamiento por
  archivo, asi que un DXF corrupto o sin unidades declaradas (el caso tipico de un export de Corel) tiraba abajo
  la corrida entera sin imprimir ni una fila, perdiendo las mediciones de los demas; ahora informa el error del
  archivo malo y sigue; (b) el README documentaba un flag --unidades que el banco no tenia (existe en la CLI
  principal) — ahora el banco lo tiene de verdad; (c) el primer comando del README usaba "python", que en esta
  maquina no existe.
  MENOR arreglado: habia dos relojes midiendo el mismo tramo (uno propio de run_one y el de PackResult.seconds).
  Quedo PackResult.seconds como fuente unica, que ademas es lo correcto a futuro: cuando el empaquetado haga
  varios reintentos, va a cubrirlos todos. Documentado que mide SOLO el empaquetado, sin lectura ni preparacion.

=== HITO 2 COMPLETO === Circuito de punta a punta funcionando y midiendo. 241 tests.
  >>> LINEA DE BASE A SUPERAR EN EL HITO 3: motor 'shelf' (bounding box), muestra sintetica con --copias 6:
      72 piezas, 2 placas, 40.7% de aprovechamiento. Con --copias 1: 12 piezas, 1 placa, 13.6%.
  Los archivos reales .ai y .3dm ya estan en bench/files/ esperando sus lectores (hito 5). El .cdr no se puede
  leer: Raulo tiene que exportarlo a DXF desde Corel (instrucciones en bench/README.md).
Task 15: completa — rasterizado de piezas. 25 tests. Suite: 267 passed. Tres rondas de arreglos.
  CRITICO, defecto del plan: yo asumi que PIL.ImageDraw.polygon marca todo pixel cuyo centro cae dentro del
  poligono. ES FALSO para lados no alineados a la grilla, y el error NO esta acotado a un pixel. El revisor
  midio hasta 1% de los pixeles del borde sin marcar, ya presente en el codigo literal del brief.
  Sub-representar material = el motor coloca piezas demasiado cerca = el verificador exacto rechaza el layout
  entero = el usuario se queda sin salida en un trabajo valido. Falla dura del producto.
  Ronda 1: sacar una contraccion de 1e-6 que el implementador habia agregado (empeoraba, en la direccion
    peligrosa) y dilatar 1 pixel. Mi chequeo independiente igual encontro 95 faltantes.
  Ronda 2: los faltantes estaban en la PARED DE LOS AGUJEROS, porque el exterior se dilataba pero los agujeros
    se restaban con el mismo relleno inclusivo, o sea borrando de mas. Simetria correcta: dilatar el exterior,
    EROSIONAR los agujeros. Mi chequeo con resoluciones mas finas igual encontro 1767 faltantes.
  Ronda 3 (la buena): dejar de depender de la semantica de relleno de Pillow. SUPERMUESTREO 4x, y reduccion
    asimetrica: exterior con "cualquiera" (cubre de mas), agujeros con "todos" (cubren de menos), mas la
    dilatacion/erosion de seguridad como margen de sobra en vez de justo.
  Verificacion final independiente mia: 640 combinaciones (poligonos aleatorios, paredes finisimas, multiples
  agujeros, angulos aleatorios, resoluciones 0.3 a 2.5 mm/px), 83.5 millones de pixeles, CERO FALTANTES.
  Costo: 2.6x en tiempo de rasterizado (3.7 -> 9.6 ms para una pieza de 300 mm a 1 mm/px). Densidad sin cambio.
  Otros IMPORTANTES arreglados: la cache indexaba por part.id (dos Part con el mismo id devolvian la mascara
  equivocada; ahora la clave incluye la geometria); sin cota de tamano de grilla se comia 8.8 GB a 0.02 mm/px y
  moria por OOM a 0.01; el tope de cache contaba entradas y no bytes (una pieza tamano placa pesa 9.1 MB, o sea
  4.66 GB con la cache llena) y ahora se acota por bytes.
  >>> PARA LA CALIBRACION (Task 24): rasterizar de forma conservadora cuesta densidad, y el costo es
      proporcional al perimetro sobre el area. Medido a 1 mm/px: +2% en una pieza de 300 mm, +9% en una de
      100x50. La palanca es la RESOLUCION, no el algoritmo. Vale la pena barrer --resolucion en la calibracion.
Task 16: completa — busqueda de posiciones por correlacion FFT. 19 tests. Suite: 286 passed.
  IMPORTANTE arreglado, con dientes: overlap_counts casteaba a float32, y el ruido de la FFT en float32 CRECE
  con el tamano del arreglo y con la cantidad de material en la placa. A 12000x16000 el revisor reprodujo
  FALSOS NEGATIVOS: un solapamiento real de 1 pixel midiendo 0.388 contra un umbral de 0.5, o sea posicion
  reportada como libre HABIENDO COLISION. No es hipotetico: --resolucion no tiene cota inferior, y una placa
  de 1830x2600 mm a 0.25 mm/px ya da 7320x10400.
  Arreglado pasando a float64: ruido 5.8e-11 a escala real y 2.2e-9 a 12000x16000, y un solapamiento real de
  1 pixel mide siempre exactamente 1.0. Margen restaurado a nueve ordenes de magnitud.
  Se probo tambien oaconvolve (metodo de solapamiento-y-suma): resultados identicos pero sin ventaja de
  velocidad para las proporciones placa/mascara de este motor. Se mantiene fftconvolve.
  MENOR arreglado: la forma del resultado no respetaba el contrato de 2 dimensiones en entradas degeneradas
  (una mascara con una dimension en cero hacia que fftconvolve devolviera un arreglo 1-D).
  >>> PRESUPUESTO DE TIEMPO PARA LA TASK 18: una correlacion a escala de placa completa (1830x2600 con mascara
      de 300x300) cuesta ~75 ms en float64 (era ~39 ms en float32). Con 60 piezas x 8 orientaciones son 480
      correlaciones por pasada = ~36 s, y con esfuerzo 'normal' (10 reintentos) serian ~6 minutos, por encima
      de lo que estimaba la spec. EL RECORTE A LA REGION ACTIVA NO ES UNA OPTIMIZACION, ES UN REQUISITO.
      Hay que implementarlo bien en la Task 18 y medirlo en la Task 24.
Task 17: completa — puntaje de posiciones. 22 tests. Suite: 308 passed.
  Bug del plan detectado por el implementador: dos tests pasaban np.ones((4,4)) como holgura a contact_band,
  que devuelve dilatar(holgura) & ~holgura con la MISMA forma — si la holgura llena el arreglo entero, la banda
  es necesariamente vacia y el test es insatisfacible. Las mascaras reales de rasterize siempre traen relleno.
  IMPORTANTE arreglado, otro numero mal elegido por mi: COLUMN_TIE_BREAK = 0.001 hacia que la contribucion de
  la columna superara una fila entera apenas la placa pasara de 1000 columnas. A escala real (1830 o 2600
  columnas a 1 mm/px, mas a resoluciones finas) el bottom-left DEJABA DE SER bottom-left: el revisor reprodujo
  que con la unica factible de la fila 0 en la ultima columna, elegia la fila 1. Arreglado normalizando el
  desempate por el ancho: columna/(columnas+1), asi el termino de columna nunca alcanza una fila POR
  CONSTRUCCION y no por eleccion de constante. Verificado por mi de 500 a 12000 columnas.
  MENORES arreglados: una discrepancia de formas entre la banda y las posiciones factibles se descartaba en
  silencio (un bug de integracion oculto) y ahora lanza; y Weights no validaba signo, lo que volvia
  incomparables los pesos y ensuciaria la calibracion.
  Evidencia de que el termino de contacto sirve: el revisor armo un bloque con una muesca del tamano exacto de
  una pieza; con peso de contacto la pieza se acopla en la muesca, sin el se va a la esquina. La caja
  delimitadora del material ocupado baja de 784 a 225 px2, un 71% mas compacto. Compra densidad real.
Task 18: completa — RasterOracle conectado. 321 passed, 0 en rojo. Tres rondas.
  CRITICO arreglado, defecto de diseno del plan: EL BORDE SE COBRABA DOS VECES. La grilla cubre el area util,
  pero la correlacion en modo "valid" exigia que entrara la mascara de HOLGURA completa —que incluye el halo de
  separacion—, o sea que el material quedaba a margen+sep del borde fisico. Medido: con margen 20 y halo 12, la
  primera pieza caia en 32 mm en vez de 20. Desperdiciaba una franja de sep alrededor de toda la placa.
  Arreglado rellenando la placa con ceros por 'pad' pixeles antes de correlacionar: el MATERIAL tiene que entrar
  en el area util, la HOLGURA puede sobresalir (mas alla del borde no hay piezas con las que chocar).
  Bug secundario: la holgura llegaba justo al borde de su arreglo, sin lugar para que contact_band dibujara el
  anillo — el termino de contacto quedaba casi inerte. Ahora 'pad' reserva tambien ese espacio.
  Test mio mal disenado, reemplazado: exigia meter 14 circulos en una placa, que esta a 0.7 mm del optimo
  geometrico global y ni siquiera sobrevive la cuantizacion de la grilla. Reemplazado por dos tests honestos:
  piezas que entran en UNA placa, y densidad de la primera placa.
  METRICA CIEGA detectada y corregida en el banco: total_utilization = area de piezas / (area de placa x placas),
  y como el conjunto de piezas es el mismo, SOLO puede variar si cambia la cantidad de placas. Con igual cantidad
  de placas da identica por construccion aunque un motor llene mucho mejor. El banco ahora informa tambien el
  aprovechamiento de la PRIMERA PLACA, que si distingue.

=== HITO 3 COMPLETO === El motor raster esta adentro y la mejora esta medida.
  RESULTADO (muestra.dxf, mdf18, sep 6, borde 10):
    48 piezas: shelf 2 placas / 27.1%  ->  raster 1 PLACA / 54.2%   (una placa entera ahorrada)
    72 piezas: 1ra placa 52.3% -> 60.0%
    14 circulos en una placa: shelf 9 -> raster 12 piezas (+33%)
  Verificado por mi con la CLI de punta a punta: 48 piezas, 1 placa, 54.2%, 47 s.
  Que los tests de la CLI, del packer y del banco pasaran SIN TOCARSE es la prueba de que la costura funciona.

  >>> PRESUPUESTO DE TIEMPO, PARA LA TASK 19 Y LA 24: una pasada golosa con 48 piezas y 8 orientaciones cuesta
      47 s a 1 mm/px. Si 'normal' hace 10 reintentos como dice el plan, son ~8 minutos, POR ENCIMA de los 3-5
      que estimaba la spec. Antes de fijar EFFORT_RESTARTS hay que:
      (a) medir DONDE se va el tiempo (la region activa deberia hacer baratas las primeras colocaciones);
      (b) revisar si la MaskCache se comparte: hoy pack() crea un RasterOracle por placa, y cada uno su propia
          cache, asi que las mascaras se re-rasterizan por placa y por reintento al pepe. Las mascaras dependen
          solo de (pieza, angulo, espejado, resolucion, sep), no del estado de la placa: UNA sola cache para
          toda la llamada a pack() es correcta;
      (c) fijar los reintentos contra un objetivo de reloj medido, no contra los numeros que adivine en el plan.
Task 19: completa — niveles de esfuerzo y compactacion de la ultima placa. 335 passed.
  CALIBRACION MEDIDA, no adivinada. Mis numeros del plan {rapido:1, normal:10, lento:120} habrian costado
  8 minutos y DOS HORAS Y MEDIA. Los medidos: {rapido:1, normal:3, lento:12}.
    rapido  1 reintento  -> 46s (48 piezas) / 81s (72 piezas)
    normal  3 reintentos -> 182s / 236s   (bajo el objetivo de 5 min; con 4 ya se rompe: 317s)
    lento   12           -> 575s / ~742s
  Perfilado (confirmado de forma independiente por el revisor con cProfile): la correlacion FFT es el 88% del
  tiempo y rasterizar el 6%. Por eso compartir la MaskCache entre placas y reintentos solo mejora 0.6-2.6%:
  ataca un costo que ya era chico. La region activa SI funciona: la primera pieza de una placa tarda 0.19s y
  la ultima 1.55s, unas 8 veces mas.
  IMPORTANTE arreglado: 'lento' podia dar PEOR que 'normal' con la misma semilla, porque son busquedas distintas
  (reintentos aleatorios desde el orden original contra escalada de colina desde el mejor conocido), sin relacion
  de superconjunto. Para el usuario, mas esfuerzo tiene que significar nunca peor. Arreglado haciendo que 'lento'
  ejecute primero exactamente los mismos reintentos que haria 'normal' —misma base y mismo consumo del generador—
  y recien despues siga con escalada. Medido: el caso que fallaba pasa de (1,1324) a (1,1300).
  MENOR arreglado: un test del brief usaba 18 rectangulos IDENTICOS para comprobar que semillas distintas dan
  resultados distintos; con piezas iguales dan lo mismo, asi que la clausula 'or' lo satisfacia trivialmente.
  DATO HONESTO QUE QUEDO DOCUMENTADO EN EL CODIGO: 'normal' cuesta 3-4 veces mas que 'rapido' y EMPATA con el en
  5 de 7 escenarios. Su ganancia no es gradual: aparece cuando el trabajo queda cerca de necesitar una placa
  mas, que es justo donde ahorra una placa entera. Vale la pena, pero el usuario merece saber que compra.
Task 20: completa — previsualizacion PNG. 12 tests. Suite: 347 passed.
  CRITICO arreglado: una pieza anidada dentro del agujero de otra DESAPARECIA del dibujo si su colocacion venia
  antes en la lista, porque el agujero de la grande se pintaba encima y la borraba. Nada en el modelo garantiza
  ese orden, asi que era cuestion de suerte. Grave por partida doble: el usuario veria una placa a la que le
  falta una pieza que el DXF SI va a cortar, y justo se perderia de ver la capacidad de anidar en agujeros.
  Arreglado dibujando por area descendente: una pieza que cae en un agujero es necesariamente mas chica que su
  contenedora, asi que ese orden garantiza que la contenedora se dibuje primero.
  IMPORTANTES arreglados: un part_id desconocido levantaba KeyError crudo (justo el bug que esta herramienta
  deberia ayudar a diagnosticar), ahora dibuja lo que puede y avisa; y sin tope de escala, px_per_mm=50 sobre una
  placa de 1000 mm generaba un PNG de 10 MB que Pillow despues SE NIEGA A ABRIR por posible bomba de
  descompresion — o sea que escribia un archivo que ni el propio proyecto puede leer.
  Verificado por mi visualmente: genere la comparacion de los dos motores sobre 48 piezas y se ve exactamente lo
  que buscabamos — el trivial apila en filas rigidas y deja la 2da placa casi vacia, el raster ENTRELAZA las
  patas una en la concavidad de la otra y acomoda los circulos en panal, todo en 1 placa. Imagenes enviadas.
Task 21: completa — CLI completa con --esfuerzo, --preview y sobrante util. Suite: 362 passed.
  CRITICO arreglado: el bloque de write_preview solo atrapaba ValueError, asi que un error de sistema de
  archivos salia como traza cruda. Terminaba con codigo 1 solo por el comportamiento por defecto de Python ante
  una excepcion no atrapada, no por una decision del programa.
  IMPORTANTE arreglado: --preview creaba arboles de directorios EN SILENCIO mientras que -o daba error
  controlado ante lo mismo. Dos comportamientos distintos para la misma situacion en la misma invocacion.
  Ahora los dos dan error claro.
  MENOR arreglado: otra asercion vacia, `assert "s" in output` — cualquier texto en español contiene una "s".
  Verificado por el revisor: --esfuerzo llega de verdad al packer (instrumento pack y los tiempos escalan con
  los reintentos); el preview se escribe DESPUES de la verificacion, asi que nunca queda una imagen huerfana de
  un layout rechazado; el sobrante util es correcto en placa casi llena, casi vacia y con varias placas.

=== HITO 4 COMPLETO === El producto esta usable de punta a punta. 362 tests.
Task 22: completa — lector de archivos .ai (AI3/PostScript). 23 tests. Suite: 385 passed.
  EL ARCHIVO REAL DEL USUARIO ANDA DE PUNTA A PUNTA. bench/files/banqueta.ai, export genuino de
  CorelDRAW 2020: 40 piezas reconocidas, 1 placa, 25.3%, sobrante util 1830x1308 mm, codigo de salida 0, 52 s.
  NINGUN contorno abierto con la tolerancia por defecto (0.1 mm) — buena señal sobre la calidad del export.
  PROBLEMA REAL DEL FLUJO DEL USUARIO, encontrado y resuelto: CorelDRAW exporta el BORDE DE LA MESA DE TRABAJO
  como geometria real, un rectangulo de 900x2600 mm que el sistema tomaba como la pieza mas grande del archivo
  y hacia fallar la corrida entera con "no entra en una placa vacia". El propio archivo declara ese rectangulo
  en su cabecera (%%BoundingBox:0 0 2551 7370 = 900x2600 mm), asi que se identifica sin adivinar.
  La condicion quedo ESTRICTA a proposito: el contorno tiene que SER el rectangulo (cerrado, 4 esquinas,
  alineado a los ejes, los 4 lados coincidiendo dentro de 1 mm), no solo tener una caja envolvente que coincida
  — porque la pieza mas grande de cualquier archivo toca el bounding box por definicion. Hay tests de que NO
  descarta de mas: un triangulo que toca los 4 bordes, una forma en L, coincidencia en 3 lados, un rectangulo
  desplazado y uno rotado. Y siempre avisa.
  Previsualizacion verificada por mi: se ven las patas en cruz (rojas y verdes, dos lotes de color), los
  asientos redondos con sus ranuras y las bases. Coincide con los screenshots de Corel que mando el usuario.
  Colores originales preservados. Imagen enviada.
Task 23: completa — lector de archivos .3dm de Rhino. 13 tests. Suite: 398 passed.
  BUG REAL encontrado por el implementador al probar contra el archivo real: el chequeo de tolerancia de cuerda
  comparaba solo en X,Y ignorando Z. Para un circulo completo parado en el plano XZ, eso daba una coincidencia
  matematica exacta en los cuartos de vuelta que detenia la subdivision al primer nivel y colapsaba el circulo
  en una polilinea degenerada de 3 puntos SIN NINGUN AVISO — justo lo que el chequeo de planaridad debia evitar.
  Corregido comparando en 3D, con test de regresion.
  EL ARCHIVO .3dm DEL USUARIO DA 0 PIEZAS, Y ESTA BIEN. Verificado por mi de forma independiente: 59 objetos
  (21 ArcCurve, 30 PolyCurve, 3 PolylineCurve, 5 cotas), y las 54 curvas abarcan 500 mm en Z — son los circulos
  PARADOS EN VERTICAL. Es el modelo 3D ARMADO de la banqueta (patas cilindricas verticales, tableros en sus
  posiciones reales), no un despiece plano como el .ai. Antes de la correccion del bug, 21 de esas curvas se
  colaban falsamente como planas.
  >>> PARA DECIRLE AL USUARIO: su .3dm no sirve para nestear tal cual. Habria que desarrollar el despiece a 2D
      en Rhino primero. El .ai si funciona (40 piezas).
  Tradeoff declarado de este lector, distinto a los otros dos: lineas y polilineas exactas, pero NURBS, arcos y
  curvas compuestas se MUESTREAN a polilineas al leer (0.05 mm), porque convertir NURBS a Beziers exige
  insercion de nudos que rhino3dm no expone de forma confiable entre versiones. Declarado en el docstring.

=== HITO 5 COMPLETO === Los tres formatos de entrada andan. 398 tests.
Task 24: completa — calibracion con mediciones sobre archivos reales.
  Metodo: hubo que FORZAR DESBORDE DE PLACA para que las metricas distinguieran algo. Tanto el aprovechamiento
  total como el de la primera placa son un cociente FIJO cuando todas las piezas entran en una placa, sin
  importar como se acomoden. Mi primer barrido cayo en esa trampa (dio 54.2% identico para todos los valores);
  el agente lo detecto y midio con 8 y 5 copias, forzando 2 y 3 placas.
  PESO DE CONTACTO: se mantiene en 1.0, pero AHORA POR UNA RAZON MEDIDA. El aprovechamiento agregado dice que
  conviene apagarlo (contact=0 es 34-46% mas rapido porque saltea la segunda FFT, y en muestra.dxf hasta da un
  punto mas). Pero una biseccion contra el caso de anidar una pieza chica en el agujero de una grande mostro
  el umbral: por debajo de ~0.8 el bottom-left le gana el argmax al contacto y la pieza se va a la esquina en
  vez de meterse en el agujero. O sea que apagarlo tiraria la capacidad que justifica todo el motor raster.
  1.0 es el valor mas chico que la preserva.
  RESOLUCION: CAMBIADA de 1.0 a 2.0 mm/px. De 1.0 a 2.0 no cuesta nada en muestra.dxf (identico) y cuesta 0.76
  puntos en el archivo real, a cambio de 4.5-4.8x menos tiempo. A 3.0 ya se pierden 2.9 puntos. A 0.5 sale 4.9x
  mas caro por una ganancia marginal. El verificador exacto dio CERO violaciones en todas las resoluciones: la
  resolucion mas gruesa cuesta densidad, nunca correccion, porque la separacion se valida sobre los poligonos
  exactos y no sobre la grilla.
  EFFORT_RESTARTS no se toco: ya estaba calibrado en la Task 19.
  COMPARACION FINAL raster vs trivial (primera placa): muestra.dxf 56.1% -> 62.9% y ademas una placa menos
  (3 -> 2); banqueta real 54.9% -> 60.3%.
  Efecto colateral bueno del cambio de resolucion: EFFORT_RESTARTS se calibro a 1.0 mm/px, asi que a 2.0 cada
  nivel corre mas rapido que lo medido, nunca mas lento. El objetivo de 5 min para 'normal' queda con mas margen.

LIMPIEZA FINAL: pasada ortografica sobre ~40 mensajes de cara al usuario en 13 archivos (tildes, eñes, signos
  de apertura). Ademas: UnknownUnitsError ahora distingue "no declara unidades" de "declara una unidad no
  soportada" nombrandola con su codigo; y dxf_writer ya no deja escapar KeyError/IndexError crudos (nuevas
  UnknownPartError e InvalidEntityIdError con mensaje accionable).

=== PROYECTO TERMINADO === 24/24 tareas. 423 tests, 0 fallas.

REVISION FINAL DE TODO EL PROYECTO (la que mira el conjunto, no tarea por tarea). Encontro 2 criticos y
5 importantes que ninguna revision individual podia ver. Todos arreglados:
  C1: un contorno de area cero no se filtraba (la spec 6.3 lo pide). Un export sucio de Corel podia tirar abajo
      el trabajo entero con codigo 2 y un mensaje que MENTIA ("se autointersecta" cuando era colineal), o
      reventar con IndexError si todas las piezas tenian area cero. Arreglado: se filtran con aviso.
  C2: el lector de .3dm ADIVINABA UNIDADES en silencio — cubria 5 de los 27 sistemas de Rhino y trataba el resto
      como milimetros sin avisar. Politica opuesta a la del lector de DXF, que distingue con cuidado. Ahora
      falla con UnknownUnitsError y acepta --unidades.
  I1: LOS COLORES SE PERDIAN en la salida DXF -> DXF. La rama de color verdadero era INALCANZABLE porque el
      lector siempre completa el ACI con 256 (BYLAYER). Peor: la previsualizacion usa style.rgb, asi que el PNG
      mostraba los colores correctos y el DXF que va a la fresadora no. Y habia un test que pasaba en verde
      justo sobre esa propiedad, porque usaba un ACI explicito (el unico caso que funcionaba).
  I2: si fallaba la previsualizacion, se ocultaba que el DXF SI se habia escrito. Politica de errores invertida.
  I3/I4: dos trazas crudas que quedaban (--resolucion muy chica, y un .3dm invalido).
  I5: el camino de escritura que usan el 100% de los archivos reales (Bezier -> SPLINE) no tenia NINGUN test.
      La corrida sobre el archivo real escribe 2682 SPLINE y cero LINE, y los tests solo cubrian LINE y CIRCLE.
Menores documentados y no arreglados a proposito, con su justificacion, en el informe de la revision final.

=== MUDANZA (2026-09-18) ===
El proyecto se movio de <home>/cut-placement a <home>/Projects/cut-placement.
(El usuario escribio "Porjects"; use "Projects", que es el que existe y tiene sus otros proyectos.)
El venv NO se movio: tenia rutas absolutas grabadas en los shebangs de .venv/bin/* y en el .pth de la
instalacion editable. Se reconstruyo de cero en el destino.
Se descartaron, por regenerables: .venv, .pytest_cache, .coverage, __pycache__ y los .egg-info.
Verificado en la ubicacion nueva: 423 tests en verde; la CLI sobre banqueta.ai da el mismo
resultado (80 piezas, 1 placa, 50.7%); el banco da los mismos numeros (raster 1 placa 54.2% contra shelf
2 placas 27.1%); y DEFAULT_MATERIALS_PATH resuelve bien porque se calcula relativo al paquete.

=== --diagnostico (2026-09-18) ===
Pedido del usuario: los avisos dicen CUANTO se descarto pero no CUAL. En un dibujo de 11 metros, un tramo
suelto de 12 mm -- o de 24 micrones -- es invisible. Nueva bandera --diagnostico RUTA.png que marca sobre el
dibujo original todo lo descartado, con una tira de recuadros de zoom numerados.

DECISION DE DISENO CENTRAL: cada sitio que descarta algo ahora devuelve EL OBJETO, no un contador.
  chain_contours      -> tuple[int, ...] con los ids duplicados   (antes: len)
  build_parts         -> list[Contour] de los de area nula        (antes: int)
  discard_plate_outline -> list[Part] descartadas                 (antes: int)
  prepare_parts       -> (parts, warnings, discards)              (antes: 2-tupla)
  Drawing             -> campo nuevo `discards`, paralelo a `warnings`
El aviso de texto se arma con len() sobre la MISMA lista que dibuja el diagnostico, asi que el numero que se
imprime y las marcas de la imagen no pueden discrepar. Un contador por un lado y una lista por el otro si
podrian, y esa deriva ya mordio una vez en este proyecto (I1: los colores que la previsualizacion mostraba
bien y el DXF perdia).

prepare_parts NO muta el Drawing que recibe: copia `discards` igual que ya copiaba `warnings`. El Drawing
sigue vivo despues (dxf_writer le saca los colores originales), asi que ensuciarlo lo dejaria distinto de lo
que produjo el lector. Hay test.

El diagnostico se escribe ANTES del acomodo. Dos motivos: si es lo unico que se pide el comando sale en ~1s
(medido: 1.1s contra 34s del acomodo completo sobre robot.ai), y si la ruta del PNG esta mal el usuario
se entera ya y no despues de medio minuto tirado. Como todavia no se escribio nada mas, fallar ahi no puede
ocultar un archivo que si salio -- que era el defecto I2 de --preview.

DEFECTOS ENCONTRADOS Y ARREGLADOS DURANTE EL TRABAJO (todos por mirar el PNG real, ninguno lo agarro un test
que yo hubiera escrito antes de mirar):
  D1: ACENTOS ROTOS. La tipografia por omision de Pillow 12 es FreeType pero NO tiene 'a' ni 'n' con tilde:
      las dibuja como el cuadradito de glifo desconocido. Toda la interfaz de este programa esta en espanol,
      asi que la leyenda quedaba ilegible justo donde explica por que se descarto algo. Arreglado con una
      cadena de candidatas (_font) que cubre Linux y macOS. El test compara el glifo contra un caracter que
      ninguna tipografia latina tiene: si salen iguales, los dos son el cuadradito.
      OJO: mi primera verificacion de esto dio un falso verde. Compare 'nae' con 'nae' acentuado y dieron
      distinto -- pero daban distinto porque uno era tofu y el otro letras. El test bueno compara contra tofu.
  D2: ZOOMS_PER_ROW estaba fijado a mano en 6 y la sexta columna terminaba 98 px FUERA del lienzo, partida,
      con su etiqueta perdida entera. Ahora se calcula de PLAN_W (da 5). Hay test.
  D3: El renglon de la leyenda que dice el total no tenia alto reservado y se dibujaba fuera del lienzo. Es
      justo el que avisa que hay mas descartes de los que se ven marcados. Hay test.
  D4: VENTANA DE ZOOM FIJA -> el rectangulo del tamano de la placa (1830x2600) daba un recuadro COMPLETAMENTE
      VACIO, que se lee como un error del programa. Ahora la ventana se agranda cuando el descarte no entra, y
      la leyenda dice siempre cuantos mm abarca.
  D5: "[ventana 299..." truncado por 2990 mm. Truncar ese texto no lo deja incompleto: lo deja MINTIENDO,
      porque es el unico dato que fija la escala. Va en renglon propio y hay test de que nunca se recorta.
  D6: usaba draw._image (atributo privado de Pillow) para pegar los recuadros. Cambiado a pasar la Image.

DOS TESTS MIOS ESTABAN MAL, no el codigo:
  - test del borde de lienzo en .ai: compare contra 100 mm cuando el cuerpo del .ai esta en PUNTOS y el
    descarte sale en mm (100 pt = 35.28 mm).
  - test del contorno de placa en la CLI: puse la pieza chica ADENTRO del rectangulo de placa, asi que se
    volvio un agujero de el y entonces ya no era un contorno de placa (la regla pide sin agujeros, y esta
    bien que la pida).

MEDIDO sobre los archivos reales del usuario:
  robot.ai : 3 descartes, 3 marcados. 1.1s.
  robot.3dm: 9 descartes, 6 marcados (las 3 cotas de Rhino no tienen contorno en XY que marcar). 1.0s.
DIAGNOSTICO DE LOS ARCHIVOS DEL USUARIO (lo que el pregunto):
  - Las 2 "duplicadas" del .ai y 2 de los 4 "tramos sueltos" del .3dm SON LA MISMA COSA: dos lineas de 12 mm
    en y=2673.79 (x 8648-8660 y x 8837-8849), el lado de arriba de dos rectangulitos de 12x25 mm, dibujado dos
    veces. En .ai no existe "curva cerrada" y el encadenador la absorbio como lado del rectangulo, sobrando
    una copia -> "duplicada". En .3dm el rectangulito ya viene cerrado, asi que no tenian con que unirse ->
    "suelta". Los dos archivos terminan en 165 contornos -> 93 piezas -> 47.7%. No se pierde nada.
  - Los otros 2 tramos sueltos miden 0.024 mm: vertices repetidos sobre el borde de dos piezas.
  - Los "3 objetos que no son curvas" son 3 cotas (DimLinear) que dicen 1201.40, 734.19 y 400.47.
  - La "curva no plana" es una polilinea cerrada de 77 tramos, 436 x 1583 mm, parada en el plano vertical
    (y=100.3 constante, z de -62 a 1521): la silueta del robot armado de frente, una vista de referencia.
    Es la unica de las tres que vale la pena que el usuario mire.
  D7: LOS ANILLOS SE DIBUJABAN ABIERTOS. Los contornos de este programa se guardan sin repetir el primer
      punto al final (convencion de `Contour`), asi que el rectangulo de placa salia en el recuadro CON TRES
      LADOS y el cuarto faltando -- que se lee como geometria rota, o sea el diagnostico exactamente
      equivocado sobre un rectangulo que esta perfecto. Campo `closed` en Discard + propiedad `path` que
      cierra el anillo, y `path` idempotente para los que ya llegan cerrados (las duplicadas, que pasan por
      _flatten_closed) para no dejarles un segmento de largo cero al final.
  D8: HUECO QUE ABRI YO al hacer -o opcional: --diagnostico junto con --preview y sin -o pasaba la validacion,
      escribia el diagnostico, salia con 0 y SE OLVIDABA DEL PREVIEW en silencio. El usuario esperaba un PNG
      que nunca llegaba, sin una linea que lo explicara. Ahora --preview sin -o se rechaza con un mensaje que
      dice por que (la previsualizacion dibuja el acomodo) y adonde ir (--diagnostico).

ESTADO: 495 tests, 0 fallas (eran 434). Verificado end to end sobre los dos archivos reales del usuario.

=== INTERFAZ GRÁFICA (2026-09-19) ===
Plan: docs/superpowers/plans/2026-09-19-interfaz-grafica.md (14 tareas)
Rama: interfaz-grafica, desde main en de51338.
Pre-flight: ningún test existente toca _validate_numeric_args ni _pack_once, así que las tareas 1 y 4
  no pueden romper la suite por la puerta de atrás. DEFAULT_MATERIALS_PATH sí lo usan
  tests/model/test_material.py:73 y :192, y la Task 2 lo contempla explícitamente.
DECISIÓN del usuario (pre-flight): los tests de HTML/JS por búsqueda de texto se quedan, PERO se sacan los
  frágiles (tipo `assert "180" not in js`). Se conservan los que verifican contrato real: que exista cada id
  que el JavaScript busca, y que se use cada ruta que la API expone. Aplica a las tareas 10, 11 y 12.
Task 2: completa (commits 0ce9601..fad34e0, revisión limpia).
  ERROR DEL PLAN que se coló hasta la revisión: recurso("web") resolvía a <repo>/web, pero la interfaz vive
  en src/nesting_app/web/ (adentro del paquete, para que pip install la instale). Como el test sólo pedía
  .is_dir(), el implementador creó una carpeta vacía en la raíz y pasó en verde contra la equivocada.
  Arreglado con el mapa EN_EL_REPO, que separa el camino congelado (todo aplanado en _MEIPASS) del camino
  desde el repo (cada recurso donde de verdad está).
  Segundo hallazgo, que el revisor comprobó ARMANDO EL WHEEL: package-data con "web/*" no es recursivo y
  dejaba las subcarpetas afuera sin error. Ahora son cuatro patrones.
  Tercer hallazgo: el test de eso NO PROBABA NADA. Con sólo .gitkeep adentro y un break en el bucle, el
  patrón recursivo nunca se ejercitaba. Ahora arma un árbol sintético en tmp_path y se verificó que falla
  al sacar cada patrón.
  MENORES anotados, no arreglados: ninguno pendiente (los dos se arreglaron en fad34e0).
  LECCIÓN: un test que pide "existe un directorio" se satisface con cualquier directorio vacío. Tres veces
  en dos tareas el test pasó en verde sobre la cosa equivocada.
Task 3: completa (commits fad34e0..c31dbfb, revisión limpia).
  El implementador transcribió el brief tal cual, así que los huecos que quedaron ya estaban en el brief:
  editar() rechazaba renombrar encima de otro material pero NINGÚN test lo ejercitaba -- borrar ese if
  dejaba los 14 tests en verde mientras el usuario perdía las medidas de un material. El test nuevo además
  verifica que ninguno de los dos materiales quedó modificado: levantar después de haber escrito sería
  pérdida de datos igual. El revisor lo probó rompiendo editar() de tres formas distintas y las agarra todas.
  Dos mensajes decían qué falló y no qué hacer. Al completarlos, el primer intento inventó una causa
  ("se puede haber borrado desde otra ventana") que no existe: el programa tiene una sola ventana.
  LECCIÓN: al hacer accionable un mensaje, la acción tiene que ser real. Un diagnóstico inventado manda a
  buscar donde no es, que es peor que no decir nada.
Task 4: completa (commits c31dbfb..4256db4, revisión limpia). Único cambio al motor en todo el plan.
  pack() acepta progreso: Callable[[Avance], bool]; devolver False levanta Cancelado. _compact_last_sheet
  NO recibe avisos a propósito: reacomoda una sola placa y sus conteos no son comparables con los de una
  pasada completa; harían saltar la barra.
  DOS ERRORES DE MI PLAN que encontró el implementador: el helper config(**cambios) del test duplicaba
  `effort`, y la comparación usaba p.part cuando Placement sólo tiene part_id. Los corrigió bien y además
  sumó p.transform a la comparación, así el test de "sin callback da lo mismo" compara POSICIONES y no
  sólo ids.
  MENOR anotado, no arreglado: test_cancelar_no_deja_el_resultado_a_medias es redundante con
  test_devolver_False_cancela_y_levanta. Para la limpieza final.
Task 5: completa (commits 4256db4..HEAD, revisión limpia).
  archivos.py es la única puerta que sabe escritorio-contra-web. El revisor probó a mano C:\x.dxf, UNC,
  "..", ".dxf" y "" y ninguno escapa la carpeta: por construcción, como la extensión válida tiene que estar
  al final del string, el segmento final nunca puede quedar vacío ni ser "..".
  TRES IMPORTANTES: un byte nulo en el nombre reventaba con ValueError crudo en inglés; el consejo sobre
  CorelDRAW aparecía aunque hubieras subido un PNG; y ningún test ejercitaba el rechazo de extensión por
  registrar_local, así que un refactor podía romper la paridad entre las dos puertas sin que nada avisara.
  El revisor de la segunda vuelta hizo PRUEBAS DE MUTACIÓN sobre cada arreglo: revirtió cada uno y confirmó
  que el test correspondiente vuelve a fallar. Encontró además que el arreglo había reducido un parametrize
  sin necesidad.
  OBSERVACIÓN para la Task 8: el brief declaraba `Consumes: nesting_app.rutas` pero archivos.py no lo usa.
  Deposito recibe su carpeta por parámetro, así que quien lo instancie tiene que pasarle una ruta derivada
  de rutas.carpeta_datos().
Task 6: completa (commits c1ca0b9..a6714b9, código de producción verificado limpio). TRES vueltas de arreglo.
  jobs.py separa administrar trabajos de hacerlos: recibe un `corredor` y lo ejecuta, así los tests del ciclo
  de vida tardan milisegundos en vez de medio minuto.
  R1 -- TRES carreras reales, todas reproducidas por el revisor: cerrar() recorría self._trabajos.values()
    mientras crear() escribía (RuntimeError); crear() después de cerrar() dejaba el trabajo en PENDIENTE para
    siempre, sin señal; y ERRORES_DEL_USUARIO incluía KeyError, así que un bug nuestro le decía al usuario
    "revisá tu dibujo". Ahora la lista es explícita: las 7 excepciones que el motor levanta por problemas del
    archivo, y ChainingInvariantError / UnknownPartError / InvalidEntityIdError del lado de bug nuestro.
  R2 -- el arreglo dejó una VENTANA RESIDUAL: los dos cola.put() habían quedado fuera del lock. Y el test de
    concurrencia NO TENÍA MORDIDA: el revisor lo corrió 20 veces contra el código sin lock y pasó las 20.
  R3 -- el test nuevo decía "esto no es una apuesta de timing" y detectaba 8 de 90. Ahora detecta 23 de 30 y
    el docstring DICE ESE NÚMERO en vez de prometer determinismo.
  LECCIÓN: en código con hilos, "los tests pasan" no dice nada. Lo único que vale es revertir el arreglo y
  contar cuántas corridas lo detectan. Tres tests de esta tarea parecían cubrir algo y no lo cubrían.
Task 7: completa (commits a6714b9..1817bbe, revisión limpia). TRES vueltas.
  corredor.py hace el mismo recorrido que cli.py: verifica ANTES de escribir, y si la verificación falla no
  queda ningún archivo.
  R1 -- LOS AVISOS SE CALCULABAN Y SE TIRABAN. Resultado no tenía campo y Registro nunca escribía en
    Trabajo.avisos. Importaba sobre todo por el aviso del rectángulo del tamaño de la placa, que SÓLO se
    puede generar en acomodar() porque necesita las medidas del material: no había ningún otro lugar del
    sistema donde el usuario pudiera enterarse. Y write_preview no estaba protegido como en la CLI: si
    fallaba después de un write_dxf exitoso, el trabajo quedaba en ERROR aunque el DXF estuviera perfecto.
  R2 -- el arreglo cubrió cuatro raise y se escapaban replicate(), pack() y verify(). El revisor lo
    reprodujo con esfuerzo inválido: ERROR, es_bug=False, avisos vacíos.
  R3 -- se reemplazó por UN try/except Exception que envuelve todo el bloque posterior a que avisos exista,
    con `except Cancelado: raise` adelante para no romper la cancelación. Así un raise nuevo mañana queda
    cubierto sin que nadie tenga que acordarse.
  LECCIÓN: arreglar caso por caso deja el próximo caso afuera. Cuando el problema es "hay que acordarse",
  la solución tiene que quitar la necesidad de acordarse.
  NOTA: el import de nesting_app adentro de una función en nesting/model/material.py NO es una violación;
  es deliberado y está documentado ahí. Un revisor lo marcó de paso.
Task 8: completa (commits 1817bbe..e18c9a6, revisión limpia). API: token, materiales, archivos, análisis.
  El implementador cambió el token de "dependencia por ruta" (lo que traía el brief: una lista que hay que
  acordarse de actualizar) a un middleware. Bien pensado, pero la primera versión usaba @app.middleware("http")
  = BaseHTTPMiddleware, que DEJA PASAR TODO SCOPE QUE NO SEA HTTP, incluidos los websockets. El revisor lo
  comprobó agregando una ruta websocket: el handshake se aceptaba sin token. Y el test que debía protegerlo
  filtraba por getattr(ruta,"methods") -- una APIWebSocketRoute no lo tiene, así que quedaba excluida EN
  SILENCIO y el test seguía verde. Ahora es un middleware ASGI puro y el test recorre todas las rutas.
  /openapi.json estaba abierto sin token y exponía las seis rutas con el nombre de cada campo. openapi_url=None.
  ERROR MÍO: commiteé "Declarar python-multipart y httpx" y httpx nunca entró -- mi str.replace no matcheó
  (la línea era dev = ["pytest"], sin pyinstaller, que recién llega en la Task 14) y no verifiqué la salida
  del grep, que sólo mostraba python-multipart.
  LECCIÓN: un reemplazo de texto que no matchea no falla, no hace nada. Hay que verificar el resultado, no
  que el comando salió con código 0.
Task 9: completa (commits e18c9a6..0c2f182, revisión limpia, sólo un Menor). API de trabajos.
  El revisor probó la ruta de descarga con ../../../etc/passwd, ..%2F..%2F, %00 y un scope ASGI crudo sin
  normalizar, para descartar que el resultado dependiera de que httpx normaliza del lado cliente. Los seis
  dan 404: el nombre se compara contra un diccionario cerrado de tres claves ANTES de tocar disco.
  Dos errores más del brief que corrigió el implementador: `dependencies=protegido` no existe (la protección
  la hace el middleware de la Task 8, no una dependencia por ruta), y el DXF de ezdxf usa \n y no \r\n.
  MENOR anotado: el 404 de un nombre de archivo inválido no dice cuáles son los válidos.
Task 10: completa (commits 0c2f182..15c1e51, revisión limpia). HTML y CSS de la dirección D.
  El revisor comparó el HTML y el CSS contra el brief BYTE A BYTE, extrajo los 49 ids programáticamente y
  verificó que los 11 label-for apunten a ids que existen. Recalculó los tres contrastes por su cuenta:
  #606B7B/#FFFFFF 5.40:1, #606B7B/#F4F6F8 4.99:1, #FFFFFF/#047857 5.48:1, y además midió los que nadie había
  medido (rojo de error, insignias): todos arriba de 4.5:1.
  DOS MENORES heredados de mi brief, arreglados: el box-shadow del foco tenía rgba(4,120,87,.12) -- el acento
  escrito a mano, así que cambiar --acento habría desincronizado el halo del borde. Y el regex de emojis
  dejaba pasar banderas, ⭐, ⌛ y ‼.
Task 11: completa (commits 15c1e51..HEAD). CUATRO vueltas. El flujo principal en JavaScript.
  CRÍTICO, y era un bug de mi plan: mostrarImagen() hacía img.src = "/api/..." y el botón Guardar hacía
  a.href = "/api/...". Un <img> y un <a download> son pedidos nativos del navegador y NO PUEDEN LLEVAR
  CABECERAS, así que el middleware del token los rechazaba con 401. La previsualización mostraba siempre una
  imagen rota y la descarga web no bajaba nada -- la función central de la pantalla, rota de punta a punta,
  en escritorio y en web. Ningún test de texto podía verlo: este JavaScript no se ejecuta en ningún test.
  Ahora se trae con fetch vía api(), se arma un Blob y se usa createObjectURL.
  Después: una carrera entre dos pedidos de imagen superpuestos (dos <img> apilados y un blob filtrado si la
  segunda respuesta llegaba antes que la primera), un catch que tapaba un 500 mostrando el mismo texto que un
  409, y tres promesas sin catch.
  El test que debía cubrir el bug crítico SÓLO AGARRABA LA MITAD: su regex exigía la ruta pegada al `=`, y el
  bug del botón Guardar era `a.href = url` con url armado antes. Ahora cubre las dos formas, verificado
  reintroduciendo cada una.
  LECCIÓN: el código que ningún test ejecuta necesita que alguien lo lea como si lo ejecutara. Las cuatro
  vueltas salieron de leer, no de correr nada.
Task 12: completa (commits 7007319..HEAD, revisión limpia). Pantalla de materiales.
  El brief traía TRES bugs que el implementador corrigió: un onclick sobre btn-materiales que pisaba el de
  app.js (.onclick= es asignación, no addEventListener, así que el segundo gana y el primero desaparece),
  btn-volver que no volvía a mostrar la pantalla principal, y un await sin catch.
  HALLAZGO IMPORTANTE: el nombre del material iba sin escapar a innerHTML. Es texto libre que el usuario
  tipea y queda guardado en materials.yaml, así que se re-ejecuta cada vez que alguien abre la pantalla --
  persistente, no reflejado. En la versión web con catálogo compartido, el material que guarda uno corre en
  el navegador de todos. Ahora las celdas van con createElement/textContent.
  El test de ids tenía un punto ciego: su regex sólo tomaba $("literal") y se comía los del ternario
  $(cond ? "a" : "b"). Arreglado en los dos tests.
  SE DESCARTÓ, con el visto bueno del dueño: `assert "180" not in js_materiales`, frágil (se rompe con un
  180px). Lo que quería verificar ya lo cubre el test de que use las palabras libre/respetar.
Task 13: completa (commits e70407c..14cbf8e). TRES vueltas. La ventana de escritorio.
  Un TEST VACUO DE MI BRIEF: la URL se armaba con "127.0.0.1" hardcodeado y el test que verificaba "escucha
  sólo en localhost" comparaba contra el mismo literal que la construía. El implementador lo detectó mutando
  host a "0.0.0.0" y viendo que el test seguía verde. Ahora host y puerto salen de getsockname().
  DOS CRÍTICOS de seguridad en Puente.guardar(), los dos reproducidos por el revisor:
   1. SYMLINK: Path.resolve() sigue los enlaces, así que la autorización quedaba registrada contra el destino
      del enlace y la escritura lo atravesaba. Se sobrescribía un archivo que el usuario nunca eligió, sin
      ningún error. Arreglado: _clave() resuelve sólo el directorio contenedor y conserva el nombre final sin
      resolver, más un is_symlink() en el momento de escribir (contra un enlace plantado después de autorizar).
   2. HARD LINK: is_symlink() da False para un hard link. Peor que el symlink, porque un selector de archivos
      suele marcar visualmente un enlace simbólico y un hard link se ve idéntico a un archivo común -- el
      usuario no tiene forma de notarlo. Arreglado con st_nlink > 1, condicionado a no-Windows porque ahí el
      dato no es confiable.
  RESIDUAL ANOTADO EN EL CÓDIGO, a propósito: sigue siendo "chequear y después escribir", así que queda una
  ventana de carrera microscópica. Cerrarla exigiría O_NOFOLLOW y escribir por descriptor. La ventana que sí
  importaba, entre autorizar y guardar, está cerrada.
  SIN VERIFICAR, para el dueño: abrir la ventana a mano y recorrer la lista de 9 puntos del brief. Ningún
  agente puede ver la pantalla.
Task 14: completa (commits 14cbf8e..4a797f1). Empaquetado para Mac.
  Armó a la primera: --autotest sobre el paquete congelado salió ok sin tener que agregar NADA al .spec.
  Eso es mérito de la Task 2 (rutas.py) -- la clase de bug que ese módulo existe para impedir no apareció.
  PESO REAL MEDIDO: carpeta 106 MB, zip 56 MB. La spec estimaba 250-400 MB y 100-150 MB; esa estimación
  asumía un binario universal2 y éste es arm64 puro. Spec actualizada con los números reales.
  El log de PyInstaller avisó dos hidden-imports de scipy "not found" (scipy._lib.array_api_compat.numpy.fft
  y scipy.special._cdflib). No rompieron nada acá; son nombres atados a la versión de scipy, así que anotar
  por si reaparecen al armar el de Windows.
  SIN HACER, para el dueño: abrir dist/Nesting/Nesting a mano. Ningún agente puede ver la pantalla.
  FUERA DE ALCANCE, decisión del dueño: el .exe de Windows. PyInstaller no compila cruzado y este Mac es ARM.

=== LAS 14 TAREAS COMPLETAS === Falta la revisión final de toda la rama.

=== REVISIÓN FINAL DE LA RAMA === 12 hallazgos, 1 crítico. Los 7 accionables arreglados en 44db898.
  CRÍTICO: elegir un archivo nuevo NO reseteaba el trabajo anterior. Acomodabas A.dxf, elegías B.dxf, y el
    botón Guardar seguía habilitado apuntando al trabajo de A: bajaba el corte de A y lo ofrecía como
    "B_acomodado.dxf". Ese archivo va a una fresadora. Además la solapa Revisión mostraba los descartes de A
    creyendo que eran de B. Es el hueco exacto entre el flujo de archivo y el flujo de trabajo: nadie
    reseteaba el estado del trabajo al cambiar la fuente.
  IMPORTANTES: /api/analizar devolvía 500 "Internal Server Error" en inglés para los defectos de dibujo MÁS
    COMUNES (contorno abierto, contornos que se pisan, curva no plana), porque sólo atajaba ValueError y esas
    tres heredan de Exception pelado -- el MISMO archivo por /api/trabajos daba el mensaje bueno en español.
    Los avisos llegaban hasta la API y morían en un console.info que la ventana de pywebview no puede abrir,
    tirando por la borda la cadena que la Task 7 construyó a propósito. Y un material que desaparecía entre
    el pre-chequeo de la API y la lectura del hilo trabajador se reportaba como BUG DEL PROGRAMA, con
    traceback y un repr pelado de una clave de diccionario.
  MENORES arreglados: dos literales pegados sin espacio; POST/PUT/DELETE de materiales daban 500 crudo con
    el catálogo corrupto mientras GET daba el mensaje bueno; y un mensaje del motor mandaba a usar
    "--tol-cierre" en una pantalla donde el control se llama "Tolerancia de cierre" (se traduce en corredor.py
    para no romper la CLI, que sí tiene ese flag).
  MENORES ANOTADOS, NO ARREGLADOS: los descartes se serializan enteros y la interfaz sólo usa .length;
    resultado.aprovechamiento y resultado.segundos no se leen; el comentario de cabecera de app.js dice que
    nada sabe de escritorio y hay cuatro lugares que sí; POST /api/archivos/local es una capacidad de
    escritorio registrada sin condición en la API compartida; index.html carga Google Fonts con un <link>
    bloqueante en cada arranque; y --autotest nunca ejerce un acomodo, así que no toca el camino de
    scipy/rhino3dm que es donde estarían los bugs de empaquetado que dice atajar.
  PARA EL DUEÑO, sin resolver: tres commits al motor (998bb5b rhino_reader, 246d479 ai_reader, 46ad971
    dxf_writer) que no son ninguna de las 14 tareas y que ninguna revisión por tarea miró. Llevan la línea de
    coautoría de esta sesión. Verifiqué que NO debilitaron tests: las aserciones borradas contaban entidades
    Line y la representación cambió a Polyline, así que cambiar esas cuentas era obligatorio; las de reemplazo
    verifican vértices y coordenadas, y los tres commits suman 7 tests sin borrar ninguno.

=== RECORRIDA DEL FLUJO EN UN NAVEGADOR DE VERDAD (post-entrega) === 6 defectos, todos en la capa web.
  Método: servidor local + navegador embebido, con `window.pywebview.api` falsificado para ejercer las ramas
  de escritorio (las únicas que corre el usuario). Es la primera vez que este código se EJECUTA: los tests
  leen los archivos como texto y ninguno abre una página. Los seis salieron en una sola pasada.
  1. REPORTADO POR EL USUARIO: guardar el DXF no apagaba la bandera de "sin guardar". Elegir otro archivo
     avisaba que ibas a perder un acomodo que ya estaba escrito en la carpeta del usuario, y cerrar la
     ventana después de guardar también preguntaba. `terminado` decía "hay un resultado", no "hay un
     resultado en riesgo", y nadie llamaba marcar_sin_guardar(false) después de escribir. Ahora los dos
     caminos de guardado pasan por marcarGuardado().
  2. LAYOUT: `body { min-height: 100vh }` deja crecer la fila `1fr` de la grilla hasta el contenido. Medido:
     733 px de body en una ventana de 558. Lo que se va abajo del borde es la barra de acción entera --
     Acomodar, la barra de avance y Guardar DXF. Con el panel de opciones abierto en una ventana de 1100x720
     (la real) el usuario perdía de vista el avance de un trabajo de 9 minutos. `height` fija la cáscara y
     el panel scrollea solo, que para eso ya tenía overflow-y: auto.
  3. El link "· N descartes" -- que existe exactamente para ver CUÁLES se descartaron -- llevaba a un panel
     gris vacío. `mostrarImagen()` salía sin hacer nada porque las dos imágenes las dibuja el trabajo y
     todavía no hay ninguno. Ahora el lienzo dice por qué está vacío. NO resuelto: que el diagnóstico se
     pueda ver ANTES de acomodar, que es lo que el usuario pidió originalmente.
  4. Un typo en "Ángulos" abría un cartel de error CON TÍTULO Y SIN TEXTO: "9o" -> NaN -> JSON.stringify lo
     manda como null -> 422 de pydantic, que trae una LISTA, y el mensaje se armaba con
     `typeof detalle === "string" ? detalle : ""`. Dos arreglos: textoDeDetalle() para que ningún cartel
     salga vacío nunca, y validación de ángulos en la pantalla con el cartel debajo del campo.
  5. `tol-cierre` (min=0.001 step=0.01 value=0.1) y `resolucion` (min=0.1 step=0.5 value=2) nacían INVÁLIDOS:
     step se cuenta desde min, no desde cero. El navegador los marcaba mal antes de que el usuario tocara
     nada, con mensaje en inglés. step="any".
  6. Las casillas salían en el azul del sistema. accent-color: var(--acento).
  ANOTADO, NO ARREGLADO: "94 piezas" no se recalcula al cambiar de material, así que puede contradecir el
  "de 93" de la barra de avance cuando el material nuevo hace que un rectángulo coincida con el tamaño de
  la placa. Es honesto pero confunde.
  LECCIÓN: los cuatro bugs de app.js de las revisiones anteriores salieron de LEER el código; estos seis
  salieron de CORRERLO. Son clases distintas de defecto y ninguna de las dos sustituye a la otra.

=== LA REVISIÓN, ANTES DE ACOMODAR (pedido del usuario) ===
  `write_diagnostic` sólo necesita las piezas y los descartes, y `analizar()` ya calculaba las dos: la
  imagen se escribía únicamente en `acomodar()` por dónde estaba puesta la llamada, no por dependencias.
  Ahora `analizar()` también la deja, en `fuente.carpeta`, y se ve al segundo de elegir el archivo -- que
  es cuando sirve, porque es cuando el usuario todavía puede volver al original y corregirlo.
  SEAM: `Fuente` gana `carpeta`. Una subida ya vivía en una carpeta propia; una ruta local no se copia y
  no tenía ninguna. Dárselas a las dos es lo que deja al resto del programa sin preguntar de dónde vino el
  archivo, que es la regla entera de archivos.py.
  LAS DOS IMÁGENES NO SON LA MISMA: la del acomodo conoce el material, así que marca además los
  rectángulos del tamaño exacto de la placa (medido: 1594 px de alto contra 1568 para el mismo archivo).
  `rutaDeImagen()` prefiere la del trabajo cuando hay trabajo. Hay un test que fija ese orden, porque
  invertirlo deja al usuario mirando la versión incompleta justo después de acomodar.
  El fallo al escribir el PNG NO levanta: el análisis ya tiene su respuesta y perderla por un disco lleno
  sería peor que quedarse sin la imagen. Se cuenta como aviso y la ruta contesta 409.
  Ruta nueva GET /api/archivos/{fuente_id}/{nombre}, con `nombre` comparado contra un único valor exacto.
  Tests de que no sale ningún otro archivo por ahí y de que el middleware del token la cubre: es la capa
  que en la versión web queda expuesta a internet.
  SIGUE ANOTADO: "94 piezas" no se recalcula al cambiar de material. Pasar el material a /api/analizar lo
  arreglaría y de paso haría que la revisión previa marcara también el contorno de placa, pero acopla el
  análisis a la selección de material (habría que reanalizar en cada cambio). No se hizo.

=== CUATRO COSAS QUE REPORTÓ EL USUARIO MIRANDO LA VENTANA DE VERDAD ===
  1. El botón "Materiales" seguía visible dentro de la pantalla de materiales. La causa no era el olvido:
     "mostrar" vivía en app.js y "volver" en materiales.js, así que cada cosa que se apaga al entrar había
     que acordarse de prenderla en el otro archivo. Ahora las dos mitades son `mostrarPantalla()`, una sola
     función, y materiales.js llama a `mostrarPrincipal()`.
  2. LAYOUT ROTO AL VOLVER DE MATERIALES DESPUÉS DE REDIMENSIONAR. El navegador embebido NO lo reproduce.
     Hubo que escribir un arnés que maneja la ventana de pywebview de verdad (webview.evaluate_js +
     window.resize) y mide la geometría desde adentro de la página. Con eso se reprodujo al primer intento
     y se descartó la hipótesis obvia: NO era `100vh` -- el body siempre midió igual que la ventana.
     La causa medida: sin `grid-row` explícito, la fila que le toca a cada hijo depende de cuántos hermanos
     estén en display:none, y la pantalla de materiales oculta justo al del medio. Con materiales abierta,
     `.barra-accion` se corría a la fila `1fr` y pasaba de 76 px a 636. Queda tapada, así que no se ve;
     al volver, WKWebView no re-ubica y la pantalla principal queda en 0 px hasta que un resize fuerza el
     recálculo. Clavar las tres filas lo saca de raíz. Verificado con el mismo arnés: paso 4 pasa de
     `principal alto=0 / barra alto=816` a `principal alto=740 / barra top=796 alto=76`.
  3. webview.OPEN_DIALOG / SAVE_DIALOG deprecados -> webview.FileDialog.OPEN / .SAVE, y pywebview>=5 en
     pyproject. Importa más de lo que parece: en el paquete armado esa consola no se ve, así que el día que
     pywebview los saque nos enteraríamos por el diálogo de elegir archivo y el de guardar el DXF dejando
     de abrir. El test ignora los comentarios -- el comentario que explica por qué no se usan los nombres
     viejos los nombra, y la primera versión del test falló por eso.
  4. ZOOM EN LA REVISIÓN. El diagnóstico se dibuja a 1800 px y el panel mide menos de 300: al 20% que entra
     las medidas de cada descarte son ilegibles, justo cuando hay muchos (59 en el archivo que lo reportó).
     Botones, rueda anclada al cursor (error medido: 0 px en los dos ejes), doble click para 100%/ajustar,
     y arrastrar para mover.
     DOS BUGS DE CSS QUE APARECIERON AL PROBARLO, no al escribirlo:
     a) `justify-content: center` recorta el borde de arriba y de la izquierda cuando el contenido no
        entra, que es justo cuando hace falta llegar ahí. Se centra con `margin: auto`.
     b) El lienzo NO scrolleaba en horizontal: se ensanchaba. Una pista implícita de grilla es `auto`, y
        `auto` crece hasta el max-content: con la imagen al 100% la columna entera se estiraba a 1800 px y
        se llevaba puesta la ventana. `grid-template-columns: minmax(0, 1fr)` es la versión en grilla del
        `min-width: 0` de flex -- el mismo bug que ya había roto los campos Ancho/Alto.
  LECCIÓN: el arnés de la ventana real es la tercera clase de verificación de esta interfaz, después de
  leer el código y de correrlo en el navegador embebido. El bug 2 no era alcanzable por ninguna de las dos.

=== LA APP SE COLGABA AL CERRAR DESPUÉS DE ACOMODAR (reportado por el usuario) ===
  Abrazo mortal de manual, y la cadena entera se lee en el código de pywebview:
  - `window.events.closing = Event(self, True)` -> `should_lock=True` -> `Event.set()` ejecuta los
    handlers SINCRÓNICAMENTE en el hilo que lo disparó, en vez de tirarlos a un hilo nuevo (lo hace así
    porque necesita el valor de retorno para poder cancelar el cierre).
  - `cocoa.BrowserView.should_close()` -- o sea el hilo principal de Cocoa -- es quien lo dispara.
  - `cocoa.create_confirmation_dialog()` hace `AppHelper.callAfter(_confirm)` + `semaphore.acquire()`
    SIN timeout.
  Resultado: el hilo principal encola el dibujo del diálogo en su propio run loop y se queda esperando un
  semáforo que sólo se libera cuando ese dibujo corre. No corre nunca. Y sólo pasa con `hay_sin_guardar`
  en True, o sea después de acomodar y antes de guardar: exactamente como lo reportó el usuario.
  ARREGLO: `CierreSeguro`. El handler cancela ese cierre y devuelve enseguida (con eso el hilo principal
  queda libre), la pregunta va a un hilo aparte, y si el usuario acepta se llama `ventana.destroy()` a
  mano. Un `_confirmado` deja pasar el `closing` que dispara ese destroy.
  Vive afuera de `main()` para poder probarlo: los tests le inyectan `preguntar`, `cerrar` y `en_hilo`.
  El test que importa imita la FORMA del diálogo de pywebview (callAfter + semáforo) en vez de mockearlo,
  así que falla si alguien vuelve a preguntar desde el hilo que cierra.
  VERIFICADO EN LA VENTANA REAL, las dos direcciones, disparando `should_close` con `AppHelper.callAfter`
  para que corra en el hilo principal de verdad:
    handler viejo -> "el diálogo NO se pudo dibujar: el hilo principal está trabado" (y sólo escapó
                     porque el diálogo del arnés tiene timeout; el de pywebview no tiene).
    handler nuevo -> devuelve enseguida, el diálogo contesta, y `BrowserView.instances` queda en 0, o sea
                     que `ventana.destroy()` desde un hilo que no es el principal cierra de verdad.
  Este es el tercer bug seguido que sólo aparece en el hilo principal de Cocoa. El arnés dejó de ser un
  truco de una vez: es la única forma de ver esta clase de defecto.

=== EL ARNÉS DE LA VENTANA REAL PASÓ AL REPO: herramientas/ventana_real.py ===
  Tres bugs seguidos que sólo existen en el hilo principal de Cocoa (la barra de acción estirada, el
  cuelgue al cerrar, la columna de grilla estirada por la revisión ampliada) dejaron claro que no era un
  truco de una vez. Revisa layout y cierre, sale con 1 si encuentra algo, y lista los problemas en
  castellano. No corre en la suite: abre una ventana y necesita pantalla. No entra al paquete: el .spec
  sólo empaqueta materials.yaml y src/nesting_app/web.
  SU PROPIO CRITERIO ESTÁ PROBADO. Una herramienta de diagnóstico que dejó de detectar cosas se ve
  EXACTAMENTE IGUAL que una que no encuentra problemas -- es el modo de falla más caro que puede tener.
  `problemas_de_medida()` es aritmética pura, separada de la ventana, y sus tests usan los números que la
  herramienta midió de verdad antes y después de cada arreglo (principal en 0 con el pie en 816; body de
  733 en una ventana de 558; ancho de 2168). Verificado por mutación: sacar cualquiera de las tres
  comprobaciones, o aflojar el umbral de la barra, hace fallar los tests.
  EL CASO QUE HABÍA QUE ACERTAR: con materiales abierta la pantalla principal mide 0 de alto y ESO ESTÁ
  BIEN, está oculta. El bug es medir 0 estando visible. Sin esa distinción la herramienta daría una falsa
  alarma en cada corrida, y una herramienta que siempre se queja se deja de mirar. Tiene su test.
  La revisión de cierre es sólo macOS y se saltea diciéndolo, en vez de dar un falso verde.

=== REVISIÓN DE SEGURIDAD (pedida por el dueño) ===
Dos revisiones en paralelo: fuga de datos personales, y superficie de ataque del programa instalado.

UNA VULNERABILIDAD REAL, ARREGLADA (435f27f). Con el programa abierto, cualquier página que el usuario
visitara podía leerle archivos del disco. DNS rebinding: el atacante pone el TTL de su DNS en cero y
rebindea su dominio a 127.0.0.1; para el navegador sigue siendo el MISMO ORIGEN, así que lo deja leer las
respuestas. Pide `GET /`, que entrega el token en un <meta> sin pedir nada a cambio -- tiene que ser así,
es como arranca la interfaz --, y con ese token encadena POST /api/archivos/local, que acepta CUALQUIER
ruta del disco. Reproducido de punta a punta antes de arreglar: con `Host: evil.attacker.com` salió el
token y después un PNG de 37 KB con un dibujo privado. El puerto aleatorio no protege: son 65535.
  Lo corta el `Host`, que el JavaScript no puede falsificar. La cerradura envuelve a `_ConToken` y no al
  revés -- la página que entrega el token es lo que el atacante quiere leer --, y vive en desktop.py y no
  en api.py, porque "el único host válido es el local" es falso para la versión web.

LIMPIO Y VERIFICADO, NO SUPUESTO: cero XSS (se rastreó cada dato de archivo y catálogo hasta el DOM), cero
recorrido de rutas, el middleware del token no se esquiva (15 variantes de path), sin deserialización
insegura, y `Puente.guardar()` aguanta ADS, mayúsculas en FS insensibles, nombres reservados, UNC y \\?\.
Ningún archivo de diseño estuvo JAMÁS en la historia de git -- censo de todas las rutas de todos los
commits --, y el reflog prueba que la historia previa al filter-branch nunca se pusheó. Cero credenciales
en los 304 blobs. Sin telemetría.

QUEDA ABIERTO, SIN ARREGLAR:
  - Cualquier proceso local con el mismo usuario se lleva el token con un curl a `GET /` tras barrer
    puertos. El Host no lo tapa. Un proceso que corre como el usuario ya puede leer sus archivos sin esto;
    importa de verdad si hay OTRA cuenta en la máquina. El arreglo es no pasar el token por HTTP sino por
    el canal de pywebview, con coletazos en la versión web.
  - El binario está firmado sólo ad-hoc, sin hardened runtime, y la interfaz se relee del disco en cada
    pedido: otro admin de la máquina reescribe app.js y su código corre dentro de la ventana.

DECISIÓN DEL DUEÑO: NO se reescribe la historia. Su argumento, que es el bueno: el path `/Users/raulo` no
agrega nada que el repo no diga ya -- la cuenta es rauleoyarzun, el README y la licencia llevan su nombre.
Un path absoluto no es una credencial. Reescribir historia era el riesgo más alto de toda la jornada para
tapar lo de menor valor, y el filter-branch anterior de este mismo proyecto había borrado archivos del
disco además de sacarlos de git. El árbol de trabajo SÍ quedó limpio (07f8d1b), así que esto sólo afecta a
lo ya pusheado.
  LO QUE SIGUE EN LA HISTORIA Y ES DISTINTO EN NATURALEZA: las dos capturas viejas dibujan robot_raaulo.ai
  entero. No son fabricables a esa resolución, pero sí identificables. Si el repo se hace público alguna
  vez, hay que volver a mirarlo -- y ahí alcanza con reescribir esos dos blobs, que es mucho más chico.

## Plan de los globos de ayuda (2026-09-20)

Ledger aparte: `.superpowers/sdd/info-opciones/progress.md`

---

# Progreso — Densidad de acomodo y colisión exacta

Plan: docs/superpowers/plans/2026-09-20-densidad-y-colision-exacta.md
Modo: subagent-driven-development, CON git, en worktree
Rama: `worktree-densidad-colision-exacta`
Base de la rama: 1d32512 (el commit del plan)
Línea base de tests antes de empezar: **1007 passed**

Nota del controlador (pre-flight): la tarea 5 trae los cuerpos de sus tres
tests como `...` en el plan. Es un placeholder, o sea un defecto del plan
según el estándar de writing-plans. Resolución: el implementador de la
tarea 5 los escribe completos antes de tocar `packer.py`, y se le despacha
con un modelo capaz en vez del barato. No se bloquea el plan por esto.

## Tareas

Task 1: completa (commits 34e6d4d..adce827, revisión limpia).
  `layout_cost` devuelve `CostoLayout(placas, material_ultima, alto_ultima)`, un dataclass
  frozen con `order=True`. Los tres consumidores migrados a acceso por atributo:
  `packer.py` (_compact_last_sheet), `cli.py`, `corredor.py`. 1009 passed (1007 + 2 nuevos),
  verificado por el controlador aparte del informe del implementador.
  Menor pendiente p/revisión final: en `tests/engine/test_effort.py`, el comentario
  "gana en alto" de `test_el_costo_prefiere_dejar_menos_material_en_la_ultima_placa`
  exagera: los dos altos empatan en 100.0 y la asercion usa `<=`. Texto mio del plan,
  no del implementador. Arreglar la redaccion si alguien vuelve a tocar ese test.
Task 2: completa (commits 47e1b35..2677265, revisión limpia).
  `Resultado.material_ultima_placa_m2` llega al motor -> API -> ventana -> CLI. 1012 passed
  (1009 + 3), corrida por el controlador. El revisor verificó los dos riesgos nombrados:
  (a) la cifra SÍ llega a la pantalla (`app.js` la arma en el mismo innerHTML que el
      sobrante, y `.resultado strong` ya le da `tabular-nums`, por eso no hizo falta
      tocar index.html ni app.css);
  (b) `jobs.py`/`test_jobs.py` no son scope creep: `Resultado` vive en `jobs.py`, no en
      `corredor.py` como decía el plan. ERROR DEL PLAN, corregido por el implementador.
  Menor pendiente p/revisión final: `tests/app/test_web_javascript.py` sólo comprueba que
  las dos cifras aparecen en el fuente de app.js, no que salgan juntas en la misma línea
  renderizada. Un regex de proximidad lo fijaría mejor.
Task 3: completa (commits 76c9253..5e9dbee, revisión limpia tras un arreglo).
  Nuevo `src/nesting/engine/exact.py` con `ArbitroExacto`. 1018 passed + 1 del arreglo.
  DEFECTO DEL PLAN encontrado por el revisor y arreglado: el árbitro sólo comparaba
  `distance < sep - EPS`. Como `shapely.distance` da 0.0 tanto para "se tocan" como para
  "se superponen", con `sep = 0` (valor legal: `params.py` sólo rechaza sep < 0) la
  comparación es `0.0 < -1e-6`, siempre falsa, y el árbitro aceptaba superposiciones
  enormes. `verify.py` hace DOS chequeos: área de intersección y después distancia.
  Arreglo (5e9dbee): mismo doble chequeo, importando `OVERLAP_AREA_THRESHOLD_MM2` de
  `verify.py` en vez de duplicar el número. El revisor verificó el orden de los dos
  chequeos, el caso de caída-a-través con intersección despreciable, y que el prefiltro
  por caja no puede saltearse un par superpuesto.
  Menor pendiente p/revisión final: `EPS = 1e-6` sigue duplicado en `exact.py` en vez de
  importarse de `verify.py`, aunque el arreglo ya sentó el precedente con la otra
  constante y el propio docstring dice que "tienen que coincidir". Una línea.
Task 4: completa (commits 4cf85ab..788c7f9, revisión aprobada). 1021 passed (1019 + 2).
  La grilla propone con holgura optimista y `ArbitroExacto` dispone.
  RESULTADO MEDIDO sobre NESTING 2.ai: separación real 10.00 mm (antes 16.00), 2 placas,
  31/5, cero violaciones, 12.4 s. Los cuatro riesgos nombrados verificados por el revisor:
  dirección de redondeo de `radio_optimista` (floor, correcta), fallback conservador real
  y ejercitado por un test que comprueba el EFECTO (separación > 12), desviación de la
  banda de contacto justificada y documentada en el código, y `best_placement` sin efectos.
  Desviación deliberada del plan, con evidencia: la banda de contacto se queda sobre
  `clearance` y no sobre la holgura optimista. El plan decía lo contrario, pero eso rompe
  `test_a_small_part_is_nested_inside_a_big_hole` (la holgura fina se traga la zona de
  contacto). Medido y anotado en el docstring de `_banda_de_contacto`.

  >>> ENTRADA OBLIGATORIA PARA LA TASK 6 (recalibración):
      El peso `contact` está calibrado contra el motor conservador y AHORA CUESTA PIEZAS.
      Medido por el implementador sobre NESTING 2.ai: con `contact = 1.0` (el actual) da
      31/5; con `contact = 0` da 34/2. También costaba antes del cambio (29/7 con, 30/6 sin).
      No se tocó ningún peso: recalibrarlo es trabajo de la tarea 6, con el bench completo,
      cuidando `test_a_small_part_is_nested_inside_a_big_hole`, que es la capacidad que el
      término de contacto existe para sostener.

  MENORES PENDIENTES P/REVISIÓN FINAL (varios valen la pena, van en una sola tanda al final):
  (a) `tests/engine/raster/test_raster_oracle.py:312`: el test estrella usa
      `pytest.approx(10.0, abs=0.51)`, una banda de DOS lados, así que un layout con 9.5 mm
      de separación real -- una violación de verdad -- pasa el test que existe para probar
      la separación exacta. Tolerancia mía del plan. Arreglo: cota de un solo lado más una
      llamada a `verify(...)` en el mismo test.
  (b) `best_position` quedó muerto en producción: la rama conservadora reimplementa su
      argmax en línea (`oracle.py:337-339`). Duplicación y riesgo de deriva; quince
      aserciones de `test_scoring.py` ahora cuidan un envoltorio que el motor no usa.
  (c) La pasada conservadora corre aunque no pueda ayudar: `_buscar_con` devuelve `None`
      por dos motivos distintos (conjunto vacío vs presupuesto agotado) y sólo el segundo
      justifica el fallback. La instrumentación del implementador lo muestra: 48 de 48
      fallbacks del trabajo real fueron del tipo inútil, cada uno una correlación completa
      de placa de más.
  (d) La afirmación de "salida sin warnings" no está respaldada: las corridas usan
      `-p no:warnings`, que apaga el plugin. Instrucción mía. El controlador tiene que
      correr `pytest` pelado una vez antes de cerrar.
  (e) La desigualdad del superconjunto se cumple con IGUALDAD, no estrictamente, y el
      docstring la enuncia como si fuera estricta. Vale una frase.
  (f) El mismo efecto de separación fantasma sigue vigente CONTRA EL BORDE de la placa:
      el material queda hasta `margin + 2*INFLACION_MAX_PX*resolution` del borde físico
      aunque el árbitro lo aceptaría a `margin`. Fuera del alcance de la tarea, pero nada
      en el código lo anota.
  (g) Nits: `_mejores` recorre el arreglo entero por tanda; imports dentro de los cuerpos
      de dos tests.
Task 5: completa (commits 353177c..4bea902, aprobada tras un arreglo). 1024 passed + 1 del arreglo.
  DEFECTO DEL PLAN, grande, encontrado y demostrado por el implementador: el algoritmo que
  yo especifiqué era un NO-OP. `_pack_once` ya prueba cada pieza pendiente contra CADA placa
  (`for part in remaining`, y los fallos se acumulan en `still_pending`), y colocar sólo
  agrega material, así que volver a preguntarle a una placa congelada con la misma consulta
  golosa no puede recuperar nada jamás. Medido con mi código tal cual: 0 recuperaciones en
  45 escenarios al azar y 0 en el trabajo real. Verifiqué el argumento yo mismo contra el
  bucle: es correcto.
  Sustituto (mismo nombre, firma y punto de llamada): rompe la avaricia cambiando el ORDEN
  DE INSERCIÓN -- la placa anterior se rearma desde cero con la pieza pendiente primero, y
  se acepta sólo si no se cayó ninguna de las piezas originales. Esa condición de aceptación
  es lo que impide que `layout_cost` suba.
  RESULTADO MEDIDO sobre NESTING 2.ai: 32/4 (antes 31/5), 0 violaciones, material en la
  última placa 0.179 -> 0.143 m2. Es exactamente el disco que el usuario movió a mano.
  Arreglo (4bea902): la pasada era sorda -- hasta 24 s sin llamar al callback de progreso,
  o sea barra congelada y botón de cancelar muerto, contra el contrato que el propio módulo
  documenta con `Cancelado`. Se reenvía el `aviso` a `_pack_once` reusando `avisos_de` y el
  campo `compactando` que ya existían. Sin campos nuevos en `Avance`, sin tocar `nesting_app`.
  COSTO: el trabajo real pasó de 11.7 s a 35.8 s en `rapido` (3.1x). El costo es constante
  por `pack()`, así que se diluye en `normal`/`lento`. Un tope de 1 intento por placa lo
  bajaría a ~24 s a cambio de la mitad de la tasa de recuperación.
  Menores pendientes p/revisión final:
  (h) el docstring público de `pack()` sigue diciendo que `progreso` se llama "una vez más
      al entrar en la compactación final"; ahora se llama muchas veces más durante la
      recuperación. Una línea.
  (i) `_recuperar_de_la_ultima_placa` devuelve un `PackResult` nuevo mientras su vecina
      `_compact_last_sheet` muta el suyo en el lugar. Asimetría de estilo.
  (j) dos idiomas distintos para la misma guarda `progreso is None` a pocas líneas.

NOTA PARA LA TASK 6: el plan manda correr `bench/run_bench.py --resoluciones ... --esfuerzos ...`
  y esos flags NO EXISTEN. La herramienta correcta es `bench/calibrate.py`, que ya barre peso
  de contacto, resolución y esfuerzo, y toma sólo `--material` y `--copias`.
