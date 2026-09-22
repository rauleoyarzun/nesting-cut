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


def test_muestra_el_material_que_queda_en_la_ultima_placa_junto_al_sobrante(js):
    """Las dos cifras que compiten van juntas en la pantalla: el criterio
    nuevo puede acortar la tira libre (`sobrante_mm`) para bajar el material
    que queda en la última placa, así que el usuario tiene que ver las dos
    para decidir por trabajo."""
    assert "material_ultima_placa_m2" in js
    assert "sobrante_mm" in js


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


def _opciones_de_posiciones(html: str) -> str:
    """El `<select id="posiciones">` solo, sin el resto de la página.

    Buscar `value="4"` en el HTML entero pasaría por cualquier campo
    numérico que tenga un 4 adelante."""
    desde = html.index('id="posiciones"')
    return html[desde : html.index("</select>", desde)]


@pytest.mark.parametrize("valor", ["4", "8", "16", "personalizado"])
def test_el_desplegable_de_posiciones_tiene_las_cuatro_opciones(html, valor):
    assert f'value="{valor}"' in _opciones_de_posiciones(html)


def test_las_posiciones_arrancan_en_cuatro(html):
    assert re.search(
        r'<option value="4"[^>]*selected', _opciones_de_posiciones(html)
    )


def test_las_posiciones_se_reparten_en_la_vuelta_entera(js):
    """4 posiciones son 0/90/180/270 y 16 son cada 22,5 grados. La cuenta
    tiene que ser i * 360 / n, no una tabla de ángulos escrita a mano: una
    tabla se desincroniza de las etiquetas del desplegable en cuanto
    alguien agregue 32."""
    cuerpo = _cuerpo_de_funcion(js, "angulosElegidos")

    assert "360" in cuerpo
    assert "Array.from" in cuerpo


def test_personalizado_revela_el_campo_de_texto(js):
    cuerpo = _cuerpo_de_funcion(js, "angulosElegidos")
    assert '"personalizado"' in cuerpo
    assert "campo-angulos" in js


def test_el_campo_de_angulos_sigue_validandose(js):
    """Sólo en la rama Personalizado, pero con el mismo error debajo del
    campo que tenía antes."""
    assert "angulosElegidos" in _cuerpo_de_funcion(js, "angulosValidos")
    assert '"angulos"' in js


def test_la_revision_esta_a_la_izquierda_del_resultado(html):
    assert html.index('id="tab-revision"') < html.index('id="tab-preview"')


def test_la_solapa_se_llama_resultado(html):
    assert ">Resultado<" in html
    assert "Previsualización" not in html


def test_la_rueda_no_salta_por_la_escalera(js):
    """La escalera queda para los botones. Cada evento de rueda avanzaba un
    escalón entero, y un gesto de trackpad manda decenas: iba de 25% a 600%
    de un toque."""
    handler = _cuerpo_de_handler(js, "wheel")

    assert "acercar(" not in handler
    assert "zoomContinuo" in handler


def test_la_rueda_normaliza_el_modo_del_delta(js):
    """Firefox reporta líneas y no píxeles: sin normalizar, el mismo gesto
    da un salto distinto en cada navegador."""
    assert "deltaMode" in _cuerpo_de_funcion(js, "enPixeles")


def test_el_zoom_de_la_rueda_esta_acotado(js):
    cuerpo = _cuerpo_de_funcion(js, "zoomContinuo")
    assert "ZOOM_MIN" in cuerpo and "ZOOM_MAX" in cuerpo


def test_los_botones_siguen_usando_la_escalera(js):
    assert "proximoPaso" in _cuerpo_de_funcion(js, "acercar")


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
    un plano de 1800 px se vuelve un juego de paciencia.

    El anclaje lo hace `aplicarNuevoZoom`, que comparten la rueda y los
    botones -- no `acercar()`, que ahora sólo elige el próximo escalón."""
    cuerpo = _cuerpo_de_funcion(js, "aplicarNuevoZoom")
    assert "getBoundingClientRect" in cuerpo and "scrollLeft" in cuerpo, (
        "aplicarNuevoZoom() ya no corrige el scroll, así que el punto bajo "
        "el cursor se va de lugar al ampliar"
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


def _blanquear(js: str, textos: bool) -> str:
    """Reemplaza por espacios los comentarios de `js`, y también los
    literales de texto si `textos`.

    Deja las llaves y los saltos de línea donde estaban, que es lo único que
    le importa a los escaneos de abajo. Recorre los literales aunque no los
    borre: un `//` adentro de una cadena no abre un comentario. Se hace a
    mano porque Python no trae un analizador de JavaScript y sumar uno por
    esto sería más máquina que problema.
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
            crudo = js[i:j]
            salida.append(
                "".join(ch if ch == "\n" else " " for ch in crudo) if textos else crudo
            )
            i = j
        else:
            salida.append(c)
            i += 1
    return "".join(salida)


def _sin_comentarios(js: str) -> str:
    """El archivo con los comentarios borrados y los textos intactos.

    Comentar una línea es una mutación de un renglón que mata la función
    igual que borrarla, y el texto del comentario sigue estando en el
    archivo: `// globo.classList.remove("oculto");` deja pasar cualquier
    aserción que busque esa llamada en el fuente crudo. Por eso toda
    aserción estructural sobre `info.js` mira el archivo por acá, y así
    borrar y comentar quedan indistinguibles para las pruebas.

    Los literales de texto no se tocan -- a diferencia de
    `_sin_comentarios_ni_textos` -- porque varias de esas aserciones son
    justamente sobre un literal: `"Escape"`, `".boton-info"`, `"globo-info"`,
    `"oculto"`, `"true"`/`"false"`.
    """
    return _blanquear(js, textos=False)


def _sin_comentarios_ni_textos(js: str) -> str:
    """El archivo con los comentarios y los literales de texto borrados.

    Para escanear estructura pura, donde una palabra adentro de una cadena
    no debe contar (ver `_declaraciones_globales`).
    """
    return _blanquear(js, textos=True)


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
    "angulos", "posiciones", "tol-cierre", "resolucion", "espejo", "recortes",
]


@pytest.fixture(scope="module")
def js_info():
    return (rutas.recurso("web") / "info.js").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def info_limpio(js_info):
    """`info.js` sin comentarios: el fuente contra el que se afirma todo lo
    estructural que no cae adentro de una función o de un handler (ver
    `_sin_comentarios`)."""
    return _sin_comentarios(js_info)


