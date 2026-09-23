"use strict";

/* El cliente de la API y el flujo de la pantalla principal.
 *
 * Nada acá sabe si está corriendo en una ventana de escritorio o en un
 * navegador contra un servidor remoto. Esa diferencia vive en el servidor
 * (nesting_app/archivos.py) y en cómo llega el token. */

const SONDEO_MS = 400;

const TOKEN = document.querySelector('meta[name="token"]')?.content || "";
const EN_ESCRITORIO = document.querySelector('meta[name="escritorio"]')?.content === "1";

const $ = (id) => document.getElementById(id);

const estado = {
  fuenteId: null,
  nombreArchivo: null,
  unidades: null,
  trabajoId: null,
  sondeo: null,
  terminado: false,
  guardado: false,
  descartes: 0,
  // Sobrevive a cambiar de archivo y se pierde al cerrar el programa:
  // `registrar()` no lo toca a propósito. Un recorte anotado tres semanas
  // después ya se cortó o se traspapeló, así que guardarlo en disco sería
  // guardar una mentira.
  recortes: [],
  // El último número de minutos que se mostró, y desde cuándo el servidor
  // viene diciendo uno más alto. Ver `estabilizar()`.
  restante: null,
};

// --- el cliente HTTP --------------------------------------------------------

// Un 422 de pydantic no trae un texto: trae la lista de campos que no
// validaron. Armando el mensaje con `typeof detalle === "string" ? ... : ""`
// eso quedaba en cadena vacía y el cartel salía con título y sin una sola
// palabra adentro. Pasó de verdad: un typo en "Ángulos" mandaba
// `[null, null]` y el usuario veía una caja en blanco.
function textoDeDetalle(detalle) {
  if (typeof detalle === "string") return detalle;
  if (Array.isArray(detalle)) {
    return detalle
      .map((e) => [(e.loc || []).slice(1).join(" › "), e.msg].filter(Boolean).join(": "))
      .join("\n");
  }
  if (detalle && typeof detalle === "object") return JSON.stringify(detalle);
  return "";
}

async function api(ruta, opciones = {}) {
  const respuesta = await fetch(ruta, {
    ...opciones,
    headers: { "X-Token": TOKEN, ...(opciones.headers || {}) },
  });
  if (!respuesta.ok) {
    let detalle = respuesta.statusText;
    try {
      detalle = (await respuesta.json()).detail;
    } catch (_) { /* el cuerpo no era JSON; queda el statusText */ }
    const error = new Error(textoDeDetalle(detalle) || respuesta.statusText);
    error.estado = respuesta.status;
    error.detalle = detalle;
    throw error;
  }
  return respuesta;
}

const apiJson = async (ruta, opciones) => (await api(ruta, opciones)).json();

const postJson = (ruta, cuerpo) =>
  apiJson(ruta, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cuerpo),
  });

// --- carteles ---------------------------------------------------------------

function mostrarError(titulo, texto, detalleTecnico) {
  $("titulo-error").textContent = titulo;
  $("texto-error").textContent = texto;
  const detalle = $("detalle-error");
  detalle.textContent = detalleTecnico || "";
  detalle.classList.toggle("oculto", !detalleTecnico);
  $("btn-copiar-error").classList.toggle("oculto", !detalleTecnico);
  $("cartel-error").classList.remove("oculto");
  $("cartel-error").classList.add("error");
}

$("btn-cerrar-error").onclick = () => $("cartel-error").classList.add("oculto");
$("btn-copiar-error").onclick = () => {
  // Sin permiso de portapapeles esto rechaza; que falle en silencio deja
  // al usuario creyendo que copió.
  navigator.clipboard
    ?.writeText($("detalle-error").textContent)
    ?.catch(() => mostrarError("No se pudo copiar", "Seleccioná el texto y copialo a mano."));
};

function mostrarAvisos(lista) {
  // Los avisos llegan de tres caminos -- el análisis, un trabajo que
  // terminó bien, uno que falló -- y ninguno tiene otro lugar donde
  // aparecer: ni el del rectángulo del tamaño de la placa, ni los que
  // explican por qué no quedó ninguna pieza. `textContent` (no
  // `innerHTML`) porque un aviso puede traer el nombre del archivo, que no
  // es texto de confianza.
  const el = $("avisos");
  const hay = Boolean(lista && lista.length);
  el.textContent = hay ? lista.map((aviso) => `· ${aviso}`).join("\n") : "";
  el.classList.toggle("oculto", !hay);
}

function limpiarErroresDeCampo() {
  document.querySelectorAll("[data-error-de]").forEach((p) => {
    p.classList.add("oculto");
    p.closest(".campo")?.classList.remove("campo-con-error");
  });
}

function marcarCampo(campo, mensaje) {
  const p = document.querySelector(`[data-error-de="${campo}"]`);
  if (!p) return mostrarError("Un parámetro no sirve", `${campo}: ${mensaje}`);
  p.textContent = mensaje;
  p.classList.remove("oculto");
  p.closest(".campo")?.classList.add("campo-con-error");
  // El panel mide más de mil píxeles de alto y Acomodar está en la barra de
  // abajo: sin traerlo, el aviso se pinta fuera de la pantalla y el botón
  // parece no haber hecho nada. Justo el silencio que hay que evitar.
  p.scrollIntoView({ block: "center", behavior: "smooth" });
}

// --- elegir el archivo ------------------------------------------------------

$("btn-archivo").onclick = async () => {
  try {
    if (EN_ESCRITORIO) {
      // El diálogo nativo lo abre pywebview y devuelve una ruta de verdad.
      const rutas = await window.pywebview.api.elegir_archivo();
      if (!rutas || !rutas.length) return;
      await registrar(await postJson("/api/archivos/local", { ruta: rutas[0] }));
    } else {
      const entrada = document.createElement("input");
      entrada.type = "file";
      entrada.accept = ".dxf,.ai,.3dm";
      entrada.onchange = async () => {
        // Este handler corre en un evento posterior, así que queda FUERA del
        // try/catch que lo rodea: necesita el suyo.
        try {
          const datos = new FormData();
          datos.append("archivo", entrada.files[0]);
          await registrar(await apiJson("/api/archivos", { method: "POST", body: datos }));
        } catch (error) {
          mostrarError("No se pudo abrir el archivo", error.message);
        }
      };
      entrada.click();
    }
  } catch (error) {
    mostrarError("No se pudo abrir el archivo", error.message);
  }
};

