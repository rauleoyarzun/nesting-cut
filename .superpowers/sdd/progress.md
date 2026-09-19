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
  EL ARCHIVO REAL DEL USUARIO ANDA DE PUNTA A PUNTA. bench/files/banqueta final raulo.ai, export genuino de
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
El proyecto se movio de /Users/raulo/cut-placement a /Users/raulo/Projects/cut-placement.
(El usuario escribio "Porjects"; use "Projects", que es el que existe y tiene sus otros proyectos.)
El venv NO se movio: tenia rutas absolutas grabadas en los shebangs de .venv/bin/* y en el .pth de la
instalacion editable. Se reconstruyo de cero en el destino.
Se descartaron, por regenerables: .venv, .pytest_cache, .coverage, __pycache__ y los .egg-info.
Verificado en la ubicacion nueva: 423 tests en verde; la CLI sobre banqueta final raulo.ai da el mismo
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
(medido: 1.1s contra 34s del acomodo completo sobre robot_raaulo.ai), y si la ruta del PNG esta mal el usuario
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
  robot_raaulo.ai : 3 descartes, 3 marcados. 1.1s.
  robot_raaulo.3dm: 9 descartes, 6 marcados (las 3 cotas de Rhino no tienen contorno en XY que marcar). 1.0s.
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