def claves_y_textos(js_info: str) -> dict[str, str]:
    """El literal `TEXTOS` de `info.js`, leído como diccionario.

    Leerlo con una expresión regular y no evaluarlo es a propósito: el test
    no necesita un intérprete de JavaScript, necesita saber qué claves hay y
    qué dice cada una. Por eso el literal tiene todas las claves entre
    comillas y un par clave/valor por línea -- es un formato que se parsea
    en cuatro líneas, y el test que sigue lo obliga a seguir siéndolo.
    """
    # `.index()` pelado tira `ValueError: substring not found`, sin decir qué
    # archivo ni qué se esperaba, y de acá cuelgan 21 tests: renombrar
    # `TEXTOS` daría 21 trazas sin una palabra útil. Mismo criterio que
    # `_cuerpo_de_funcion` y `_cuerpo_de_handler`.
    if "const TEXTOS = {" not in js_info:
        pytest.fail(
            "no encontré `const TEXTOS = {` en info.js. Es el mapa de los "
            "textos de ayuda; si lo renombraste, actualizá este helper"
        )
    cuerpo = js_info[js_info.index("const TEXTOS = {"):]
    if "\n};" not in cuerpo:
        pytest.fail(
            "el literal `TEXTOS` de info.js no cierra con `};` al principio "
            "de un renglón, que es el formato que este helper sabe leer"
        )
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


def _cuerpo_de_funcion(js_info: str, nombre: str) -> str:
    """El cuerpo de la función `<nombre>`, sin comentarios.

    Se aceptan las dos formas de declararla: `function <nombre>(...) {` y
    `const <nombre> = (...) => {`. Pasar de una a la otra no cambia nada de
    lo que el usuario ve, así que no tiene por qué obligar a editar una
    prueba.

    Se delimita igual que en el resto del archivo: desde la declaración
    hasta el primer `}` que arranca una línea (ninguna de las funciones de
    `info.js` tiene un bloque anidado que cierre así antes de su propio
    final). Pasa por `_sin_comentarios` para que comentar una línea cuente
    igual que borrarla; los textos quedan porque muchas de las aserciones
    son sobre un literal.

    Cuando no encuentra la función corta con `pytest.fail` y dice qué
    buscaba: antes era un `.index()` pelado, y renombrar o redeclarar la
    función daba un `ValueError: substring not found` sin una palabra sobre
    qué archivo, qué función ni qué formas se aceptan."""
    limpio = _sin_comentarios(js_info)
    declaracion = re.search(
        rf"""\bfunction\s+{nombre}\s*\("""
        rf"""|\b(?:const|let|var)\s+{nombre}\s*="""
        rf"""\s*(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>""",
        limpio,
    )
    if not declaracion:
        pytest.fail(
            f"info.js ya no declara `{nombre}` de ninguna de las dos formas "
            f"que esta prueba sabe leer -- `function {nombre}(...) {{` o "
            f"`const {nombre} = (...) => {{` --, así que no hay cuerpo que "
            "mirar"
        )
    fin = limpio.find("\n}", declaracion.start())
    if fin == -1:
        pytest.fail(
            f"no se encontró el `}}` que cierra a `{nombre}` al principio de "
            "un renglón: el cuerpo de la función no se puede delimitar"
        )
    return limpio[declaracion.start():fin]


def _cuerpo_de_handler(js_info: str, evento: str) -> str:
    """El cuerpo del `addEventListener(<evento>, ...)` que registra un
    handler en línea (una función flecha), sin comentarios.

    Es lo que hay que mirar para saber qué hace de verdad ese handler, no
    qué palabras aparecen en algún comentario cerca. Antes borraba también
    los textos; ahora no, porque lo que decide el comportamiento de estos
    handlers *son* literales -- `".boton-info"` en el `closest` del click,
    `"Escape"` en el guardia del keydown -- y sin ellos no hay forma de
    fijarlos.

    Ni las comillas del nombre del evento ni el corte de renglones son
    parte del contrato: un formateador que prefiera comillas simples, o que
    parta la llamada y le deje una coma final, no cambia qué escucha nadie.
    Tampoco lo es el tercer argumento de opciones (`{ passive: false }`,
    `{ once: true }`, `true`) -- la rueda lo usa y el patrón de cierre lo
    contempla, además de la forma de dos argumentos, para no seguir de
    largo buscando el `}` que cierra el handler siguiente.
    Y si no encuentra el handler corta con `pytest.fail` diciendo qué
    buscaba, en vez del `ValueError` pelado de un `.index()`."""
    limpio = _sin_comentarios(js_info)
    registro = re.search(rf"""addEventListener\(\s*["']{evento}["']""", limpio)
    if not registro:
        pytest.fail(
            f'info.js ya no registra ningún handler de "{evento}": no está '
            f'el `addEventListener("{evento}", ...)` que esta prueba lee'
        )
    cierre = re.search(
        r"\n\s*\}\s*(?:,\s*(?:\{[^{}]*\}|[\w.]+)\s*)?,?\s*\)\s*;",
        limpio[registro.start():],
    )
    if not cierre:
        pytest.fail(
            f'no se encontró el `}});` que cierra el handler de "{evento}": '
            "el cuerpo del handler no se puede delimitar"
        )
    return limpio[registro.start():registro.start() + cierre.start()]


def test_el_cuerpo_del_handler_no_se_come_los_que_siguen(js):
    """`addEventListener` acepta un tercer argumento -- el objeto de
    opciones --, y la rueda lo usa: `(e) => {...}, { passive: false });`.
    Si el patrón que busca el cierre del handler no contempla esa forma, no
    encuentra el `}` que cierra ahí y sigue buscando más abajo: el "cuerpo"
    que devuelve para la rueda termina incluyendo el de `ondblclick`
    (`zoom === null ? 1 : null`) y el de `pointerdown`
    (`setPointerCapture`), que no tienen nada que ver con la rueda.

    Esto no es un detalle de implementación: `test_la_rueda_no_salta_por_la_
    escalera` afirma sobre este mismo cuerpo, y con la sobrecaptura pasa por
    la razón equivocada -- mirando texto de otro handler."""
    handler = _cuerpo_de_handler(js, "wheel")
    assert "zoom === null ? 1 : null" not in handler
    assert "setPointerCapture" not in handler


def test_la_pagina_carga_info_js(html):
    assert '<script src="info.js">' in html


def test_info_js_va_entero_adentro_de_una_iife(info_limpio):
    """Ver el test de nombres globales de más abajo: sin la IIFE, cualquier
    nombre que `app.js` ya haya declarado mata este archivo entero.

    Se mira el fuente sin comentarios porque comentar la línea que la abre
    (`// (() => {`) deja las dos cadenas en el archivo y rompe el archivo
    entero: el `})();` del final queda sin abrir, que es un SyntaxError."""
    assert "(() => {" in info_limpio and "})();" in info_limpio


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


# Las pruebas que siguen son estructurales y acotadas: cada una mira adentro
# de una función o de un handler puntual de `info.js` -- nunca el archivo
# entero -- y afirma la *forma* de una línea que, si desaparece o cambia un
# token, mata algo que el usuario nota. El objetivo declarado es que cada
# renglón que hace trabajo tenga al menos una aserción que se caiga si lo
# borran, lo comentan o le dan vuelta el token esencial.
#
# Dos decisiones que no son olvidos:
#
# * Todo pasa por `_sin_comentarios` (ver el helper): comentar una línea es
#   una mutación de un renglón tan mortal como borrarla, y antes se colaba,
#   porque el texto del comentario seguía estando en el archivo.
# * La aritmética de `ubicar()` queda sin fijar a propósito. Ver
#   `test_ubicar_consulta_la_ventana_y_mueve_el_globo`.