async function registrar(fuente) {
  // Elegir un archivo nuevo tiene que dejar la pantalla como si el trabajo
  // anterior nunca hubiera existido. Antes esta función sólo pisaba
  // fuenteId/nombreArchivo/unidades y dejaba trabajoId, terminado, el
  // resultado y el botón Guardar apuntando al archivo viejo -- el bug real:
  // acomodás A, elegís B, la solapa Revisión sigue pidiendo el diagnóstico
  // de A, el resultado sigue mostrando las placas de A, y Guardar sigue
  // habilitado y baja el DXF de A ofreciéndolo como "B_acomodado.dxf".
  if (estado.terminado && !estado.guardado) {
    // Hay un acomodo que todavía no se guardó a ningún lado (el mismo caso
    // que `marcar_sin_guardar` le avisa al puente de escritorio para el
    // cierre de la ventana): perderlo en silencio por elegir otro archivo
    // es tan grave como perderlo al cerrar, así que se pregunta antes.
    //
    // `guardado` es lo que separa "hay un resultado" de "hay un resultado
    // que se va a perder". Sin esa distinción el cartel salía igual después
    // de guardar: el DXF ya estaba en la carpeta del usuario y el programa
    // le seguía avisando que lo iba a perder.
    const seguir = confirm(
      "El acomodo anterior todavía no se guardó y se va a perder si elegís " +
        "otro archivo. ¿Continuar de todos modos?"
    );
    if (!seguir) return;
  } else if (estado.trabajoId) {
    // Un trabajo corriendo (o recién arrancado) del archivo anterior no
    // tiene sentido si ya se eligió uno nuevo: cancelarlo libera el hilo/
    // proceso en vez de dejarlo trabajando para nadie.
    api(`/api/trabajos/${estado.trabajoId}/cancelar`, { method: "POST" }).catch(() => {});
  }
  if (estado.sondeo) clearInterval(estado.sondeo);

  estado.fuenteId = fuente.id;
  estado.nombreArchivo = fuente.nombre;
  estado.unidades = null;
  estado.trabajoId = null;
  estado.sondeo = null;
  estado.terminado = false;
  estado.guardado = false;
  estado.descartes = 0;
  if (EN_ESCRITORIO) window.pywebview?.api?.marcar_sin_guardar(false);

  $("nombre-archivo").textContent = fuente.nombre;
  $("resumen-archivo").classList.add("oculto");
  $("link-descartes").classList.add("oculto");
  mostrarAvisos([]);
  if (urlImagenActual) {
    URL.revokeObjectURL(urlImagenActual);
    urlImagenActual = null;
  }
  $("lienzo").innerHTML = "";
  aplicarZoom();
  $("btn-acomodar").classList.remove("oculto");
  $("btn-cancelar").classList.add("oculto");
  $("pista-avance").classList.add("oculto");
  $("texto-avance").classList.add("oculto");
  $("texto-restante").classList.add("oculto");
  estado.restante = null;
  mostrarEstimacion(null);
  $("resultado").classList.add("oculto");
  $("resultado").textContent = "";
  $("placa-actual").textContent = "";
  $("btn-guardar").disabled = true;

  await analizar();
}

// --- recortes ---------------------------------------------------------------

function dibujarRecortes() {
  const lista = $("lista-recortes");
  lista.innerHTML = "";
  estado.recortes.forEach((r, indice) => {
    const fila = document.createElement("li");
    const texto = document.createElement("span");
    texto.textContent =
      `${r.ancho} × ${r.alto} mm  ×${r.cantidad}` +
      (r.veta_cruzada ? " · veta cruzada" : "");
    const quitar = document.createElement("button");
    quitar.type = "button";
    quitar.className = "enlace";
    quitar.setAttribute(
      "aria-label", `Quitar el recorte de ${r.ancho} por ${r.alto}`
    );
    quitar.innerHTML =
      '<svg viewBox="0 0 16 16" class="icono" aria-hidden="true">' +
      '<path d="M4 4l8 8"></path><path d="M12 4l-8 8"></path></svg>';
    quitar.onclick = () => {
      estado.recortes.splice(indice, 1);
      dibujarRecortes();
    };
    fila.append(texto, quitar);
    lista.append(fila);
  });
  pedirEstimacion();
}

function abrirAltaRecorte(abierta) {
  $("alta-recorte").classList.toggle("oculto", !abierta);
  $("btn-agregar-recorte").classList.toggle("oculto", abierta);
  if (abierta) $("r-ancho").focus();
}

// Vaciar el alta es parte de cerrarla, la cierre quien la cierre. Cancelar
// sólo la escondía: los números quedaban adentro para la próxima vez que se
// abriera, y el aviso de "todavía no está en la lista" seguía pintado abajo
// hablando de un recorte que el usuario acababa de descartar.
function limpiarAltaRecorte() {
  $("r-ancho").value = "";
  $("r-alto").value = "";
  $("r-cantidad").value = "1";
  $("r-cruzada").checked = false;
  limpiarErroresDeCampo();
}

$("btn-agregar-recorte").onclick = () => abrirAltaRecorte(true);
$("btn-cancelar-recorte").onclick = () => {
  limpiarAltaRecorte();
  abrirAltaRecorte(false);
};

// Tipear las medidas no agrega nada hasta tocar el botón, y eso no se ve:
// un usuario cargó ancho y alto y apretó Acomodar directo. El trabajo salía
// contra placas nuevas, sin el pedazo y sin una palabra. Lo que devuelve
// esto es lo que quedó tipeado sin agregar, o `null` si no hay nada que
// perder -- el alta cerrada, o abierta y en blanco, que es un clic de más y
// no un error.
function recorteSinAgregar() {
  if ($("alta-recorte").classList.contains("oculto")) return null;
  const ancho = $("r-ancho").value.trim();
  const alto = $("r-alto").value.trim();
  if (!ancho && !alto) return null;
  return { ancho, alto, completo: Number(ancho) > 0 && Number(alto) > 0 };
}

