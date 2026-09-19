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
  descartes: 0,
};

// --- el cliente HTTP --------------------------------------------------------

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
    const error = new Error(typeof detalle === "string" ? detalle : "");
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
$("btn-copiar-error").onclick = () =>
  navigator.clipboard?.writeText($("detalle-error").textContent);

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
        const datos = new FormData();
        datos.append("archivo", entrada.files[0]);
        await registrar(await apiJson("/api/archivos", { method: "POST", body: datos }));
      };
      entrada.click();
    }
  } catch (error) {
    mostrarError("No se pudo abrir el archivo", error.message);
  }
};

async function registrar(fuente) {
  estado.fuenteId = fuente.id;
  estado.nombreArchivo = fuente.nombre;
  estado.unidades = null;
  $("nombre-archivo").textContent = fuente.nombre;
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

async function mostrarImagen(nombre) {
  if (!estado.trabajoId) return;
  if (urlImagenActual) {
    URL.revokeObjectURL(urlImagenActual);
    urlImagenActual = null;
  }
  $("lienzo").innerHTML = "";
  try {
    const blob = await (await api(`/api/trabajos/${estado.trabajoId}/${nombre}`)).blob();
    urlImagenActual = URL.createObjectURL(blob);
    const img = new Image();
    img.alt = nombre === "preview.png" ? "Cómo quedó el acomodo" : "Qué se descartó";
    img.src = urlImagenActual;
    $("lienzo").append(img);
  } catch (error) {
    // 409: el archivo todavía no existe (por ejemplo la previsualización
    // antes de acomodar). No es un bug, así que no usa el cartel de error:
    // sólo deja el lienzo en un estado legible.
    $("lienzo").textContent = "Todavía no hay imagen para mostrar.";
  }
}

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
    angulos: $("angulos").value.split(",").map(Number),
    espejo: $("espejo").checked,
    unidades: estado.unidades,
    tol_cierre: Number($("tol-cierre").value),
    resolucion: Number($("resolucion").value),
    esfuerzo: $("esfuerzo").value,
  };
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
  estado.terminado = false;
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
  $("btn-guardar").disabled = false;
  if (EN_ESCRITORIO) {
    // El DXF vive en una carpeta temporal hasta que el usuario lo guarda.
    window.pywebview?.api?.marcar_sin_guardar(true);
  }
  const r = t.resultado;
  const placas = r.placas === 1 ? "1 placa" : `${r.placas} placas`;
  $("resultado").innerHTML =
    `<strong>${placas}</strong> · <strong>${(100 * r.total).toFixed(1)}%</strong> ` +
    `aprovechado · sobrante <strong>${r.sobrante_mm.toFixed(0)} mm</strong>`;
  $("resultado").classList.remove("oculto");
  $("placa-actual").textContent = `${r.placas} placa${r.placas === 1 ? "" : "s"}`;
  $("tab-preview").click();
  if (t.avisos.length) console.info("avisos:", t.avisos);
}

// --- guardar ----------------------------------------------------------------

$("btn-guardar").onclick = async () => {
  const url = `/api/trabajos/${estado.trabajoId}/salida.dxf`;
  const sugerido = (estado.nombreArchivo || "salida").replace(/\.[^.]+$/, "") + "_acomodado.dxf";
  if (EN_ESCRITORIO) {
    // Diálogo nativo: el usuario elige la carpeta de su proyecto, que es
    // donde este archivo tiene que ir.
    const destino = await window.pywebview.api.elegir_destino(sugerido);
    if (!destino) return;
    const datos = new Uint8Array(await (await api(url)).arrayBuffer());
    await window.pywebview.api.guardar(destino, Array.from(datos));
    $("resultado").insertAdjacentHTML("beforeend", ` · guardado`);
    return;
  }
  // Mismo problema que en mostrarImagen(): un <a download> tampoco lleva
  // cabeceras, así que el archivo se trae con `api()` y se descarga desde
  // un blob local en vez de apuntar el href directo a la ruta de la API.
  const blob = await (await api(url)).blob();
  const urlBlob = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = urlBlob;
  a.download = sugerido;
  a.click();
  // Revocar en el siguiente turno: hacerlo antes de que el navegador haya
  // arrancado la descarga la corta en algunos navegadores.
  setTimeout(() => URL.revokeObjectURL(urlBlob), 0);
};

// --- pantalla de materiales ---------------------------------------------

// El flujo principal sólo sabe mostrar y ocultar la pantalla: qué hay
// adentro (la tabla, el alta, el borrado) es de `materiales.js`, que se
// engancha llamando a `window.__nesting.mostrarMateriales`.
function mostrarMateriales() {
  $("pantalla-principal").classList.add("oculto");
  $("pantalla-materiales").classList.remove("oculto");
}

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
  mostrarError,
  $,
};

refrescarMateriales().catch((error) =>
  mostrarError("No se pudo leer el catálogo de materiales", error.message)
);