def test_el_globo_del_script_es_el_que_el_html_trae(info_limpio, html):
    """`const globo = document.getElementById("globo-info");` es la única
    línea que ata este script al DOM, y la única cuyo error no se puede ver
    leyendo `info.js` contra sí mismo: con el id mal tipeado el archivo
    sigue siendo perfectamente coherente -- `globo` simplemente queda en
    `null`, y el primer clic tira adentro de `abrir()`. Ningún globo,
    nunca. Por eso el id se confronta con el HTML, que es donde está la
    otra mitad del contrato.

    Se acepta tanto `getElementById("x")` como `querySelector("#x")`: son
    la misma cosa dicha de dos maneras, y fijar una de las dos sería
    convertir un reacomodo legítimo en una edición de esta prueba.

    Verificación manual: cambiando el id por otro, este test falla."""
    hallazgo = re.search(
        r"""\bglobo\s*=\s*document\."""
        r"""(?:getElementById\(\s*["']([\w-]+)["']"""
        r"""|querySelector\(\s*["']#([\w-]+)["'])""",
        info_limpio,
    )
    assert hallazgo, "info.js ya no toma el globo por su id"
    identificador = hallazgo.group(1) or hallazgo.group(2)
    assert f'id="{identificador}"' in html, (
        f"info.js busca el elemento #{identificador}, que el HTML no trae: "
        "`globo` queda en null y el primer clic tira"
    )


def test_el_boton_abierto_se_declara_antes_de_usarse(info_limpio):
    """`let abierto = null;` es la declaración que `abrir()` y `cerrar()`
    escriben. El archivo corre en modo estricto -- `"use strict"` en la
    primera línea --, así que sin ella el `abierto = boton;` de `abrir()`
    no crea un global de prepo: tira ReferenceError y mata el primer clic.

    Verificación manual: borrando `let abierto = null;`, este test falla."""
    assert re.search(r"\blet\s+abierto\s*=\s*null\b", info_limpio), (
        "info.js ya no declara `abierto`: en modo estricto, escribirla tira"
    )


def test_el_margen_contra_el_borde_se_declara_antes_de_usarse(info_limpio):
    """`const MARGEN = 8;` es la otra declaración del ámbito del módulo, y
    borrarla mata la feature tan callado como borrar `abierto`: `ubicar()`
    lee `MARGEN` cuatro veces, y en modo estricto leer un nombre que nadie
    declaró es un ReferenceError.

    Dónde tira es lo que lo hace invisible: adentro de `ubicar()`, después
    del `classList.remove("oculto")` y antes del `globo.style.visibility =
    ""`. El globo queda sin la clase que lo esconde pero con el
    `visibility: hidden` que `ubicar()` le puso para medirlo, o sea
    invisible para siempre, y `abrir()` --que quedó a mitad de camino--
    nunca llega a ponerle los atributos ARIA al botón ni a anotarlo en
    `abierto`. En la pantalla: el primer clic en un ícono no hace nada, y
    ninguno de los siguientes tampoco.

    Se fija que esté declarada, no cuánto vale: el valor es aritmética de
    `ubicar()` y queda deliberadamente sin fijar (ver
    `test_ubicar_consulta_la_ventana_y_mueve_el_globo`).

    Verificación manual: borrando `const MARGEN = 8;`, este test falla."""
    assert re.search(r"\b(?:const|let|var)\s+MARGEN\s*=", info_limpio), (
        "info.js ya no declara `MARGEN`: en modo estricto, las cuatro "
        "lecturas que hace ubicar() tiran, y el globo queda invisible"
    )


def test_el_click_resuelve_el_boton_por_la_clase_que_el_html_usa(js_info, html):
    """`e.target.closest?.(".boton-info")` es lo que traduce "el usuario
    apretó acá" en "apretó el ícono de ayuda de tal campo". Con un selector
    que no existe -- `.boton-infos` -- `boton` es `null` en todos los
    clics: no se abre nada nunca. Y el handler sigue ahí, registrado, con
    su `abrir(boton)` y su `cerrar()` intactos, así que ninguna prueba que
    mire esas llamadas se entera.

    La clase también se confronta con el HTML: tiene que estar puesta en
    los botones que llevan `data-info`.

    El receptor es parte de la aserción. `e.currentTarget.closest?.(...)`
    parece lo mismo y no lo es: `currentTarget` es el `document` --ahí está
    registrado el handler--, `document.closest` no existe, y el `?.` se
    come el error en silencio. `boton` queda `undefined` en todos los
    clics y no se abre nada nunca, sin un solo mensaje en una consola que
    en pywebview tampoco se puede abrir.

    Verificación manual: cambiando `.boton-info` por `.boton-infos`, y
    `e.target` por `e.currentTarget`, este test falla en los dos casos."""
    cuerpo = _cuerpo_de_handler(js_info, "click")
    hallazgo = re.search(
        r"""e\.target\.closest\??\.?\(\s*["']\.([\w-]+)["']\s*,?\s*\)""", cuerpo
    )
    assert hallazgo, (
        "el handler de click ya no resuelve el botón con "
        "e.target.closest(): ningún clic sabe sobre qué ícono cayó"
    )
    clase = hallazgo.group(1)
    assert re.search(
        rf'class="[^"]*\b{re.escape(clase)}\b[^"]*"[^>]*data-info=', html
    ), (
        f"el click busca `.{clase}`, que el HTML no le pone a ningún botón "
        "con data-info: ningún clic resuelve un botón"
    )


def test_el_click_en_un_boton_llama_a_abrir(js_info):
    """Borrar `if (boton) abrir(boton);` del handler de click no toca
    ningún literal que las pruebas originales miraran: el globo dejaba de
    abrirse para siempre y las seis pasaban igual.

    La guarda va junto con la llamada. `if (!boton) abrir(boton);` --un
    caracter-- deja la llamada donde estaba: clic en un ícono, nada; clic
    en cualquier otro lado de la pantalla, `abrir(null)`, que tira. Buscar
    la llamada suelta no alcanza.

    Verificación manual: borrando la línea `if (boton) abrir(boton);`, y
    negándole la condición, este test falla en los dos casos."""
    cuerpo = _cuerpo_de_handler(js_info, "click")
    llamada = re.search(r"if\s*\(([^)]*)\)\s*\{?\s*abrir\(\s*boton\s*,?\s*\)", cuerpo)
    assert llamada, (
        "el handler de click ya no llama a abrir(boton) detrás de una "
        "guarda: ningún clic abre el globo"
    )
    assert "boton" in llamada.group(1) and "!" not in llamada.group(1), (
        "el handler de click abre el globo justo cuando *no* hay botón: "
        f"`if ({llamada.group(1).strip()})`"
    )