// Sin un <form> alrededor no hay envío implícito: Enter no hacía nada y
// había que soltar el teclado para ir a buscar el botón con el mouse.
$("alta-recorte").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.tagName === "INPUT") {
    e.preventDefault();
    $("btn-confirmar-recorte").click();
  }
});

$("btn-confirmar-recorte").onclick = () => {
  const ancho = Number($("r-ancho").value);
  const alto = Number($("r-alto").value);
  const cantidad = Number($("r-cantidad").value);
  limpiarErroresDeCampo();
  if (!(ancho > 0) || !(alto > 0) || !(cantidad >= 1)) {
    return marcarCampo(
      "recortes",
      "poné un ancho y un alto mayores que cero, y al menos una unidad"
    );
  }
  estado.recortes.push({
    ancho,
    alto,
    cantidad,
    veta_cruzada: $("r-cruzada").checked,
  });
  limpiarAltaRecorte();
  abrirAltaRecorte(false);
  dibujarRecortes();
};

// En un material de veta libre la casilla no cambiaría nada, así que se
// apaga en vez de quedar marcable y muda. Los recortes YA cargados
// conservan su bandera: en un material libre no hace daño (todos los
// ángulos están permitidos igual), y si se vuelve a un material con veta
// tiene que seguir valiendo lo que el usuario dijo del pedazo.
let vetaPorMaterial = {};

function vetaDeLaCorrida() {
  return $("veta-respetar").checked ? "respetar" : "libre";
}

// Mira el control y no el material: con "no importa" elegido a mano sobre
// un fenólico, la casilla tampoco cambiaría nada.
function ajustarVetaCruzada() {
  const libre = vetaDeLaCorrida() === "libre";
  $("r-cruzada").disabled = libre;
  if (libre) $("r-cruzada").checked = false;
  $("etiqueta-cruzada").classList.toggle("deshabilitada", libre);
}

// El mismo número que `VETA_RESPETAR` en nesting/model/material.py. Está
// repetido para no preguntarle al servidor algo que no cambia; un test
// compara los dos.
const TOLERANCIA_VETA = 5;

// Lo que había en Posiciones antes de bloquearlo, para devolverlo al
// soltar. `null` mientras no está bloqueado.
let posicionesAntesDeVeta = null;

function respetaLaVeta(angulo) {
  const plegado = ((angulo % 180) + 180) % 180;
  return Math.min(plegado, 180 - plegado) <= TOLERANCIA_VETA + 1e-9;
}

function bloquearPosiciones() {
  if (posicionesAntesDeVeta === null) posicionesAntesDeVeta = $("posiciones").value;
  $("posiciones").value = "veta";
  $("posiciones").disabled = true;
  $("campo-angulos").classList.add("oculto");
  $("nota-veta").classList.remove("oculto");
}

function soltarPosiciones() {
  if (posicionesAntesDeVeta !== null) $("posiciones").value = posicionesAntesDeVeta;
  posicionesAntesDeVeta = null;
  $("posiciones").disabled = false;
  $("campo-angulos").classList.toggle("oculto", $("posiciones").value !== "personalizado");
  $("nota-veta").classList.add("oculto");
}

// Deja el control en `veta` y todo lo que depende de él al día. No
// pregunta nada: quien tiene que preguntar antes es `pedirVeta`.
function ponerVeta(veta) {
  $(veta === "respetar" ? "veta-respetar" : "veta-libre").checked = true;
  if (veta === "respetar") bloquearPosiciones();
  else soltarPosiciones();
  ajustarVetaCruzada();
}

// Lo que pasa cuando el USUARIO cambia algo: elige un material o marca un
// radio. Si pasar a "respetar" descartaría ángulos que eligió, se lo dice
// en ese momento y no al tocar Acomodar, después de haber cargado todo.
// Ya bloqueado (`posicionesAntesDeVeta !== null`) no hay nada que
// descartar. Con ángulos inválidos tampoco se pregunta: se bloquea, y el
// texto queda guardado para cuando se suelte.
function pedirVeta(veta, origen) {
  if (veta === "respetar" && posicionesAntesDeVeta === null && angulosValidos()) {
    const angulos = angulosElegidos();
    if (angulos.some((a) => !respetaLaVeta(a))) {
      mostrarCartelVeta(angulos.length, origen);
      return;
    }
  }
  ponerVeta(veta);
}

function mostrarCartelVeta(cuantas, origen) {
  $("titulo-veta").textContent = origen === "material"
    ? "Este material respeta la veta"
    : "Respetar la veta limita los giros";
  $("texto-veta").textContent =
    `Sólo se puede girar a 0° y 180°. Tenías elegidas ${cuantas} posiciones.`;
  $("cartel-veta").classList.remove("oculto");
}

$("btn-veta-respetar").onclick = () => {
  $("cartel-veta").classList.add("oculto");
  ponerVeta("respetar");
};
$("btn-veta-libre").onclick = () => {
  $("cartel-veta").classList.add("oculto");
  ponerVeta("libre");
};

$("material").addEventListener("change", () =>
  pedirVeta(vetaPorMaterial[$("material").value], "material")
);
["veta-respetar", "veta-libre"].forEach((id) =>
  $(id).addEventListener("change", () => pedirVeta(vetaDeLaCorrida(), "control"))
);

// --- analizar ---------------------------------------------------------------

