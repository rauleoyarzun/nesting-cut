"""Contrato del JavaScript: que llame a las rutas que la API expone.

No corre un navegador -- eso quedó fuera de alcance a propósito. Verifica
que el archivo hable de las mismas rutas, campos e ids que el servidor y
la interfaz producen, que es la clase de desincronización que rompe la
pantalla en silencio: un endpoint que ya no se llama, un id mal tipeado
que hace que un botón no haga nada, un estado que el servidor manda y que
nadie contempla.
"""

import re

import pytest

from nesting_app import rutas


@pytest.fixture(scope="module")
def js():
    return (rutas.recurso("web") / "app.js").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def html():
    return (rutas.recurso("web") / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("ruta", [
    "/api/materiales", "/api/archivos", "/api/archivos/local",
    "/api/analizar", "/api/trabajos",
])
def test_usa_la_ruta_que_la_api_expone(js, ruta):
    assert ruta in js


def test_manda_el_token_en_cada_pedido(js):
    assert "X-Token" in js


def test_lee_el_token_del_meta(js):
    """`desktop.py` lo inyecta ahí al servir la página. En la web lo va a
    poner el servidor con la sesión: este código no cambia."""
    assert 'name="token"' in js or "'token'" in js


def test_leer_el_token_no_depende_de_estar_en_escritorio(js):
    """El meta de escritorio (`EN_ESCRITORIO`) y el del token son cosas
    separadas: si la lectura del token quedara enredada con esa rama, la
    web -- que nunca pone `meta[name="escritorio"]` -- se quedaría sin
    token."""
    linea_token = next(l for l in js.splitlines() if 'meta[name="token"]' in l)
    assert "EN_ESCRITORIO" not in linea_token
    assert "pywebview" not in linea_token


@pytest.mark.parametrize("estado", ["listo", "cancelado", "error", "corriendo", "pendiente"])
def test_contempla_cada_estado_de_un_trabajo(js, estado):
    assert f'"{estado}"' in js or f"'{estado}'" in js


def test_distingue_un_bug_del_programa_de_un_error_del_dibujo(js):
    """Son dos mensajes distintos: uno manda a corregir el archivo, el otro
    dice que el problema es nuestro y ofrece copiar el detalle."""
    assert "es_bug" in js


def test_el_bug_del_programa_ofrece_copiar_el_detalle_tecnico(js):
    """El cartel de error genérico sabe mostrar un `detalleTecnico`
    opcional; que la rama de `es_bug` se lo pase es lo que hace que el
    botón "Copiar detalle" aparezca sólo cuando corresponde."""
    indice = js.index("es_bug")
    contexto = js[indice:indice + 400]
    assert "detalle_tecnico" in contexto


def test_reacciona_a_que_falten_las_unidades(js):
    assert "faltan_unidades" in js


def test_pone_el_error_de_un_parametro_debajo_de_su_campo(js):
    assert "data-error-de" in js


def test_sondea_con_un_intervalo_razonable(js):
    """Los trabajos tardan de 34 s a 9 minutos. Sondear cada 50 ms sería
    quemar CPU al pedo; cada 5 s se sentiría trabado."""
    intervalos = [int(n) for n in re.findall(r"SONDEO_MS\s*=\s*(\d+)", js)]
    assert intervalos, "no se encontró SONDEO_MS"
    assert 200 <= intervalos[0] <= 1000


def test_la_barra_de_avance_no_retrocede_al_empezar_un_intento_nuevo(js):
    """`nesting/engine/packer.py` reinicia el conteo de piezas ubicadas en
    cada intento nuevo -- a propósito, según su propio docstring de
    `Avance`. Una barra armada sólo con ubicadas/totales retrocedería justo
    ahí, y una barra que retrocede es peor que no tener barra: por eso el
    cálculo que fija el ancho tiene que mirar también el intento."""
    indice = js.index('"barra-avance"')
    contexto = js[max(0, indice - 400):indice]
    assert "intento" in contexto and "ubicadas" in contexto


def test_expone_su_estado_para_la_pantalla_de_materiales(js):
    assert "window.__nesting" in js


def test_expone_mostrar_materiales_para_que_la_tarea_siguiente_se_enganche(js):
    """La tabla, el alta y el borrado son de `materiales.js`; este archivo
    sólo tiene que saber mostrar y ocultar la pantalla para que esa otra
    pieza se pueda enganchar."""
    indice = js.index("window.__nesting")
    contexto = js[indice:indice + 300]
    assert "mostrarMateriales" in contexto


def test_registrar_limpia_el_trabajo_anterior(js):
    """El bug real: acomodás A, elegís B, y si `registrar()` no limpia
    `estado.trabajoId` (y `terminado`), la solapa Revisión sigue pidiendo el
    diagnóstico de A, el resultado sigue mostrando las placas de A, y el
    botón Guardar -- que se habilita mirando `terminado` -- sigue apuntando
    a `/api/trabajos/<id-de-A>/salida.dxf`. Ese archivo va a una fresadora.

    Verificación manual de que este test puede fallar de verdad: comentando
    la línea `estado.trabajoId = null;` dentro de `registrar()`, este test
    falla (y el `assert` de abajo es justo el que lo agarra)."""
    inicio = js.index("async function registrar(")
    fin = js.index("async function analizar(")
    cuerpo = js[inicio:fin]
    assert "estado.trabajoId = null" in cuerpo, (
        "registrar() ya no limpia estado.trabajoId: el trabajo del archivo "
        "anterior queda vivo para el archivo nuevo"
    )
    assert "estado.terminado = false" in cuerpo, (
        "registrar() ya no limpia estado.terminado: el botón Guardar puede "
        "quedar habilitado apuntando al trabajo anterior"
    )


def test_un_cartel_de_error_nunca_sale_vacio(js):
    """Un 422 de pydantic trae una lista de campos, no un texto. Mientras el
    mensaje se armaba con `typeof detalle === "string" ? detalle : ""`, un
    typo en Ángulos abría un cartel con título y sin una sola palabra
    adentro -- el usuario no tenía forma de saber qué corregir."""
    assert 'typeof detalle === "string" ? detalle : ""' not in js, (
        "volvió el armado que tira el detalle no-texto a la basura"
    )
    inicio = js.index("function textoDeDetalle(")
    cuerpo = js[inicio:js.index("\n}", inicio)]
    assert "Array.isArray(detalle)" in cuerpo, (
        "textoDeDetalle no contempla la lista de errores de pydantic, que es "
        "justo la forma que tiene un 422"
    )
    assert re.search(r"new Error\(\s*textoDeDetalle\(detalle\)\s*\|\|", js), (
        "el mensaje del error no pasa por textoDeDetalle, o no tiene respaldo "
        "para cuando el cuerpo no trae nada"
    )


def test_los_angulos_se_validan_antes_de_mandarlos(js):
    """Es el único parámetro de texto libre. Un "9o" daba NaN, JSON.stringify
    lo mandaba como null y el servidor contestaba con el 422 crudo. Se corta
    en la pantalla, con el mismo cartel debajo del campo que los demás."""
    inicio = js.index('$("btn-acomodar").onclick')
    cuerpo = js[inicio:js.index('$("btn-cancelar").onclick')]
    assert "angulosValidos()" in cuerpo, (
        "acomodar ya no chequea los ángulos: un typo vuelve a viajar como "
        "null al servidor"
    )
    assert re.search(r'marcarCampo\(\s*\n?\s*"angulos"', cuerpo), (
        "el error de ángulos no se muestra debajo del campo"
    )


def test_el_campo_de_angulos_tiene_donde_mostrar_su_error(html):
    """`marcarCampo` busca `[data-error-de=...]`; si no está, cae al cartel
    modal, que para un typo en un campo es desproporcionado."""
    assert 'data-error-de="angulos"' in html


def test_el_zoom_arranca_ajustado_en_cada_imagen(js):
    """Heredar el zoom de la imagen anterior deja al usuario mirando una
    esquina de un dibujo distinto sin entender qué está viendo."""
    inicio = js.index("async function mostrarImagen(")
    cuerpo = js[inicio:js.index("// --- zoom", inicio)]
    assert "zoom = null" in cuerpo, (
        "mostrarImagen ya no reinicia el zoom al cargar una imagen nueva"
    )


def test_la_rueda_acerca_donde_esta_el_cursor(js):
    """Si el zoom se va siempre al centro, perseguir un descarte concreto en
    un plano de 1800 px se vuelve un juego de paciencia."""
    inicio = js.index("function acercar(")
    cuerpo = js[inicio:js.index("\nfunction centroDelLienzo", inicio)]
    assert "getBoundingClientRect" in cuerpo and "scrollLeft" in cuerpo, (
        "acercar() ya no corrige el scroll, así que el punto bajo el cursor "
        "se va de lugar al ampliar"
    )
    assert re.search(r'addEventListener\("wheel"', js)


def test_los_controles_de_zoom_se_apagan_cuando_no_hay_imagen(js):
    """Quedarían prendidos sobre un texto, ofreciendo ampliar la nada.

    Dos invariantes, una por cada forma de dejar el lienzo sin imagen:
    escribir texto pasa siempre por `mensajeEnLienzo`, y vaciarlo del todo
    (que es lo que hace `registrar()`) avisa por su cuenta."""
    inicio = js.index("function aplicarZoom(")
    cuerpo = js[inicio:js.index("\n}", inicio)]
    assert 'classList.toggle("oculto", !img)' in cuerpo

    assert js.count('$("lienzo").textContent =') == 1, (
        "hay otro lugar que escribe texto en el lienzo sin pasar por "
        "mensajeEnLienzo, y deja los controles de zoom prendidos"
    )
    registrar = js[js.index("async function registrar("):js.index("async function analizar(")]
    assert "aplicarZoom()" in registrar, (
        "registrar() vacía el lienzo y no refresca el zoom: los controles "
        "quedan prendidos después de elegir otro archivo"
    )


def test_la_revision_se_puede_ver_antes_de_acomodar(js):
    """Es para lo que el usuario pidió esta imagen: saber CUÁLES son los dos
    que se descartaron, en el segundo que tarda el análisis, y no después de
    comprometerse a un acomodo de nueve minutos. Mientras la única ruta era
    la del trabajo, apretar "· 2 descartes" no mostraba nada."""
    inicio = js.index("function rutaDeImagen(")
    cuerpo = js[inicio:js.index("\n}", inicio)]
    assert "/api/archivos/${estado.fuenteId}/${nombre}" in cuerpo, (
        "la revisión volvió a depender de que exista un trabajo"
    )


def test_el_cambio_de_pantalla_vive_en_un_solo_lugar(js):
    """Cuando "mostrar" estaba en app.js y "volver" en materiales.js, cada
    cosa que se apagaba al entrar había que acordarse de prenderla en el otro
    archivo. No pasó: el botón que abre el catálogo seguía visible adentro de
    la pantalla de materiales, ofreciendo ir a donde el usuario ya estaba.
    Hoy ese botón está adentro de la pantalla principal, así que se apaga con
    ella: son dos cosas que apagar, y las dos se apagan acá."""
    inicio = js.index("function mostrarPantalla(")
    cuerpo = js[inicio:js.index("\n}", inicio)]
    for id_ in ("pantalla-principal", "pantalla-materiales"):
        assert id_ in cuerpo, f"mostrarPantalla ya no se ocupa de {id_}"
    assert cuerpo.count("classList.toggle") == 2, (
        "alguna mitad del cambio de pantalla volvió a hacerse por afuera, "
        "que es como se desincronizan"
    )
    assert "mostrarPrincipal" in js


def test_la_revision_del_trabajo_le_gana_a_la_del_analisis(js):
    """Son dos dibujos distintos: el del acomodo conoce el material, así que
    marca además los rectángulos del tamaño exacto de la placa. Si el orden
    se invierte, después de acomodar se sigue viendo la versión incompleta."""
    inicio = js.index("function rutaDeImagen(")
    cuerpo = js[inicio:js.index("\n}", inicio)]
    assert cuerpo.index("/api/trabajos/") < cuerpo.index("/api/archivos/"), (
        "la ruta del análisis se consulta antes que la del trabajo"
    )


def test_el_lienzo_explica_por_que_esta_vacio(js):
    """La previsualización es el resultado de un acomodo, así que antes del
    primero no existe. Sin texto el lienzo queda gris y mudo, y el usuario no
    tiene forma de distinguir "no hay nada todavía" de "se colgó"."""
    inicio = js.index("async function mostrarImagen(")
    cuerpo = js[inicio:js.index("const miPedido", inicio)]
    assert "Todavía no hay nada acomodado" in cuerpo, (
        "el lienzo vuelve a quedarse en blanco cuando no hay ninguna imagen"
    )
    assert "Elegí un archivo" in cuerpo, (
        "sin archivo elegido el lienzo tampoco dice nada"
    )


def test_guardar_el_dxf_deja_de_considerarlo_en_riesgo(js):
    """El bug que reportó el usuario: guardaba el DXF, elegía otro archivo y
    el programa le avisaba que iba a perder el acomodo -- que ya estaba
    escrito en su carpeta. El mismo descuido hacía que cerrar la ventana
    después de guardar también preguntara.

    La causa: los dos caminos de guardado escribían el archivo y nadie
    apagaba la bandera. Este test fija que los dos pasen por el mismo lugar
    y que ese lugar apague las dos alarmas (la de elegir otro archivo y la
    que mira el puente de escritorio al cerrar)."""
    inicio = js.index("function marcarGuardado(")
    cuerpo = js[inicio:js.index("\n}", inicio)]
    assert "estado.guardado = true" in cuerpo
    assert "marcar_sin_guardar(false)" in cuerpo, (
        "marcarGuardado() no le avisa al puente: cerrar la ventana después "
        "de guardar va a seguir preguntando por un archivo que ya está en "
        "disco"
    )

    guardar = js[js.index('$("btn-guardar").onclick'):]
    assert guardar.count("marcarGuardado()") == 2, (
        "los dos caminos de guardado (diálogo nativo y descarga del "
        "navegador) tienen que marcar el acomodo a salvo; hay "
        f"{guardar.count('marcarGuardado()')}"
    )


def test_el_cartel_de_perder_el_acomodo_solo_sale_si_no_se_guardo(js):
    """`terminado` dice que hay un resultado, no que esté en riesgo. Si la
    condición mira sólo eso, el cartel sale igual después de guardar."""
    inicio = js.index("async function registrar(")
    cuerpo = js[inicio:js.index("async function analizar(")]
    assert re.search(r"if\s*\(\s*estado\.terminado\s*&&\s*!estado\.guardado\s*\)", cuerpo), (
        "la condición del confirm() no mira estado.guardado: el usuario que "
        "ya guardó va a ver igual el cartel de que va a perder el trabajo"
    )
    assert "estado.guardado = false" in cuerpo, (
        "registrar() no limpia estado.guardado: el archivo nuevo arranca "
        "considerándose guardado y su acomodo se puede perder en silencio"
    )


def test_registrar_deja_el_boton_guardar_deshabilitado(js):
    """Aunque `trabajoId` se limpie, si el botón Guardar no se deshabilita
    de forma explícita puede quedar habilitado por un estado anterior (por
    ejemplo si `corriendo()` no se llamó a tiempo). Es la última línea de
    defensa del bug crítico: aunque todo lo demás falle, Guardar no tiene
    que poder apretarse para un archivo que la pantalla ya cambió."""
    inicio = js.index("async function registrar(")
    fin = js.index("async function analizar(")
    cuerpo = js[inicio:fin]
    assert re.search(r'"btn-guardar"\)\.disabled\s*=\s*true', cuerpo)


def test_los_avisos_del_analisis_se_muestran_en_la_interfaz(js):
    """Antes, `analisis.avisos` no se leía en absoluto: el aviso del
    rectángulo del tamaño de la placa no tiene ningún otro lugar donde
    aparecer que este camino."""
    assert re.search(r"mostrarAvisos\(\s*analisis\.avisos\s*\)", js)


def test_los_avisos_del_trabajo_se_muestran_al_terminar_y_al_fallar(js):
    """Antes, `t.avisos` en el camino de éxito sólo llegaba a un
    `console.info` (que la ventana de pywebview no puede abrir), y en el
    camino de error no se leía en absoluto -- pese a que son, según el
    propio comentario del código, "la explicación de por qué no quedó
    nada"."""
    ocurrencias = re.findall(r"mostrarAvisos\(\s*t\.avisos\s*\)", js)
    assert len(ocurrencias) >= 2, (
        f"esperaba que t.avisos se mostrara al terminar bien y al fallar, "
        f"se encontraron {len(ocurrencias)} veces"
    )


def test_los_avisos_no_terminan_solo_en_console_info(js):
    assert not re.search(r"console\.info\([^)]*aviso", js, re.IGNORECASE)


def test_no_asigna_src_o_href_con_una_ruta_de_api_directa(js):
    """`<img>` y `<a download>` son pedidos nativos del navegador: no pueden
    llevar el header `X-Token`, y el middleware de la API rechaza con 401
    todo lo que no lo traiga. El archivo tiene que traer la imagen o el DXF
    con `api()` y asignar `.src`/`.href` a un blob local (`createObjectURL`).

    Un regex que sólo busca la ruta pegada al `=` (`img.src = "/api/..."`)
    no agarra la otra forma del mismo bug: una variable armada antes con la
    ruta y usada después (`const url = \`/api/...\`; a.href = url;`, que fue
    el bug real del botón "Guardar DXF"). Por eso esta prueba verifica lo
    positivo en vez de lo negativo: toda asignación a `.src`/`.href` en el
    archivo tiene que resolver, a lo sumo una variable de por medio, a un
    `createObjectURL`.

    Alcance: sigue un solo nivel de indirección (la variable asignada
    directamente a `.src`/`.href`, y si esa variable viene de otra
    asignación simple, esa asignación) y ubica la declaración por posición
    en el texto del archivo, no por alcance léxico real. No sigue cadenas
    más largas ni funciones que devuelvan la URL. Alcanza para este
    archivo, donde `mostrarImagen()` y el guardado del DXF asignan la URL a
    lo sumo con una variable de por medio."""
    # Forma 1: la ruta pegada al `=`.
    assert not re.search(r'\.(?:src|href)\s*=\s*(?:`|["\'])?/api/', js)

    # Forma 2: una variable de por medio. Para cada `algo.src = X;` /
    # `algo.href = X;` con X un identificador, alguna asignación a X antes
    # de ese punto -- directamente, o con un solo salto más -- tiene que
    # venir de `createObjectURL`.
    def valor_previo(variable, antes_de):
        """La asignación a `variable` más cercana (hacia atrás) antes de la
        posición `antes_de`, o None si no hay ninguna."""
        asignaciones = [
            m
            for m in re.finditer(
                rf'\b{re.escape(variable)}\b\s*=\s*([^=][^;]*);', js
            )
            if m.start() < antes_de
        ]
        return asignaciones[-1] if asignaciones else None

    usos = list(re.finditer(r'\.(?:src|href)\s*=\s*([A-Za-z_$][\w$]*)\s*;', js))
    assert usos, "no se encontró ninguna asignación a .src/.href para revisar"

    for uso in usos:
        variable = uso.group(1)
        paso1 = valor_previo(variable, uso.start())
        assert paso1, f"no se encontró de dónde sale `{variable}` (usada en {uso.group(0)!r})"
        valor = paso1.group(1).strip()
        if "createObjectURL" not in valor:
            identificador = re.fullmatch(r'[A-Za-z_$][\w$]*', valor)
            paso2 = identificador and valor_previo(valor, paso1.start())
            valor = paso2.group(1).strip() if paso2 else valor
        assert "createObjectURL" in valor, (
            f"`{variable}` se asigna a .src/.href pero no viene de "
            f"createObjectURL (llega a `{valor}`)"
        )


def test_usa_createobjecturl_y_lo_libera_con_revokeobjecturl(js):
    """Cada blob que se crea para una imagen o una descarga tiene que
    liberarse: si no, cambiar de solapa muchas veces deja blobs retenidos
    en memoria mientras la ventana esté abierta."""
    assert "createObjectURL" in js
    assert "revokeObjectURL" in js


def _ids_que_busca(js):
    """Todo id que el archivo le pasa a `$(...)`.

    Cubre la forma directa, `$("id")`, y la condicional que usa
    `materiales.js` para elegir un radio button según el estado del
    material, `$(condición ? "id-a" : "id-b")`: sin esto, los dos ids de
    adentro del ternario no entraban al conjunto que se compara contra
    `index.html`, que es exactamente el punto ciego que esta batería
    existe para atajar (un id mal tipeado ahí quedaría en verde). No cubre
    un id armado con un template literal (`` $(`algo-${x}`) ``) ni uno que
    salga de una variable o de una llamada a función: `materiales.js` y
    `app.js` no usan esas formas hoy."""
    directos = re.findall(r'\$\("([^"]+)"\)', js)
    del_ternario = re.findall(r'\$\([^()]*\?\s*"([^"]+)"\s*:\s*"([^"]+)"\)', js)
    return set(directos) | {id_ for par in del_ternario for id_ in par}


def test_todo_id_que_busca_el_js_existe_en_el_html(js, html):
    """Un id que `$("...")` busca y no está en `index.html` no falla en
    ningún lado: el botón correspondiente simplemente se queda mudo, y
    nadie se entera hasta que alguien lo aprieta. Es el error más probable
    de este archivo, y el más fácil de atajar comparando los dos lados."""
    ids_del_html = set(re.findall(r'id="([^"]+)"', html))
    ids_que_busca_el_js = _ids_que_busca(js)
    faltantes = ids_que_busca_el_js - ids_del_html
    assert not faltantes, f"ids que $() busca y no están en index.html: {faltantes}"


@pytest.fixture(scope="module")
def js_materiales():
    return (rutas.recurso("web") / "materiales.js").read_text(encoding="utf-8")


def test_materiales_usa_los_cuatro_verbos(js_materiales):
    """El alta y el restaurar van por `postJson`, el helper de app.js que ya
    envuelve todo POST con JSON del resto de la interfaz -- por eso acá no se
    busca el string "POST" literal, que nunca aparece si se usa ese helper
    en vez de repetir a mano lo que ya hace."""
    assert "postJson" in js_materiales
    for verbo in ("PUT", "DELETE"):
        assert verbo in js_materiales
    assert "/api/materiales/restaurar" in js_materiales


def test_materiales_pide_confirmacion_antes_de_borrar(js_materiales):
    """Borrar un material que se usa en trabajos anteriores no se deshace."""
    assert "confirm" in js_materiales


def test_materiales_muestra_la_veta_en_palabras(js_materiales):
    """La interfaz nunca muestra grados: nadie sabe qué significa 5."""
    assert "libre" in js_materiales and "respetar" in js_materiales


def test_materiales_refresca_el_desplegable_de_la_pantalla_principal(js_materiales):
    """Agregar un material y no verlo en la lista de al lado haría pensar
    que no se guardó."""
    assert "refrescarMateriales" in js_materiales


def test_todo_id_que_busca_materiales_js_existe_en_el_html(js_materiales, html):
    """El mismo contrato que `test_todo_id_que_busca_el_js_existe_en_el_html`
    verifica para `app.js`, pero para `materiales.js`: un id mal tipeado acá
    deja un botón mudo de la misma forma. `materiales.js` es justamente el
    archivo que elige un id con un ternario (`$(m.veta === "libre" ?
    "m-veta-libre" : "m-veta-respetar")`), así que usa la misma extracción
    que ya contempla esa forma -- ver el docstring de `_ids_que_busca`."""
    ids_del_html = set(re.findall(r'id="([^"]+)"', html))
    ids_que_busca_el_js = _ids_que_busca(js_materiales)
    faltantes = ids_que_busca_el_js - ids_del_html
    assert not faltantes, f"ids que $() busca y no están en index.html: {faltantes}"


def test_ningun_dato_del_material_se_interpola_en_un_innerhtml(js_materiales):
    """El bug que esta revisión encontró: `dibujarTabla()` armaba la fila
    con `fila.innerHTML = `<td>${m.nombre}</td>` + ...`, y `m.nombre` es
    texto libre que el usuario tipea y que vuelve del catálogo guardado
    (`materials.yaml`). Un nombre como `<img src=x onerror=...>` quedaba
    persistente: se ejecutaba cada vez que alguien abría esta pantalla, no
    sólo para quien lo escribió -- y en la versión web el catálogo puede
    ser compartido entre usuarios.

    Cubre: que ningún campo de `m` (`${m.algo}`) aparezca dentro del texto
    de una asignación a `.innerHTML` (buscando desde `.innerHTML =` hasta
    el primer `;`, con `re.DOTALL` para plantillas de varias líneas). No
    cubre: una interpolación armada en una variable aparte y asignada a
    `innerHTML` recién en la statement siguiente (la misma clase de
    indirección que la Forma 2 de
    `test_no_asigna_src_o_href_con_una_ruta_de_api_directa` persigue para
    `.src`/`.href`; acá no hace falta ese segundo paso porque hoy no hay
    ningún caso así), ni `insertAdjacentHTML`, ni el caso legítimo de la
    insignia de veta: ese campo no es texto libre (la API sólo acepta
    "libre" o "respetar") y el archivo lo copia a una variable propia
    (`veta`) antes de interpolarlo, así que no matchea `${m.`.

    Verificación manual de que este test puede fallar de verdad: si en
    `dibujarTabla()` se vuelve a escribir `celdaNombre.innerHTML =
    `${m.nombre}`` en vez de `celdaNombre.textContent = m.nombre`, este
    test detecta el `${m.nombre}` adentro de la asignación y falla."""
    asignaciones = re.findall(r"\.innerHTML\s*\+?=\s*[^;]*;", js_materiales, re.DOTALL)
    assert asignaciones, "no se encontró ninguna asignación a innerHTML para revisar"
    sospechosas = [a for a in asignaciones if "${m." in a]
    assert not sospechosas, (
        f"interpola un campo de un material en un innerHTML: {sospechosas}"
    )


# --- Lo que rompió la pantalla de materiales la primera vez que se abrió ------


def _sin_comentarios_ni_textos(js: str) -> str:
    """Reemplaza comentarios y literales de texto por espacios.

    Deja las llaves y los saltos de línea donde estaban, que es lo único que
    le importa al escaneo de abajo. Se hace a mano porque Python no trae un
    analizador de JavaScript y sumar uno por esto sería más máquina que
    problema.
    """
    salida = []
    i, n = 0, len(js)
    while i < n:
        c = js[i]
        par = js[i : i + 2]
        if par == "//":
            fin = js.find("\n", i)
            fin = n if fin == -1 else fin
            salida.append(" " * (fin - i))
            i = fin
        elif par == "/*":
            fin = js.find("*/", i + 2)
            fin = n if fin == -1 else fin + 2
            salida.append("".join(ch if ch == "\n" else " " for ch in js[i:fin]))
            i = fin
        elif c in "\"'`":
            cierre, j = c, i + 1
            while j < n and js[j] != cierre:
                j += 2 if js[j] == "\\" else 1
            j = min(j + 1, n)
            salida.append("".join(ch if ch == "\n" else " " for ch in js[i:j]))
            i = j
        else:
            salida.append(c)
            i += 1
    return "".join(salida)


def _declaraciones_globales(js: str) -> set[str]:
    """Los nombres que el archivo declara en el ámbito de más afuera."""
    limpio = _sin_comentarios_ni_textos(js)
    nombres: set[str] = set()
    profundidad = 0
    for linea in limpio.split("\n"):
        if profundidad == 0:
            hallazgo = re.match(
                r"\s*(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)", linea
            )
            if hallazgo:
                nombres.add(hallazgo.group(1))
            destructurado = re.match(r"\s*(?:const|let|var)\s*\{([^}]*)\}", linea)
            if destructurado:
                for parte in destructurado.group(1).split(","):
                    nombre = parte.split(":")[-1].strip()
                    if nombre:
                        nombres.add(nombre)
        profundidad += linea.count("{") + linea.count("(") - linea.count("}") - linea.count(")")
    return nombres



# --- los globos de ayuda ---------------------------------------------------

CLAVES_CON_GLOBO = [
    "archivo", "material", "sep", "borde", "copias", "esfuerzo",
    "angulos", "tol-cierre", "resolucion", "espejo",
]


@pytest.fixture(scope="module")
def js_info():
    return (rutas.recurso("web") / "info.js").read_text(encoding="utf-8")


def claves_y_textos(js_info: str) -> dict[str, str]:
    """El literal `TEXTOS` de `info.js`, leído como diccionario.

    Leerlo con una expresión regular y no evaluarlo es a propósito: el test
    no necesita un intérprete de JavaScript, necesita saber qué claves hay y
    qué dice cada una. Por eso el literal tiene todas las claves entre
    comillas y un par clave/valor por línea -- es un formato que se parsea
    en cuatro líneas, y el test que sigue lo obliga a seguir siéndolo.
    """
    cuerpo = js_info[js_info.index("const TEXTOS = {"):]
    cuerpo = cuerpo[:cuerpo.index("\n};")]
    return {
        m.group(1): m.group(2).replace('\\"', '"')
        for m in re.finditer(r'^\s*"([^"]+)":\s*"((?:[^"\\]|\\.)*)"', cuerpo, re.M)
    }


def test_estan_las_diez_claves_y_ninguna_de_mas(js_info):
    assert sorted(claves_y_textos(js_info)) == sorted(CLAVES_CON_GLOBO)


@pytest.mark.parametrize("clave", CLAVES_CON_GLOBO)
def test_el_texto_del_globo_dice_algo(js_info, clave):
    assert claves_y_textos(js_info)[clave].strip()


@pytest.mark.parametrize("clave", CLAVES_CON_GLOBO)
def test_el_texto_del_globo_entra_en_un_globo(js_info, clave):
    """Son dos o tres oraciones al costado de un campo, no un párrafo. A
    partir de acá el globo empieza a taparle la pantalla al que lo abrió."""
    texto = claves_y_textos(js_info)[clave]
    assert len(texto) <= 300, f"{clave}: {len(texto)} caracteres"


def test_la_pagina_carga_info_js(html):
    assert '<script src="info.js">' in html


def test_info_js_va_entero_adentro_de_una_iife(js_info):
    """Ver el test de nombres globales de más abajo: sin la IIFE, cualquier
    nombre que `app.js` ya haya declarado mata este archivo entero."""
    assert "(() => {" in js_info and "})();" in js_info


@pytest.mark.parametrize("a,b", [
    ("app", "materiales"), ("app", "info"), ("materiales", "info"),
])
def test_ningun_script_declara_un_nombre_que_otro_ya_declaro(a, b):
    """Los `<script>` clásicos comparten el ámbito global.

    Declarar en `materiales.js` un `const` que `app.js` ya declaró es un
    SyntaxError, y no falla la línea: **falla el archivo entero** antes de
    registrar un solo handler. Pasó de verdad la primera vez que se abrió la
    pantalla: `materiales.js` hacía `const { apiJson, ... } = window.__nesting`
    y `app.js` ya tenía `const apiJson`. La pantalla abría --ese botón lo
    registra app.js-- pero no andaban ni "Volver" ni "Cancelar" ni aparecía
    ningún material, y la consola de una ventana de pywebview no se puede
    abrir para ver el error.

    El arreglo fue envolver los archivos de más en una IIFE. Este test existe
    para que nadie la saque sin enterarse, y se parametriza para que sumar un
    cuarto archivo sea agregar un par acá.
    """
    leer = lambda n: (rutas.recurso("web") / f"{n}.js").read_text(encoding="utf-8")
    chocan = _declaraciones_globales(leer(a)) & _declaraciones_globales(leer(b))

    assert not chocan, (
        f"{a}.js y {b}.js declaran los mismos nombres globales: {sorted(chocan)}. "
        "Dos <script> clásicos comparten ámbito, así que eso es un SyntaxError "
        "que mata el segundo archivo entero."
    )


def test_cada_boton_del_html_tiene_su_texto_y_al_reves(html, js_info):
    del_html = set(re.findall(r'data-info="([^"]+)"', html))
    del_js = set(claves_y_textos(js_info))

    assert del_html == del_js, (
        f"sólo en el HTML: {sorted(del_html - del_js)}; "
        f"sólo en info.js: {sorted(del_js - del_html)}"
    )


def test_el_globo_se_cierra_de_las_cuatro_formas(js_info):
    """Un globo que sólo cierra con el mismo botón queda tapando el panel en
    cuanto el usuario sigue trabajando. Escape y el clic afuera son lo que
    todo el mundo prueba; el scroll y el resize son los que lo dejarían
    flotando lejos del campo que explica, porque está posicionado en fijo
    contra coordenadas de pantalla."""
    for señal in ('"Escape"', '"scroll"', '"resize"', '"click"'):
        assert señal in js_info, f"info.js no contempla {señal}"


def test_el_scroll_se_escucha_en_captura(js_info):
    """El que scrollea es `.panel-opciones`, no la ventana, y un evento de
    scroll de un elemento no burbujea hasta document. En captura sí pasa por
    ahí. Sin el `true` el globo se queda flotando mientras el campo se va."""
    assert re.search(r'addEventListener\(\s*"scroll".*,\s*true\s*\)', js_info), (
        "el scroll no se escucha en la fase de captura"
    )


def test_el_globo_se_ubica_contra_el_boton(js_info):
    """Si no lee el rect del botón, el globo sale siempre en el mismo lado
    de la pantalla y no se sabe de qué campo habla."""
    assert "getBoundingClientRect" in js_info


def test_el_globo_no_se_sale_de_la_ventana(js_info):
    """El panel mide 336 px y la ventana no siempre es ancha: si no se mide
    contra `innerWidth` / `innerHeight`, el globo de las opciones avanzadas
    --que están abajo de todo-- sale cortado por el borde."""
    assert "innerWidth" in js_info and "innerHeight" in js_info


def test_el_boton_anuncia_si_esta_abierto(js_info):
    """`aria-expanded` es lo único que le dice a un lector de pantalla que
    ese botón abrió algo, y `aria-describedby` es lo que hace que le lea el
    texto sin tener que ir a buscarlo."""
    assert "aria-expanded" in js_info
    assert "aria-describedby" in js_info


def test_escape_devuelve_el_foco_al_boton(js_info):
    """Si el foco se pierde, el siguiente Tab arranca del principio de la
    página y el que navega con teclado tiene que recorrer todo de nuevo."""
    assert ".focus()" in js_info