def test_el_mismo_boton_cierra_el_globo_que_tenia_abierto(js_info):
    """La rama de toggle compara el botón apretado contra `abierto`. Con
    `!==` en vez de `===` la comparación da verdadera en el primer clic
    --el botón apretado no es el que está abierto, porque no hay ninguno--
    y el handler cierra y se va por su `return` antes de llegar a
    `abrir()`: el globo no se abre nunca, con un caracter de diferencia.

    La rama se verifica entera, porque cada pedazo carga algo:

    * el `&&`. Con `||` la condición da verdadera también cuando no hay
      ningún botón bajo el clic (`null === null`) y cuando el botón es otro
      distinto del abierto -- es decir, casi siempre: el handler cierra y
      se va antes de `abrir()`, y el globo no aparece nunca.
    * el `cerrar()` de adentro. Sin él, apretar el mismo botón no lo cierra
      y el globo se queda pegado.
    * el `return`. Sin él la ejecución sigue de largo por el `cerrar();` y
      el `abrir(boton)` de abajo: el mismo botón cierra y vuelve a abrir en
      el mismo gesto, que es exactamente el "parece que no hace nada" que
      esta rama existe para evitar.

    Verificación manual: cambiando `===` por `!==`, `&&` por `||`, y
    sacando por separado el `cerrar();` y el `return;` de adentro de las
    llaves, este test falla en los cuatro casos."""
    cuerpo = _cuerpo_de_handler(js_info, "click")
    rama = re.search(r"if\s*\(([^)]*===\s*abierto\b[^)]*)\)\s*\{(.*?)\}", cuerpo, re.S)
    assert rama, (
        "el handler de click ya no compara el botón apretado con `abierto` "
        "por identidad: o no hay toggle, o la comparación está dada vuelta "
        "y no se abre nada"
    )
    condicion, bloque = rama.group(1), rama.group(2)
    assert "&&" in condicion and "||" not in condicion, (
        "la rama del toggle ya no exige *las dos* cosas (que haya botón y "
        f"que sea el abierto): `{condicion.strip()}`"
    )
    assert re.search(r"\bcerrar\(\s*\)", bloque), (
        "la rama del toggle ya no cierra: apretar el mismo botón deja el "
        "globo pegado"
    )
    assert re.search(r"\breturn\b", bloque), (
        "la rama del toggle ya no corta: sigue de largo y vuelve a abrir "
        "el globo que acaba de cerrar, en el mismo gesto"
    )


def test_el_click_cierra_el_globo_anterior_antes_de_abrir_el_nuevo(js_info):
    """El `cerrar();` suelto --el que está afuera de las llaves del
    toggle-- es lo que despega el globo del botón anterior cuando el
    usuario pasa de un campo al siguiente. Borrarlo no se ve: el globo se
    mueve igual, porque `abrir()` lo reposiciona. Lo que queda atrás es el
    botón viejo con `aria-expanded="true"` y `aria-describedby` puestos
    para siempre, y a los cinco clics hay media docena de botones que le
    anuncian a un lector de pantalla que cada uno abrió el globo. Una
    regresión pura de accesibilidad, invisible en la pantalla y por eso
    mismo la que nadie va a reportar.

    Se fija la forma y no el orden exacto de los renglones: tiene que haber
    una llamada a `cerrar()` que sea una sentencia del handler --no la de
    adentro del toggle-- y que esté antes de la llamada a `abrir()`.

    Verificación manual: borrando ese `cerrar();`, este test falla."""
    lineas = _cuerpo_de_handler(js_info, "click").splitlines()
    sueltas = [i for i, l in enumerate(lineas) if l.strip() == "cerrar();"]
    abre = [i for i, l in enumerate(lineas) if re.search(r"\babrir\(", l)]
    assert sueltas, (
        "el handler de click ya no tiene un `cerrar();` suelto: el botón "
        "anterior se queda con aria-expanded=\"true\" y aria-describedby "
        "puestos para siempre"
    )
    assert abre and min(sueltas) < max(abre), (
        "el `cerrar();` suelto quedó después de abrir(): cierra el globo "
        "que acaba de abrir"
    )


def test_abrir_saca_el_texto_del_data_info_del_boton(js_info):
    """`TEXTOS[boton.dataset.info]` es lo que convierte el botón apretado
    en el texto que se muestra. Con `dataset.infos` --o con cualquier otra
    propiedad-- `texto` queda `undefined` para los diez botones, el
    `if (!texto) return;` corta siempre y no se abre nada. Todas las
    pruebas sobre el contenido de `TEXTOS` siguen pasando: el mapa está
    intacto; lo que se rompió es la llave con la que se lo consulta.

    Se acepta `boton.dataset.info` o el `boton.getAttribute("data-info")`
    equivalente: son la misma lectura escrita de dos maneras.

    Verificación manual: cambiando `dataset.info` por `dataset.infos`, este
    test falla."""
    cuerpo = _cuerpo_de_funcion(js_info, "abrir")
    assert re.search(
        r"""\bTEXTOS\s*\[\s*boton\."""
        r"""(?:dataset\.info\b|getAttribute\(\s*["']data-info["']\s*,?\s*\))""",
        cuerpo,
    ), "abrir() ya no busca el texto en TEXTOS por el data-info del botón"


def test_abrir_corta_cuando_no_hay_texto_y_no_al_reves(js_info):
    """`if (!texto) return;` protege del botón sin entrada en `TEXTOS`.
    Dado vuelta --`if (texto) return;`-- hace exactamente lo contrario: las
    diez claves conocidas cortan y la única que llegaría a abrir un globo
    es la que no tiene nada que decir. El archivo queda con la misma forma
    y un caracter menos.

    Verificación manual: sacándole el `!`, este test falla."""
    cuerpo = _cuerpo_de_funcion(js_info, "abrir")
    assert re.search(r"if\s*\(\s*!\s*texto\s*\)\s*return", cuerpo), (
        "abrir() ya no corta cuando *no* hay texto: o no corta nunca, o "
        "corta justo con los diez botones que sí tienen ayuda"
    )


def test_abrir_escribe_el_texto_en_el_globo(js_info):
    """`globo.textContent = texto;` es la línea que más se parece a "la
    feature" y la que menos huella deja en el resto del archivo: ninguna
    otra la menciona. Sin ella el globo abre, se ubica contra el ícono
    correcto, anuncia bien sus atributos ARIA y se cierra por las cuatro
    vías -- vacío, siempre.

    Verificación manual: borrando (o comentando) esa línea, este test
    falla."""
    cuerpo = _cuerpo_de_funcion(js_info, "abrir")
    assert re.search(r"\bglobo\.textContent\s*=\s*texto\b", cuerpo), (
        "abrir() ya no escribe el texto en el globo: se abre en blanco"
    )


def test_abrir_registra_el_boton_como_el_globo_abierto(js_info):
    """`abierto` es lo único que le permite a `cerrar()`, al clic repetido
    sobre el mismo botón y a Escape saber cuál botón tiene el globo
    abierto. Borrar `abierto = boton;` de `abrir()` no toca ningún literal
    de los que las demás pruebas verifican --el globo todavía abre la
    primera vez, con el texto y la posición correctos-- pero el toggle y
    las cuatro formas de cerrar, que miran `abierto`, quedan rotas.

    Verificación manual: borrando `abierto = boton;` de `abrir()`, este
    test falla."""
    cuerpo = _cuerpo_de_funcion(js_info, "abrir")
    assert re.search(r"\babierto\s*=\s*boton\b", cuerpo), (
        "abrir() ya no guarda el botón en `abierto`"
    )