async function analizar() {
  try {
    const analisis = await postJson("/api/analizar", {
      fuente_id: estado.fuenteId,
      unidades: estado.unidades,
      tol_cierre: Number($("tol-cierre").value),
    });
    estado.descartes = analisis.descartes.length;
    $("cuenta-piezas").textContent = analisis.piezas;
    $("resumen-archivo").classList.remove("oculto");
    const link = $("link-descartes");
    link.textContent = `· ${analisis.descartes.length} descartes`;
    link.classList.toggle("oculto", analisis.descartes.length === 0);
    mostrarAvisos(analisis.avisos);
    mostrarRevision();
    pedirEstimacion();
  } catch (error) {
    if (error.estado === 409 && error.detalle?.faltan_unidades) {
      // No es un error: es una pregunta. Por eso tiene cartel propio.
      $("cartel-unidades").classList.remove("oculto");
      return;
    }
    mostrarError("No se pudo leer el archivo", error.message);
  }
}

document.querySelectorAll("[data-unidad]").forEach((boton) => {
  boton.onclick = async () => {
    estado.unidades = boton.dataset.unidad;
    $("cartel-unidades").classList.add("oculto");
    await analizar();
  };
});

// --- solapas ----------------------------------------------------------------

// Un <img> es un pedido nativo del navegador: no puede llevar el header
// `X-Token`, y el middleware de la API rechaza con 401 todo lo que no lo
// traiga. Por eso el archivo se trae con `api()` (que sí manda el token) y
// se arma un blob local -- ver la nota crítica al pie del archivo.
let urlImagenActual = null;

// Dos solapas pueden pedir su imagen casi al mismo tiempo (por ejemplo el
// usuario pasa de "revisión" a "previsualización" antes de que la primera
// responda) y las respuestas pueden llegar en cualquier orden. `pedidoImagen`
// numera cada llamada: si al resolver ya no es la última que se hizo, la
// respuesta llegó tarde y se descarta -- se libera el blob propio y no se
// toca el lienzo, que ya le pertenece a un pedido más nuevo.
let pedidoImagen = 0;

// Todo lo que deja el lienzo en texto pasa por acá, para que ningún camino
// se olvide de apagar los controles de zoom: quedarían prendidos sobre un
// texto, ofreciendo ampliar la nada. El otro camino que vacía el lienzo es
// `registrar()`, que llama a `aplicarZoom()` por su cuenta porque ahí no va
// ningún texto.
function mensajeEnLienzo(texto) {
  $("lienzo").textContent = texto;
  aplicarZoom();
}

// La revisión existe en dos momentos y son dos dibujos distintos. El del
// análisis está al segundo de elegir el archivo, que es cuando sirve para
// decidir si vale la pena acomodar. El del acomodo conoce el material, así
// que marca además los rectángulos del tamaño exacto de la placa. Mientras
// haya trabajo gana el del trabajo, que es el más completo.
function rutaDeImagen(nombre) {
  if (estado.trabajoId) return `/api/trabajos/${estado.trabajoId}/${nombre}`;
  if (nombre === "diagnostico.png" && estado.fuenteId) {
    return `/api/archivos/${estado.fuenteId}/${nombre}`;
  }
  return null;
}

async function mostrarImagen(nombre) {
  const ruta = rutaDeImagen(nombre);
  if (!ruta) {
    // La previsualización es el resultado de un acomodo: antes de que haya
    // uno no existe. Sin este texto el lienzo queda gris y mudo.
    return mensajeEnLienzo(
      estado.fuenteId
        ? "Todavía no hay nada acomodado."
        : "Elegí un archivo para empezar."
    );
  }
  const miPedido = ++pedidoImagen;
  try {
    const blob = await (await api(ruta)).blob();
    const url = URL.createObjectURL(blob);
    if (miPedido !== pedidoImagen) {
      URL.revokeObjectURL(url);
      return;
    }
    if (urlImagenActual) URL.revokeObjectURL(urlImagenActual);
    urlImagenActual = url;
    $("lienzo").innerHTML = "";
    const img = new Image();
    img.alt = nombre === "preview.png" ? "Cómo quedó el acomodo" : "Qué se descartó";
    // Cada imagen arranca ajustada al panel. Heredar el zoom de la anterior
    // dejaría al usuario mirando una esquina de un dibujo distinto sin
    // entender qué está viendo.
    zoom = null;
    img.onload = aplicarZoom;
    img.src = url;
    $("lienzo").append(img);
    aplicarZoom();
  } catch (error) {
    if (miPedido !== pedidoImagen) return;
    if (error.estado === 409) {
      // No es un bug: el archivo todavía no existe (por ejemplo la
      // previsualización antes de acomodar, o la revisión de una fuente
      // que no llegó a analizarse). Por eso no usa el cartel de error,
      // sólo deja el lienzo en un estado legible.
      mensajeEnLienzo("Todavía no hay imagen para mostrar.");
      return;
    }
    mostrarError("No se pudo mostrar la imagen", error.message);
  }
}

// --- zoom -------------------------------------------------------------------

// El diagnóstico se dibuja a 1800 px de ancho y el panel mide menos de 300:
// las medidas de cada descarte quedan ilegibles justo cuando hay muchos, que
// es cuando más hace falta leerlas.

const PASOS_ZOOM = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 6];
// `null` es "ajustar al panel", que no es un número fijo: depende del tamaño
// de la ventana y del alto de la imagen. Por eso no se guarda como 1.0.
let zoom = null;

const imagenDelLienzo = () => $("lienzo").querySelector("img");

function escalaAjustada(img) {
  return img.naturalWidth ? img.clientWidth / img.naturalWidth : 1;
}

function aplicarZoom() {
  const img = imagenDelLienzo();
  $("controles-zoom").classList.toggle("oculto", !img);
  if (!img) return;
  const lienzo = $("lienzo");
  lienzo.classList.toggle("ampliado", zoom !== null);
  img.style.width = zoom === null ? "" : `${img.naturalWidth * zoom}px`;
  $("nivel-zoom").textContent =
    `${Math.round((zoom ?? escalaAjustada(img)) * 100)}%`;
}

function proximoPaso(desde, direccion) {
  const margen = 0.01;
  const candidatos =
    direccion > 0
      ? PASOS_ZOOM.filter((p) => p > desde + margen)
      : PASOS_ZOOM.filter((p) => p < desde - margen).reverse();
  return candidatos.length ? candidatos[0] : null;
}

const ZOOM_MIN = 0.1;
const ZOOM_MAX = PASOS_ZOOM[PASOS_ZOOM.length - 1];

