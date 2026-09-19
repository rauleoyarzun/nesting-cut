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