def test_abrir_deja_el_globo_realmente_visible(js_info):
    """`test_el_click_en_un_boton_llama_a_abrir` sólo comprueba que el
    click llegue a `abrir(boton)`; no mira si `abrir`, una vez llamada,
    deja algo en pantalla. Cuatro borrados distintos y salteados entre sí
    --la línea `ubicar(boton);` dentro de `abrir()`, la línea
    `globo.classList.remove("oculto");` dentro de `ubicar()`, el
    `globo.style.visibility = "hidden";` con el que `ubicar()` lo mide sin
    que parpadee en la esquina, o el `globo.style.visibility = "";` con el
    que lo devuelve a la vista-- dejaban pasar toda la batería de pruebas
    existente: `ubicar()` es la única que le saca la clase `oculto` y la
    única que limpia el `visibility` que ella misma puso.

    Verificación manual: borrando cualquiera de esas cuatro líneas de
    info.js, una por vez, este test falla en cada caso. Comentarlas también
    lo hace fallar, desde que los cuerpos pasan por `_sin_comentarios`."""
    abrir = _cuerpo_de_funcion(js_info, "abrir")
    assert re.search(r"\bubicar\(\s*boton\s*,?\s*\)", abrir), (
        "abrir() ya no llama a ubicar(boton): nada muestra ni posiciona el "
        "globo"
    )

    ubicar = _cuerpo_de_funcion(js_info, "ubicar")
    assert re.search(r"""classList\.remove\(\s*["']oculto["']\s*,?\s*\)""", ubicar), (
        "ubicar() ya no le saca la clase oculto al globo: queda oculto para "
        "siempre"
    )
    assert re.search(r"""visibility\s*=\s*["']hidden["']""", ubicar), (
        "ubicar() ya no esconde el globo para medirlo: aparece un cuadro "
        "parpadeando en la esquina antes de cada globo"
    )
    assert re.search(r"""visibility\s*=\s*(?:""|'')""", ubicar), (
        "ubicar() ya no limpia el visibility \"hidden\" que puso para "
        "medir el globo: queda invisible para siempre"
    )


def test_el_globo_se_ubica_contra_el_boton(js_info):
    """Si no lee el rect del botón, el globo sale siempre en el mismo lado
    de la pantalla y no se sabe de qué campo habla. Si no lee el suyo, no
    tiene con qué decidir si entra a la derecha: `g` queda sin definir y
    `ubicar()` tira antes de mostrar nada.

    El orden también importa, y es la parte que menos se ve: `.oculto` es
    `display: none !important`, y un elemento en `display: none` mide 0 x 0.
    Medir el globo *antes* de sacarle la clase devuelve un rectángulo
    vacío, con lo cual las dos comparaciones contra el borde de la ventana
    nunca se cumplen y el globo de las opciones de abajo se va afuera de la
    pantalla, justo en la ventana angosta para la que se escribieron.

    Verificación manual: borrando cualquiera de las dos líneas `const b =`
    / `const g =`, y subiendo el `const g =` arriba del
    `classList.remove("oculto")`, este test falla en los tres casos."""
    cuerpo = _cuerpo_de_funcion(js_info, "ubicar")
    assert re.search(r"\bboton\.getBoundingClientRect\(\s*\)", cuerpo), (
        "ubicar() ya no mide el botón: el globo no sabe contra qué ícono ir"
    )
    mide = re.search(r"\bglobo\.getBoundingClientRect\(\s*\)", cuerpo)
    assert mide, (
        "ubicar() ya no mide el globo: sin su tamaño no puede saber si "
        "entra, y la variable queda sin definir"
    )
    muestra = re.search(
        r"""\bglobo\.classList\.remove\(\s*["']oculto["']\s*,?\s*\)""", cuerpo
    )
    assert muestra and muestra.start() < mide.start(), (
        "ubicar() mide el globo antes de sacarle la clase `oculto`, que es "
        "`display: none`: mide 0 x 0 y los dos ajustes contra el borde de "
        "la ventana dejan de hacer nada"
    )


def test_ubicar_declara_las_coordenadas_antes_de_usarlas(js_info):
    """`let x = ...` y `let y = ...` son las dos variables con las que
    `ubicar()` hace toda la cuenta. Borrar cualquiera de las dos
    declaraciones --y dejar el resto igual-- deja un nombre que nadie
    declaró, y el modo estricto no lo perdona: la primera lectura
    (`x + g.width`, `y + g.height`) tira ReferenceError adentro de
    `ubicar()`, con la clase `oculto` ya sacada y el `visibility: hidden`
    todavía puesto. El globo queda invisible para siempre y el botón sin
    sus atributos ARIA, igual que con `MARGEN`.

    Ninguna otra prueba se entera: las cuentas que nombran `x` e `y`
    siguen escritas tal cual, y las aserciones sobre `innerWidth` /
    `innerHeight` y sobre `globo.style.left` / `globo.style.top` las
    encuentran todas.

    Se fija la declaración, no lo que se le asigna: de qué lado del ícono
    arranca cada coordenada es aritmética de `ubicar()`, deliberadamente
    sin fijar (ver el test que sigue).

    Verificación manual: borrando `let x = b.right + MARGEN;` y
    `let y = b.top;`, una por vez, este test falla en los dos casos."""
    cuerpo = _cuerpo_de_funcion(js_info, "ubicar")
    for coordenada in ("x", "y"):
        assert re.search(rf"\b(?:const|let|var)\s+{coordenada}\s*=", cuerpo), (
            f"ubicar() ya no declara `{coordenada}`: en modo estricto, la "
            "primera lectura tira y el globo se queda invisible"
        )


def _reaccion_al_borde(cuerpo: str, eje: str) -> str:
    """Lo que `ubicar()` *hace* cuando la cuenta contra `window.<eje>` dice
    que el globo no entra.

    Si el recorte está escrito con un `if`, es su rama: las llaves, o lo
    que quede del renglón cuando no las tiene (las dos formas están en el
    archivo, y pasar de una a la otra no cambia nada). Si no hay ningún
    `if` --un `Math.min` recorta lo mismo sin ramificar-- son los
    renglones que nombran el eje.

    Sirve para distinguir un recorte de una comparación sola: comparar y
    no asignar nada deja al globo saliéndose de la pantalla."""
    for comparacion in re.finditer(
        r"if\s*(\([^()]*(?:\([^()]*\)[^()]*)*\))\s*", cuerpo
    ):
        if eje not in comparacion.group(1):
            continue
        resto = cuerpo[comparacion.end():]
        if not resto.startswith("{"):
            return resto.split("\n", 1)[0]
        fin = resto.find("}")
        return resto[1:] if fin == -1 else resto[1:fin]
    return "\n".join(l for l in cuerpo.splitlines() if eje in l)