// Cuánto zoom por píxel de scroll. Con 0.0015, una muesca de rueda típica
// (100 px) mueve el zoom un 16% y un gesto de trackpad completo recorre el
// rango sin pasarse. Es un número de tacto: se ajusta probándolo.
const SENSIBILIDAD = 0.0015;

// `deltaY` no viene en píxeles en todos lados: Firefox reporta líneas
// (deltaMode 1) y hay quien reporta páginas (2). Sin normalizar, el mismo
// gesto salta distinto en cada navegador.
const PIXELES_POR_MODO = [1, 16, 100];
function enPixeles(e) {
  return e.deltaY * (PIXELES_POR_MODO[e.deltaMode] ?? 1);
}

// El anclaje al cursor lo comparten la rueda y los botones: sin esto el
// zoom se va siempre al centro y perseguir un detalle es un juego de
// paciencia.
function aplicarNuevoZoom(siguiente, clienteX, clienteY) {
  const img = imagenDelLienzo();
  if (!img || siguiente === null) return;
  const lienzo = $("lienzo");
  const antes = zoom ?? escalaAjustada(img);
  if (siguiente === antes) return;

  const caja = img.getBoundingClientRect();
  const enImagenX = (clienteX - caja.left) / antes;
  const enImagenY = (clienteY - caja.top) / antes;

  zoom = siguiente;
  aplicarZoom();

  const nueva = img.getBoundingClientRect();
  lienzo.scrollLeft += nueva.left + enImagenX * zoom - clienteX;
  lienzo.scrollTop += nueva.top + enImagenY * zoom - clienteY;
}

// Los botones y el doble clic siguen con la escalera: ahí los números
// redondos sirven, y un clic es un paso, no un gesto.
function acercar(direccion, clienteX, clienteY) {
  const img = imagenDelLienzo();
  if (!img) return;
  const antes = zoom ?? escalaAjustada(img);
  aplicarNuevoZoom(proximoPaso(antes, direccion), clienteX, clienteY);
}

function zoomContinuo(delta, clienteX, clienteY) {
  const img = imagenDelLienzo();
  if (!img) return;
  const antes = zoom ?? escalaAjustada(img);
  const siguiente = Math.min(
    ZOOM_MAX, Math.max(ZOOM_MIN, antes * Math.exp(-delta * SENSIBILIDAD))
  );
  aplicarNuevoZoom(siguiente, clienteX, clienteY);
}

function centroDelLienzo() {
  const c = $("lienzo").getBoundingClientRect();
  return [c.left + c.width / 2, c.top + c.height / 2];
}

$("btn-acercar").onclick = () => acercar(1, ...centroDelLienzo());
$("btn-alejar").onclick = () => acercar(-1, ...centroDelLienzo());
$("btn-ajustar").onclick = () => {
  zoom = null;
  aplicarZoom();
};

$("lienzo").addEventListener("wheel", (e) => {
  if (!imagenDelLienzo()) return;
  // `preventDefault` sólo cuando hay imagen: si no, se come el scroll del
  // mensaje de texto que el lienzo muestra cuando todavía no hay nada.
  e.preventDefault();
  zoomContinuo(enPixeles(e), e.clientX, e.clientY);
}, { passive: false });

$("lienzo").ondblclick = () => {
  const img = imagenDelLienzo();
  if (!img) return;
  zoom = zoom === null ? 1 : null;
  aplicarZoom();
};

// Arrastrar para mover. Con la imagen a 6x, llegar a una esquina con las
// barras de scroll es incómodo; agarrarla y tirar es lo que uno espera de
// un plano.
let arrastre = null;
$("lienzo").addEventListener("pointerdown", (e) => {
  if (zoom === null || !imagenDelLienzo()) return;
  const lienzo = $("lienzo");
  arrastre = { x: e.clientX, y: e.clientY, sx: lienzo.scrollLeft, sy: lienzo.scrollTop };
  lienzo.setPointerCapture(e.pointerId);
  lienzo.classList.add("agarrando");
  e.preventDefault();
});
$("lienzo").addEventListener("pointermove", (e) => {
  if (!arrastre) return;
  $("lienzo").scrollLeft = arrastre.sx - (e.clientX - arrastre.x);
  $("lienzo").scrollTop = arrastre.sy - (e.clientY - arrastre.y);
});
for (const fin of ["pointerup", "pointercancel"]) {
  $("lienzo").addEventListener(fin, (e) => {
    if (!arrastre) return;
    arrastre = null;
    $("lienzo").releasePointerCapture(e.pointerId);
    $("lienzo").classList.remove("agarrando");
  });
}

// --- solapas (continuación) -------------------------------------------------

const mostrarRevision = () => {
  $("tab-revision").classList.add("activa");
  $("tab-preview").classList.remove("activa");
  mostrarImagen("diagnostico.png");
};

$("tab-preview").onclick = () => {
  $("tab-preview").classList.add("activa");
  $("tab-revision").classList.remove("activa");
  mostrarImagen("preview.png");
};
$("tab-revision").onclick = mostrarRevision;
$("link-descartes").onclick = mostrarRevision;

// --- acomodar ---------------------------------------------------------------

function parametros() {
  return {
    material: $("material").value,
    sep: Number($("sep").value),
    borde: Number($("borde").value),
    copias: Number($("copias").value),
    angulos: angulosElegidos(),
    espejo: $("espejo").checked,
    unidades: estado.unidades,
    tol_cierre: Number($("tol-cierre").value),
    resolucion: Number($("resolucion").value),
    esfuerzo: $("esfuerzo").value,
    nucleos: Number($("nucleos").value) || null,
    recortes: estado.recortes,
    veta: vetaDeLaCorrida(),
  };
}

