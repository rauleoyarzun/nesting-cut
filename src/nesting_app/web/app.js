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
  $("resultado").classList.add("oculto");
  $("resultado").textContent = "";
  $("placa-actual").textContent = "";
  $("btn-guardar").disabled = true;

  await analizar();
}

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

function acercar(direccion, clienteX, clienteY) {
  const img = imagenDelLienzo();
  if (!img) return;
  const lienzo = $("lienzo");
  const antes = zoom ?? escalaAjustada(img);
  const siguiente = proximoPaso(antes, direccion);
  if (siguiente === null) return;

  // Qué punto de la imagen está bajo el cursor, medido en píxeles de la
  // imagen. Sin esto el zoom se va siempre al centro y perseguir un detalle
  // se vuelve un juego de paciencia.
  const caja = img.getBoundingClientRect();
  const enImagenX = (clienteX - caja.left) / antes;
  const enImagenY = (clienteY - caja.top) / antes;

  zoom = siguiente;
  aplicarZoom();

  const nueva = img.getBoundingClientRect();
  lienzo.scrollLeft += nueva.left + enImagenX * zoom - clienteX;
  lienzo.scrollTop += nueva.top + enImagenY * zoom - clienteY;
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
  acercar(e.deltaY < 0 ? 1 : -1, e.clientX, e.clientY);
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
    angulos: angulosDelCampo(),
    espejo: $("espejo").checked,
    unidades: estado.unidades,
    tol_cierre: Number($("tol-cierre").value),
    resolucion: Number($("resolucion").value),
    esfuerzo: $("esfuerzo").value,
  };
}

// Los ángulos son el único parámetro que se tipea como texto libre. Un
// "9o" en vez de "90" daba `NaN`, `JSON.stringify` lo mandaba como `null`,
// y el servidor devolvía el 422 crudo de pydantic. Se corta acá, con el
// mismo cartel debajo del campo que usan los demás parámetros.
function angulosDelCampo() {
  return $("angulos")
    .value.split(",")
    .map((t) => t.trim())
    .filter((t) => t !== "")
    .map(Number);
}

function angulosValidos() {
  const lista = angulosDelCampo();
  return lista.length > 0 && lista.every(Number.isFinite);
}

function corriendo(si) {
  $("btn-acomodar").classList.toggle("oculto", si);
  $("btn-cancelar").classList.toggle("oculto", !si);
  $("pista-avance").classList.toggle("oculto", !si);
  $("texto-avance").classList.toggle("oculto", !si);
  $("resultado").classList.toggle("oculto", si);
  $("btn-guardar").disabled = si || !estado.terminado;
}

$("btn-acomodar").onclick = async () => {
  if (!estado.fuenteId) {
    return mostrarError("Falta el archivo", "Elegí un archivo antes de acomodar.");
  }
  limpiarErroresDeCampo();
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
  const intento = a.intentos > 1 ? `Intento ${a.intento} de ${a.intentos} · ` : "";
  return `${intento}ubicadas ${a.ubicadas} de ${a.totales} · placa ${a.placa}`;
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
  const placas = r.placas === 1 ? "1 placa" : `${r.placas} placas`;
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
  if (elegido) select.value = elegido;
  return datos.materiales;
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
  $,
};

refrescarMateriales().catch((error) =>
  mostrarError("No se pudo leer el catálogo de materiales", error.message)
);