def test_ubicar_consulta_la_ventana_y_mueve_el_globo(js_info):
    """El panel mide 336 px y la ventana no siempre es ancha: si no se mide
    contra `innerWidth` / `innerHeight`, el globo de las opciones avanzadas
    --que están abajo de todo-- sale cortado por el borde. Y si no escribe
    `style.left` *y* `style.top`, queda clavado en una de las dos
    coordenadas, lejos del campo que explica.

    Se fija que consulte los dos ejes de la ventana, que escriba las dos
    coordenadas, y el emparejamiento obvio entre una cosa y la otra: la
    cuenta que mira `innerWidth` trabaja con anchos y la que mira
    `innerHeight`, con altos. Cambiar `window.innerWidth` por
    `window.innerHeight` --el error de copiar y pegar típico de esas cuatro
    líneas-- tiraba el globo afuera por la derecha en cualquier ventana más
    alta que ancha, y hasta acá no lo agarraba nada más que la casualidad
    de que la palabra `innerWidth` apareciera exactamente una vez en el
    archivo.

    Cada uno de los dos recortes, además, tiene que *hacer* algo: comparar
    contra el borde y no mover nada es lo mismo que no comparar. El de la
    horizontal está escrito en un solo renglón --la asignación va pegada al
    `if`-- y por eso borrarlo se notaba; el de la vertical lleva llaves, y
    vaciarlas (`if (y + g.height > window.innerHeight - MARGEN) { }`)
    dejaba pasar la aserción de arriba, a la que le alcanza con que el
    renglón del `innerHeight` nombre un `height`. El globo de las opciones
    de abajo se iba fuera de la pantalla: exactamente la falla que este
    test dice evitar. La asimetría era del formato, no de la intención.

    **La aritmética de `ubicar()` queda deliberadamente sin fijar**: los
    `MARGEN`, el `b.right` contra el `b.left`, los `Math.max`, cuál de las
    dos coordenadas recibe cuál cuenta. Escribir eso en el test es
    transcribirlo, no verificarlo: no agrega ninguna garantía sobre lo que
    el usuario ve y convierte cualquier reacomodo legítimo de esas cuatro
    líneas en una edición de esta prueba. Es una decisión tomada, no un
    olvido; el techo honesto de una prueba que lee el archivo como texto.

    Verificación manual: cambiando `window.innerWidth` por
    `window.innerHeight`, borrando por separado cada uno de los dos
    `globo.style.left` / `globo.style.top`, y vaciando las llaves del
    ajuste vertical, este test falla en los cuatro casos."""
    cuerpo = _cuerpo_de_funcion(js_info, "ubicar")
    for eje, medida in (("innerWidth", "width"), ("innerHeight", "height")):
        lineas = [l for l in cuerpo.splitlines() if eje in l]
        assert lineas, f"ubicar() ya no consulta window.{eje}"
        assert all(medida in l for l in lineas), (
            f"hay una cuenta contra window.{eje} que no menciona ningún "
            f"`{medida}`: el ancho y el alto de la ventana quedaron cruzados"
        )
        assert re.search(r"\b\w+\s*=(?![=>])", _reaccion_al_borde(cuerpo, eje)), (
            f"la cuenta contra window.{eje} compara y no asigna nada: el "
            "globo se sale de la pantalla igual que si el ajuste no "
            "estuviera"
        )
    for coordenada in ("left", "top"):
        asignacion = re.search(rf"\bglobo\.style\.{coordenada}\s*=(.+)", cuerpo)
        assert asignacion, (
            f"ubicar() ya no escribe globo.style.{coordenada}: el globo "
            "queda clavado en esa coordenada"
        )
        assert "px" in asignacion.group(1), (
            f"globo.style.{coordenada} se escribe sin unidad. Un número "
            "pelado no es un largo de CSS: el navegador descarta la "
            "asignación entera, sin error, y el globo se queda donde lo "
            "dejó la hoja de estilos"
        )


def test_cerrar_corta_cuando_no_hay_nada_abierto_y_no_al_reves(js_info):
    """`if (!abierto) return;` es lo que hace que `cerrar()` sea inocua
    cuando no hay ningún globo. Dado vuelta corta justo cuando *sí* lo hay:
    el globo no se cierra por ninguna de las cuatro vías, y las pruebas que
    verifican que el clic, Escape, el scroll y el resize llaman a `cerrar`
    pasan todas, porque las llamadas siguen estando.

    Verificación manual: sacándole el `!`, este test falla."""
    cuerpo = _cuerpo_de_funcion(js_info, "cerrar")
    assert re.search(r"if\s*\(\s*!\s*abierto\s*\)\s*return", cuerpo), (
        "cerrar() ya no corta cuando *no* hay nada abierto: o no corta "
        "nunca, o corta justo cuando hay un globo que cerrar"
    )


def test_cerrar_oculta_el_globo_y_limpia_los_atributos(js_info):
    """Reducir el cuerpo de `cerrar()` a sólo `abierto = null;` deja el
    globo, que ya estaba en pantalla, sin volver a ocultarse nunca: nada le
    agrega la clase `oculto` ni le saca los atributos ARIA al botón que lo
    tenía abierto.

    (Una versión anterior de este docstring decía que esa reducción dejaba
    pasar las demás pruebas, y que la única que miraba adentro de la
    función sólo buscaba el literal de `aria-expanded`. Las dos cosas eran
    falsas: la reducción hace fallar **dos** pruebas --ésta y la de los
    valores de `aria-expanded`-- y esa segunda es una aserción estructural
    acotada al cuerpo de `cerrar()`, no un grep de un literal. El docstring
    quedó de un borrador previo al endurecimiento y nunca se actualizó.)

    Verificación manual: reemplazando el cuerpo de `cerrar()` por
    `abierto = null;`, fallan esta prueba y
    `test_aria_expanded_va_al_boton_y_con_el_valor_correcto`."""
    cuerpo = _cuerpo_de_funcion(js_info, "cerrar")
    assert re.search(r"""classList\.add\(\s*["']oculto["']\s*,?\s*\)""", cuerpo), (
        "cerrar() ya no oculta el globo"
    )
    saca = re.search(
        r"""\babierto\.removeAttribute\(\s*["']aria-describedby["']\s*,?\s*\)""",
        cuerpo,
    )
    assert saca, (
        "cerrar() ya no le saca aria-describedby *al botón*: un lector de "
        "pantalla lo sigue anunciando como si el globo siguiera abierto"
    )
    vacia = re.search(r"\babierto\s*=\s*null\b", cuerpo)
    assert vacia, (
        "cerrar() ya no vacía `abierto`: el botón anterior sigue "
        "considerándose el que tiene el globo abierto"
    )
    anuncia = re.search(r"""\babierto\.setAttribute\(\s*["']aria-expanded["']""", cuerpo)
    assert anuncia and vacia.start() > max(saca.start(), anuncia.start()), (
        "cerrar() vacía `abierto` antes de usarlo para limpiarle los "
        "atributos al botón: lo que viene después son accesos sobre null y "
        "tiran, así que no se cierra nada"
    )