// Las posiciones son el camino normal: 4, 8 o 16 repartidas en la vuelta
// entera. El campo de texto libre queda para "Personalizado", que es el
// único que puede traer basura -- un "9o" en vez de "90" daba `NaN`,
// `JSON.stringify` lo mandaba como `null`, y el servidor devolvía el 422
// crudo de pydantic. Se corta acá, con el mismo cartel debajo del campo
// que usan los demás parámetros.
function angulosElegidos() {
  const posiciones = $("posiciones").value;
  if (posiciones === "veta") return [0, 180];
  if (posiciones !== "personalizado") {
    const n = Number(posiciones);
    return Array.from({ length: n }, (_, i) => (i * 360) / n);
  }
  return $("angulos")
    .value.split(",")
    .map((t) => t.trim())
    .filter((t) => t !== "")
    .map(Number);
}

function angulosValidos() {
  const lista = angulosElegidos();
  return lista.length > 0 && lista.every(Number.isFinite);
}

$("posiciones").onchange = () => {
  $("campo-angulos").classList.toggle(
    "oculto", $("posiciones").value !== "personalizado"
  );
};

function corriendo(si) {
  $("btn-acomodar").classList.toggle("oculto", si);
  $("btn-cancelar").classList.toggle("oculto", !si);
  $("pista-avance").classList.toggle("oculto", !si);
  $("texto-avance").classList.toggle("oculto", !si);
  $("texto-restante").classList.toggle("oculto", !si);
  $("tiempo-estimado").classList.toggle("oculto", si || !$("tiempo-estimado").textContent);
  $("resultado").classList.toggle("oculto", si);
  $("btn-guardar").disabled = si || !estado.terminado;
}

$("btn-acomodar").onclick = async () => {
  if (!estado.fuenteId) {
    return mostrarError("Falta el archivo", "Elegí un archivo antes de acomodar.");
  }
  limpiarErroresDeCampo();
  const pendiente = recorteSinAgregar();
  if (pendiente) {
    return marcarCampo(
      "recortes",
      pendiente.completo
        ? `el recorte de ${pendiente.ancho} × ${pendiente.alto} mm todavía no ` +
          `está en la lista: agregalo a la lista o cancelalo`
        : "te quedó un recorte a medio cargar: completalo y agregalo a la " +
          "lista, o cancelalo"
    );
  }
  if (!angulosValidos()) {
    return marcarCampo(
      "angulos",
      "poné números separados por comas, por ejemplo 0,90,180,270"
    );
  }
  estado.terminado = false;
  mostrarAvisos([]);
  try {
    const creado = await postJson("/api/trabajos", {
      fuente_id: estado.fuenteId,
      params: parametros(),
    });
    estado.trabajoId = creado.id;
    estado.restante = null;
    $("texto-restante").textContent = "Calculando el tiempo…";
    corriendo(true);
    estado.sondeo = setInterval(sondear, SONDEO_MS);
  } catch (error) {
    if (error.estado === 422 && error.detalle?.campo) {
      return marcarCampo(error.detalle.campo, error.detalle.mensaje);
    }
    mostrarError("No se pudo arrancar", error.message);
  }
};

$("btn-cancelar").onclick = () =>
  api(`/api/trabajos/${estado.trabajoId}/cancelar`, { method: "POST" }).catch((error) =>
    mostrarError("No se pudo cancelar", error.message)
  );

async function sondear() {
  let t;
  try {
    t = await apiJson(`/api/trabajos/${estado.trabajoId}`);
  } catch (error) {
    clearInterval(estado.sondeo);
    corriendo(false);
    return mostrarError("Se perdió el trabajo", error.message);
  }

  if (t.avance) $("texto-avance").textContent = textoDeAvance(t.avance);
  if (t.estado === "corriendo") actualizarRestante(t.restante_s);
  if (t.avance && !t.avance.compactando) {
    // El conteo de `ubicadas` se reinicia en cada intento nuevo (ver
    // nesting/engine/packer.py): una barra armada sólo con
    // ubicadas/totales retrocedería justo ahí, y eso es peor que no tener
    // barra. Por eso el porcentaje también mira qué intento es.
    const a = t.avance;
    const hechos = (a.intento - 1) * a.totales + a.ubicadas;
    const porcentaje = a.totales ? (100 * hechos) / (a.intentos * a.totales) : 0;
    $("barra-avance").style.width = `${porcentaje}%`;
  }

  if (t.estado === "corriendo" || t.estado === "pendiente") return;

  clearInterval(estado.sondeo);
  corriendo(false);

  if (t.estado === "listo") return terminar(t);
  if (t.estado === "cancelado") {
    $("resultado").textContent = "Cancelado. No se escribió ningún archivo.";
    $("resultado").classList.remove("oculto");
    return;
  }
  if (t.estado === "error") {
    mostrarRevision();
    // Los avisos que el corredor llegó a calcular antes de fallar -- según
    // su propio comentario, "la explicación de por qué no quedó nada" -- no
    // tienen ningún otro lugar donde aparecer.
    mostrarAvisos(t.avisos);
    if (t.es_bug) {
      return mostrarError(
        "Se rompió el programa",
        "Esto no es un problema de tu dibujo: es un error nuestro. " +
          "Copiá el detalle y pasalo.",
        t.detalle_tecnico
      );
    }
    mostrarError("No se pudo acomodar", t.error);
  }
}

function textoDeAvance(a) {
  if (a.compactando) return "Compactando la última placa…";
  if (a.combinaciones) {
    return (
      `Probando combinaciones ${a.combinaciones_hechas} de ${a.combinaciones} · ` +
      `placa mínima hasta ahora: ${a.placa_minima}`
    );
  }
  const intento = a.intentos > 1 ? `Intento ${a.intento} de ${a.intentos} · ` : "";
  return `${intento}ubicadas ${a.ubicadas} de ${a.totales} · placa ${a.placa}`;
}

// --- tiempo -----------------------------------------------------------------

// Para no fingir una precisión que no hay: de a 5 minutos arriba de 10, de
// a 1 entre 2 y 10, y abajo de 2 un "menos de 2 min", que acá es el 0. La
// hora de fin sale de este número ya redondeado y no del crudo, para que
// "9 min" y "termina ~17:42" cierren entre sí.
function minutosRedondeados(segundos) {
  if (segundos < 120) return 0;
  if (segundos <= 600) return Math.round(segundos / 60);
  return Math.max(10, Math.round(segundos / 300) * 5);
}