@pytest.mark.parametrize("receptor,evento", [
    ("document", "click"), ("document", "keydown"),
    ("document", "scroll"), ("window", "resize"),
])
def test_cada_listener_se_registra_donde_el_evento_pasa(info_limpio, receptor, evento):
    """Un `addEventListener` en el objeto equivocado no falla, no avisa y no
    se ejecuta nunca. Registrar el click en `globo` en vez de en `document`
    --un cambio de una palabra-- deja el handler entero intacto, con su
    `closest`, su toggle y su `abrir(boton)`, y ningún clic en un ícono
    llega jamás, porque el ícono no está adentro del globo. Lo mismo con
    `resize`, que sólo existe en `window`: colgado de cualquier otro nodo
    no se dispara nunca.

    Esa clase de mutación sobrevivía a todas las aserciones de este
    archivo, porque todas miraban de la palabra `addEventListener` para la
    derecha.

    Verificación manual: cambiando el receptor de cada uno de los cuatro
    listeners, este test falla en los cuatro casos."""
    assert re.search(
        rf"""\b{receptor}\.addEventListener\(\s*["']{evento}["']""", info_limpio
    ), (
        f'el listener de "{evento}" ya no está colgado de `{receptor}`: '
        "el evento no pasa por donde está escuchando y el handler no corre "
        "nunca"
    )


def test_el_scroll_y_el_resize_cierran_llamando_a_cerrar(info_limpio):
    """El scroll y el resize tienen que *cerrar* el globo, no sólo
    mencionar esas palabras en algún lado del archivo. Si en vez de la
    referencia a `cerrar` quedara otra función (o una que sólo hace
    `abierto = null`), un grep de los literales `"scroll"`/`"resize"` no lo
    notaría.

    El `true` del scroll es parte de la misma aserción: el que scrollea es
    `.panel-opciones`, no la ventana, y el scroll de un elemento no
    burbujea hasta document -- en captura sí pasa por ahí. Sin el `true` el
    globo se queda flotando mientras el campo se va. (Antes eso lo cubría
    una prueba aparte, `test_el_scroll_se_escucha_en_captura`, que esta
    aserción subsume palabra por palabra.)

    Se mira el fuente sin comentarios: comentar cualquiera de las dos
    líneas deja el registro del listener adentro del comentario y el globo
    sin cerrarse.

    Verificación manual: comentando cada `addEventListener`, sacando el
    `true` del scroll y cambiando `cerrar` por otra cosa, este test falla
    en los cuatro casos."""
    assert re.search(
        r"""document\.addEventListener\("""
        r"""\s*["']scroll["']\s*,\s*cerrar\s*,\s*true\s*,?\s*\)""",
        info_limpio,
    ), (
        "el scroll ya no cierra el globo llamando a cerrar en la fase de "
        "captura"
    )
    assert re.search(
        r"""window\.addEventListener\(\s*["']resize["']\s*,\s*cerrar\s*,?\s*\)""",
        info_limpio,
    ), "el resize ya no cierra el globo llamando a cerrar"


def test_escape_cierra_el_globo_y_solo_escape(js_info):
    """El guardia del keydown es `e.key !== "Escape" || !abierto`. Con
    `===` en lugar de `!==` el comportamiento se da vuelta entero: Escape
    deja de cerrar, y cualquier otra tecla --tipear una separación en el
    campo de al lado-- cierra el globo y le roba el foco al campo para
    devolvérselo al ícono. La palabra `"Escape"` sigue en el archivo, que
    era lo único que se miraba antes.

    La segunda aserción es la otra mitad: que el handler, además de
    reconocer la tecla, llame a `cerrar()`.

    El resto del guardia va con la misma lógica. Con `abierto` en vez de
    `!abierto` corta justo cuando hay un globo abierto --Escape deja de
    cerrar-- y con `&&` en vez de `||` sólo corta si se dan las dos, o sea
    que Escape con nada abierto se mete igual a `cerrar()` y a
    `boton.focus()` sobre un `null`, que tira.

    Verificación manual: cambiando `!==` por `===`, `!abierto` por
    `abierto`, `||` por `&&`, y borrando el `cerrar();` del handler, este
    test falla en los cuatro casos."""
    cuerpo = _cuerpo_de_handler(js_info, "keydown")
    guardia = re.search(r"if\s*\(([^)]*)\)\s*return", cuerpo)
    assert guardia, "el handler de keydown ya no filtra qué tecla lo despierta"
    condicion = guardia.group(1)
    assert re.search(r"""e\.key\s*!==\s*["']Escape["']""", condicion), (
        "el handler de keydown ya no reconoce Escape por diferencia: o no "
        "cierra con Escape, o cierra con cualquier otra tecla"
    )
    assert re.search(r"!\s*abierto\b", condicion) and "||" in condicion, (
        "el guardia del keydown ya no se va cuando *no* hay nada abierto: "
        f"`{condicion.strip()}`"
    )
    assert re.search(r"\bcerrar\(\s*\)", cuerpo), (
        "el handler de keydown ya no llama a cerrar(): Escape no cierra"
    )


def test_escape_devuelve_el_foco_al_boton(js_info):
    """Si el foco se pierde, el siguiente Tab arranca del principio de la
    página y el que navega con teclado tiene que recorrer todo de nuevo.

    `".focus()" in js_info` es un grep sobre el archivo entero: un
    `.focus()` metido en un comentario (`// boton.focus();`) lo hace pasar
    sin que el handler de Escape devuelva nada. Se busca puntualmente
    adentro del cuerpo de ese handler, ya limpio de comentarios.

    La segunda aserción fija el orden: `const boton = abierto;` tiene que
    venir *antes* del `cerrar();`, porque `cerrar()` deja `abierto` en
    `null` y después ya no hay a quién devolverle el foco.

    Verificación manual: comentando la línea `boton.focus();` y moviendo el
    `const boton = abierto;` abajo del `cerrar();`, este test falla en los
    dos casos."""
    lineas = _cuerpo_de_handler(js_info, "keydown").splitlines()
    assert any(re.search(r"\bboton\.focus\(\)", l) for l in lineas), (
        "el handler de keydown ya no devuelve el foco al botón"
    )
    guarda = [i for i, l in enumerate(lineas) if re.search(r"\bboton\s*=\s*abierto\b", l)]
    cierra = [i for i, l in enumerate(lineas) if re.search(r"\bcerrar\(\s*\)", l)]
    assert guarda and cierra and min(guarda) < min(cierra), (
        "el handler de keydown ya no se guarda el botón antes de cerrar: "
        "cerrar() vacía `abierto` y el foco no vuelve a ningún lado"
    )


def test_abrir_pone_aria_describedby_en_el_boton(js_info):
    """Un grep de la cadena `"aria-describedby"` sobre el archivo entero la
    encuentra igual dentro de `cerrar()` --en su `removeAttribute`-- aunque
    `abrir()` ya no la ponga, y entonces un lector de pantalla nunca llega
    a leer el texto de ayuda porque el botón nunca quedó asociado al globo.
    Es la inversión exacta de la aserción sobre
    `removeAttribute("aria-describedby")` que hace
    `test_cerrar_oculta_el_globo_y_limpia_los_atributos` sobre `cerrar()`.

    El receptor es parte de la aserción: `globo.setAttribute(
    "aria-describedby", "globo-info")` --el globo apuntándose a sí mismo--
    no le sirve a nadie y no se ve en pantalla.

    Verificación manual: borrando esa línea, y cambiándole el receptor por
    `globo`, este test falla en los dos casos."""
    cuerpo = _cuerpo_de_funcion(js_info, "abrir")
    assert re.search(
        r"""\bboton\.setAttribute\("""
        r"""\s*["']aria-describedby["']\s*,\s*["']globo-info["']\s*,?\s*\)""",
        cuerpo,
    ), "abrir() ya no asocia el globo *al botón* con aria-describedby"


def test_aria_expanded_va_al_boton_y_con_el_valor_correcto(js_info):
    """Tres mutaciones de una línea, todas invisibles en la pantalla y
    todas mortales para un lector de pantalla:

    * intercambiar los literales `"true"`/`"false"` de los dos
      `setAttribute("aria-expanded", ...)`, con lo que se le informa al
      usuario justo lo contrario de lo que está pasando;
    * cambiar el receptor en `cerrar()` por `globo`, con lo que el atributo
      del botón nunca vuelve a `"false"` y queda anunciado como expandido
      para siempre;
    * lo mismo en `abrir()`, con lo que el botón nunca se anuncia como
      expandido.

    Un grep de `aria-expanded` sobre el archivo entero deja pasar las tres.

    Verificación manual: las tres, una por vez, hacen fallar este test."""
    abrir = _cuerpo_de_funcion(js_info, "abrir")
    cerrar = _cuerpo_de_funcion(js_info, "cerrar")
    assert re.search(
        r"""\bboton\.setAttribute\("""
        r"""\s*["']aria-expanded["']\s*,\s*["']true["']\s*,?\s*\)""",
        abrir,
    ), "abrir() no le anuncia al botón aria-expanded en true"
    assert re.search(
        r"""\babierto\.setAttribute\("""
        r"""\s*["']aria-expanded["']\s*,\s*["']false["']\s*,?\s*\)""",
        cerrar,
    ), "cerrar() no le anuncia al botón aria-expanded en false"


def test_el_campo_de_resolucion_arranca_en_uno(html):
    assert re.search(r'id="resolucion"[^>]*value="1"', html)


def test_los_recortes_viven_en_el_estado_de_la_sesion(js):
    assert "recortes: []" in js or "recortes: [ ]" in js


def test_registrar_no_borra_los_recortes(js):
    """Cambiar de archivo no tira los pedazos que hay contra la pared. Se
    pierden al cerrar el programa, no al abrir otro dibujo."""
    assert "recortes" not in _cuerpo_de_funcion(js, "registrar")


def test_los_recortes_se_mandan_con_los_parametros(js):
    assert "recortes: estado.recortes" in _cuerpo_de_funcion(js, "parametros")


def test_la_casilla_de_veta_cruzada_se_apaga_en_un_material_sin_veta(js):
    """Mira el cuerpo de la función y no el archivo: la primera versión de
    este test afirmaba `"disabled" in js`, y esa cadena ya estaba en el
    botón de guardar -- pasaba antes de que la casilla existiera."""
    cuerpo = _cuerpo_de_funcion(js, "ajustarVetaCruzada")

    assert '=== "libre"' in cuerpo
    assert '$("r-cruzada").disabled' in cuerpo
def test_el_material_arranca_en_el_que_mas_se_usa(js):
    """El selector se llenaba con el catálogo y se quedaba con el primero,
    que sale del orden del YAML. Elegir uno por nombre es lo que hace que el
    default no dependa de cómo quedó ordenado el archivo -- y el catálogo se
    guarda alfabético, así que ese orden ya cambió una vez."""
    cuerpo = _cuerpo_de_funcion(js, "refrescarMateriales")

    assert "MATERIAL_PREFERIDO" in cuerpo
    assert re.search(r'MATERIAL_PREFERIDO\s*=\s*"mdf15"', js)


def test_un_catalogo_sin_el_preferido_igual_elige_algo(js):
    """Se puede borrar mdf15 desde la pantalla de materiales. Si el default
    se aplicara a ciegas, el selector quedaría en un valor que no está en la
    lista: `select.value` devuelve "" y Acomodar sale con el material
    vacío."""
    cuerpo = _cuerpo_de_funcion(js, "refrescarMateriales")

    assert "some" in cuerpo or "includes" in cuerpo or "find" in cuerpo, (
        "nada comprueba que el preferido esté en el catálogo"
    )




def test_el_bloque_de_recortes_tiene_sus_controles(html):
    for id_ in [
        "lista-recortes", "alta-recorte", "r-ancho", "r-alto", "r-cantidad",
        "r-cruzada", "btn-agregar-recorte", "btn-confirmar-recorte",
        "btn-cancelar-recorte",
    ]:
        assert f'id="{id_}"' in html, id_


def test_el_reparto_de_placas_se_muestra_al_terminar(js):
    assert "recortes_usados" in js


def test_el_plural_de_placas_con_recortes_no_queda_fijo(js):
    """La rama de `terminar()` para cuando hubo recortes armaba
    `${r.placas} placas (...)` con "placas" fijo, igual que el resto del
    texto que sí pluraliza `recorte`/`nueva` según corresponda. Un trabajo
    chico que entra entero en un solo recorte -- el caso para el que existe
    esta función -- imprimía "1 placas (1 recorte + 0 nuevas)"."""
    cuerpo = _cuerpo_de_funcion(js, "terminar")
    inicio = cuerpo.index("r.recortes_usados > 0")
    fin = cuerpo.index("nueva${", inicio)
    rama_con_recortes = cuerpo[inicio:fin]
    assert not re.search(r"\$\{r\.placas\}\s*placas\b", rama_con_recortes), (
        'la rama con recortes sigue con "placas" pegado al literal, sin '
        "pluralizar cuando r.placas es 1"
    )
def test_las_medidas_del_recorte_van_una_abajo_de_la_otra(html):
    """Estaban los tres en un `.fila`, y `.fila > .campo` -- el que les da
    `min-width: 0` -- no les llegaba, porque adentro del `.fila` colgaban
    `.control` pelados. Resultado: el primero ocupaba el ancho entero y Alto
    y Cantidad quedaban dibujados afuera del panel. Lo reportó el usuario
    con una captura."""
    desde = html.index('id="alta-recorte"')
    hasta = html.index('data-error-de="recortes"', desde)
    alta = html[desde:hasta]
    medidas = alta[: alta.index('id="r-cruzada"')]
    assert "fila" not in medidas, (
        "las medidas del recorte volvieron a compartir una fila: " + medidas
    )