// Con 0 no hay hora de fin: "termina ~17:33" a las 17:33 diría que ya
// terminó.
function textoDeRestante(minutos, ahora) {
  if (minutos === 0) return "Faltan menos de 2 min";
  const fin = new Date(ahora.getTime() + minutos * 60000);
  const hh = String(fin.getHours()).padStart(2, "0");
  const mm = String(fin.getMinutes()).padStart(2, "0");
  return `Faltan aprox. ${minutos} min · termina ~${hh}:${mm}`;
}

const SUBIDA_SOSTENIDA_MS = 5000;

// El número mostrado baja libremente, pero sólo sube si los valores más
// altos se sostienen 5 segundos seguidos. Un número que salta de 8 a 12 y
// vuelve a 8 es peor que uno que se queda en 8: la gente planifica con él.
function estabilizar(previo, nuevo, ahora) {
  if (!previo || nuevo <= previo.mostrado) return { mostrado: nuevo, subidaDesde: null };
  const desde = previo.subidaDesde ?? ahora;
  if (ahora - desde >= SUBIDA_SOSTENIDA_MS) return { mostrado: nuevo, subidaDesde: null };
  return { mostrado: previo.mostrado, subidaDesde: desde };
}

// El servidor manda `null` durante los primeros 5 segundos o las primeras
// 20 consultas: antes de eso no hay datos, y un número inventado es peor
// que decir que se está calculando.
function actualizarRestante(restanteS) {
  if (typeof restanteS !== "number") {
    $("texto-restante").textContent = "Calculando el tiempo…";
    return;
  }
  estado.restante = estabilizar(estado.restante, minutosRedondeados(restanteS), Date.now());
  $("texto-restante").textContent = textoDeRestante(estado.restante.mostrado, new Date());
}

function textoDeTarda(minutos) {
  return minutos === 0 ? "Tarda menos de 2 min" : `Tarda aprox. ${minutos} min`;
}

// Quien elige 8 posiciones no sabe que acaba de quintuplicar la espera: la
// banqueta alta tarda 126 s con la veta y 651 s con giro libre y 8
// posiciones. Por eso el número se recalcula al cambiar cualquiera de las
// opciones que pesan, 400 ms después del último cambio para no pedir uno
// por cada tecla.
const ESPERA_ESTIMACION_MS = 400;
const CONTROLES_QUE_PESAN = ["posiciones", "angulos", "espejo", "esfuerzo", "resolucion", "material", "veta-respetar", "veta-libre", "copias"];
let temporizadorEstimacion = null;
let numeroDeEstimacion = 0;

function pedirEstimacion() {
  clearTimeout(temporizadorEstimacion);
  temporizadorEstimacion = setTimeout(calcularEstimacion, ESPERA_ESTIMACION_MS);
}

// Mientras calcula deja el valor anterior. No pide nada sin archivo ni con
// un trabajo corriendo: la prueba de una consulta le robaría CPU al
// trabajo. Un error -- un 422 por un ángulo a medio tipear, un 500 -- no
// abre ningún cartel: es un número de ayuda, y Acomodar va a dar el error
// de verdad si lo hay.
async function calcularEstimacion() {
  if (!estado.fuenteId || $("btn-acomodar").classList.contains("oculto")) return;
  const numero = ++numeroDeEstimacion;
  let segundos = null;
  try {
    const respuesta = await postJson("/api/estimar", {
      fuente_id: estado.fuenteId,
      params: parametros(),
    });
    segundos = respuesta.segundos;
  } catch (_) {
    segundos = null;
  }
  if (numero !== numeroDeEstimacion) return;
  mostrarEstimacion(segundos);
}

function mostrarEstimacion(segundos) {
  const lugar = $("tiempo-estimado");
  if (typeof segundos !== "number") {
    lugar.textContent = "";
    lugar.classList.add("oculto");
    return;
  }
  lugar.textContent = textoDeTarda(minutosRedondeados(segundos));
  lugar.classList.remove("oculto");
}

// El evento va en una variable y no como literal a propósito: los tests
// ubican los handlers en línea por su `addEventListener("change", ...)`, y
// un literal acá les ganaría de mano a los que buscan.
for (const id of CONTROLES_QUE_PESAN) {
  for (const evento of ["input", "change"]) $(id).addEventListener(evento, pedirEstimacion);
}

function terminar(t) {
  estado.terminado = true;
  estado.guardado = false;
  $("btn-guardar").disabled = false;
  if (EN_ESCRITORIO) {
    // El DXF vive en una carpeta temporal hasta que el usuario lo guarda.
    window.pywebview?.api?.marcar_sin_guardar(true);
  }
  const r = t.resultado;
  const nuevas = r.placas - r.recortes_usados;
  const placas =
    r.recortes_usados > 0
      ? `${r.placas} placa${r.placas === 1 ? "" : "s"} (${r.recortes_usados} recorte${
          r.recortes_usados === 1 ? "" : "s"
        } + ${nuevas} nueva${nuevas === 1 ? "" : "s"})`
      : r.placas === 1
        ? "1 placa"
        : `${r.placas} placas`;
  $("resultado").innerHTML =
    `<strong>${placas}</strong> · <strong>${(100 * r.total).toFixed(1)}%</strong> ` +
    `aprovechado · sobrante <strong>${r.sobrante_mm.toFixed(0)} mm</strong> · ` +
    `<strong>${r.material_ultima_placa_m2.toFixed(3)} m²</strong> en la última placa`;
  $("resultado").classList.remove("oculto");
  $("placa-actual").textContent = `${r.placas} placa${r.placas === 1 ? "" : "s"}`;
  $("tab-preview").click();
  mostrarAvisos(t.avisos);
}

// --- guardar ----------------------------------------------------------------

// Un solo lugar donde el programa pasa a considerar el acomodo a salvo, para
// que los dos caminos de guardado (diálogo nativo y descarga del navegador)
// no puedan quedar desalineados. Lo llaman recién cuando el archivo está
// escrito: si el usuario cancela el "Guardar como", no se llama.
function marcarGuardado() {
  if (!estado.guardado) $("resultado").insertAdjacentHTML("beforeend", " · guardado");
  estado.guardado = true;
  if (EN_ESCRITORIO) window.pywebview?.api?.marcar_sin_guardar(false);
}

$("btn-guardar").onclick = async () => {
  const url = `/api/trabajos/${estado.trabajoId}/salida.dxf`;
  const sugerido = (estado.nombreArchivo || "salida").replace(/\.[^.]+$/, "") + "_acomodado.dxf";
  if (EN_ESCRITORIO) {
    // Diálogo nativo: el usuario elige la carpeta de su proyecto, que es
    // donde este archivo tiene que ir. Va con su propio try/catch: es el
    // modo principal del programa, y sin él un fallo al guardar deja la
    // pantalla igual que si no hubieras apretado nada.
    try {
      const destino = await window.pywebview.api.elegir_destino(sugerido);
      if (!destino) return;
      const datos = new Uint8Array(await (await api(url)).arrayBuffer());
      await window.pywebview.api.guardar(destino, Array.from(datos));
      marcarGuardado();
    } catch (error) {
      mostrarError("No se pudo guardar", error.message);
    }
    return;
  }
  // Mismo problema que en mostrarImagen(): un <a download> tampoco lleva
  // cabeceras, así que el archivo se trae con `api()` y se descarga desde
  // un blob local en vez de apuntar el href directo a la ruta de la API.
  let urlBlob;
  try {
    const blob = await (await api(url)).blob();
    urlBlob = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = urlBlob;
    a.download = sugerido;
    a.click();
    marcarGuardado();
  } catch (error) {
    mostrarError("No se pudo guardar", error.message);
  } finally {
    // Revocar en el siguiente turno: hacerlo antes de que el navegador haya
    // arrancado la descarga la corta en algunos navegadores. Si algo falló
    // después de crear el blob, esto también lo libera.
    if (urlBlob) setTimeout(() => URL.revokeObjectURL(urlBlob), 0);
  }
};

// --- pantalla de materiales ---------------------------------------------

// El flujo principal sólo sabe mostrar y ocultar la pantalla: qué hay
// adentro (la tabla, el alta, el borrado) es de `materiales.js`, que se
// engancha llamando a `window.__nesting.mostrarMateriales`.
// Las dos mitades del cambio de pantalla viven juntas a propósito. Cuando
// "mostrar" estaba acá y "volver" en materiales.js, cada cosa que se apagaba
// al entrar había que acordarse de prenderla en el otro archivo -- y no pasó:
// el botón que abre el catálogo se quedaba visible adentro de la pantalla de
// materiales, ofreciendo ir a donde el usuario ya estaba. Hoy ese botón vive
// al lado del selector de material, o sea adentro de la pantalla principal:
// se apaga con ella y no hay una tercera cosa que acordarse de apagar.
function mostrarPantalla(cual) {
  const enMateriales = cual === "materiales";
  $("pantalla-principal").classList.toggle("oculto", enMateriales);
  $("pantalla-materiales").classList.toggle("oculto", !enMateriales);
}

const mostrarMateriales = () => mostrarPantalla("materiales");
const mostrarPrincipal = () => mostrarPantalla("principal");

$("btn-materiales").onclick = mostrarMateriales;

// --- arranque ---------------------------------------------------------------

// El material que más se corta. Se elige por nombre y no por posición:
// el catálogo se guarda en orden alfabético, así que "el primero de la
// lista" ya cambió una vez y volvería a cambiar con cada material nuevo.
const MATERIAL_PREFERIDO = "mdf15";

async function refrescarMateriales() {
  const datos = await apiJson("/api/materiales");
  const select = $("material");
  const elegido = select.value;
  select.innerHTML = "";
  for (const m of datos.materiales) {
    const opcion = document.createElement("option");
    opcion.value = m.nombre;
    opcion.textContent = `${m.nombre} — ${m.ancho} × ${m.alto}`;
    select.append(opcion);
  }
  // El preferido se puede borrar desde la pantalla de materiales. Sin este
  // `some`, `select.value = "mdf15"` contra un catálogo que ya no lo tiene
  // deja el selector en "" y Acomodar sale sin material.
  const hayPreferido = datos.materiales.some((m) => m.nombre === MATERIAL_PREFERIDO);
  if (elegido) select.value = elegido;
  else if (hayPreferido) select.value = MATERIAL_PREFERIDO;
  vetaPorMaterial = Object.fromEntries(
    datos.materiales.map((m) => [m.nombre, m.veta])
  );
  // Sin preguntar: refrescar pasa al arrancar y después de editar el
  // catálogo, y en los dos casos el control tiene que decir lo que dice el
  // material. El cartel es para cuando el usuario cambia algo a mano.
  ponerVeta(vetaPorMaterial[select.value] ?? "libre");
  return datos.materiales;
}

// Cuántos núcleos hay y hasta cuántos se pueden usar. Si la ruta falla, el
// desplegable queda vacío y `parametros()` manda `null`: el servidor usa
// su valor por omisión, que es el mismo que este desplegable mostraría.
async function cargarSistema() {
  const datos = await apiJson("/api/sistema");
  const select = $("nucleos");
  select.innerHTML = "";
  for (let n = 1; n <= datos.tope; n++) {
    const opcion = document.createElement("option");
    opcion.value = String(n);
    opcion.textContent = String(n);
    select.append(opcion);
  }
  select.value = String(datos.omision);
  $("nucleos-total").textContent = `de ${datos.nucleos}`;
}

window.__nesting = {
  api,
  apiJson,
  postJson,
  estado,
  refrescarMateriales,
  mostrarMateriales,
  mostrarPrincipal,
  mostrarError,
  dibujarRecortes,
  $,
};

refrescarMateriales().catch((error) =>
  mostrarError("No se pudo leer el catálogo de materiales", error.message)
);
cargarSistema().catch((error) =>
  mostrarError("No se pudo saber cuántos núcleos tiene la máquina", error.message)
);
