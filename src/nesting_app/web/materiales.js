"use strict";

/* La pantalla de materiales: tabla, alta, edición y baja.
 *
 * La veta se muestra siempre en palabras. Un campo de grados entre 0 y 180
 * es exacto y no le dice nada a nadie: quien compra multilaminado sabe que
 * hay que respetar la veta, no que eso son 5 grados. */

// Todo el archivo va adentro de una IIFE. Un <script> clásico comparte el
// ámbito global con los demás, así que declarar acá `const apiJson` --
// que app.js ya declaró -- es un SyntaxError que mata este archivo ENTERO
// antes de registrar un solo handler. Pasó: la pantalla de materiales
// abría (ese botón lo registra app.js) pero no andaban ni "Volver" ni
// "Cancelar" ni aparecía ningún material, y la consola de una ventana de
// pywebview no se puede abrir para verlo.
(() => {

const { apiJson, postJson, refrescarMateriales, mostrarMateriales, mostrarError, $ } =
  window.__nesting;

let editando = null;

const LAPIZ = '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.5 2.5l2 2L6 12l-3 1 1-3z"></path></svg>';
const TACHO = '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 4h11"></path><path d="M6 4V2.5h4V4"></path><path d="M4 4l.6 9.5h6.8L12 4"></path></svg>';

const ETIQUETA_VETA = { libre: "No importa", respetar: "Respetar" };

// `mostrarMateriales` (de app.js) ya sabe ocultar la pantalla principal y
// mostrar ésta -- eso lo comparten los dos archivos. Este handler reemplaza
// el `onclick` que app.js le puso a `btn-materiales`, pero llama a esa misma
// función en vez de repetir su lógica: si sólo agregáramos un segundo
// `onclick` acá, el de acá pisaría al de app.js y la pantalla principal se
// quedaría sin ocultar.
$("btn-materiales").onclick = async () => {
  mostrarMateriales();
  await dibujarTabla();
};

$("btn-volver").onclick = () => {
  $("pantalla-materiales").classList.add("oculto");
  $("pantalla-principal").classList.remove("oculto");
  limpiarFormulario();
};

async function dibujarTabla() {
  let materiales;
  try {
    materiales = (await apiJson("/api/materiales")).materiales;
  } catch (error) {
    return mostrarError("No se pudo leer el catálogo", error.message);
  }

  const cuerpo = $("tabla-materiales");
  cuerpo.innerHTML = "";
  for (const m of materiales) {
    // `m.nombre` es texto libre que el usuario tipea y queda guardado en el
    // catálogo: si se interpolara en un `innerHTML` un nombre como
    // `<img src=x onerror=...>` se ejecutaría cada vez que alguien abre esta
    // pantalla -- persistente, no un reflejo pasajero. Por eso esta celda
    // (y cualquier otra con un dato del usuario) va por `textContent`, igual
    // que `refrescarMateriales` en app.js.
    const fila = document.createElement("tr");

    const celdaNombre = document.createElement("td");
    celdaNombre.textContent = m.nombre;

    const celdaAncho = document.createElement("td");
    celdaAncho.className = "der";
    celdaAncho.textContent = m.ancho;

    const celdaAlto = document.createElement("td");
    celdaAlto.className = "der";
    celdaAlto.textContent = m.alto;

    // La veta sí va interpolada, y no es texto del usuario: viene de
    // `_nombre_de_veta()` en api.py, un if/else de dos ramas fijas, sobre
    // un grado que `load_materials()` ya acotó al leer el YAML. Ojo: no es
    // el Literal de Pydantic lo que protege acá -- ése sólo valida lo que
    // ENTRA por POST y PUT, no lo que sale al leer el catálogo.
    const veta = m.veta;
    const celdaVeta = document.createElement("td");
    celdaVeta.innerHTML = `<span class="insignia ${veta}">${ETIQUETA_VETA[veta]}</span>`;

    const acciones = document.createElement("td");
    acciones.className = "der";
    acciones.append(
      botonIcono(LAPIZ, `Editar ${m.nombre}`, () => cargarEnFormulario(m)),
      botonIcono(TACHO, `Borrar ${m.nombre}`, () => borrar(m.nombre))
    );

    fila.append(celdaNombre, celdaAncho, celdaAlto, celdaVeta, acciones);
    cuerpo.append(fila);
  }

  // El desplegable de material de la pantalla principal viene de la misma
  // lista: si esto quedara sin `catch`, un fallo acá dejaría una promesa
  // rechazada sin nadie que la atienda en cada lugar que llama a
  // `dibujarTabla` (el propio `onclick`, el alta, la edición y el borrado).
  try {
    await refrescarMateriales();
  } catch (error) {
    mostrarError("No se pudo actualizar la lista de materiales", error.message);
  }
}

function botonIcono(svg, titulo, alClickear) {
  const boton = document.createElement("button");
  boton.type = "button";
  boton.className = "icono-boton";
  boton.setAttribute("aria-label", titulo);
  boton.innerHTML = svg;
  boton.onclick = alClickear;
  return boton;
}

function cargarEnFormulario(m) {
  editando = m.nombre;
  $("titulo-form").textContent = `Editar ${m.nombre}`;
  $("m-nombre").value = m.nombre;
  $("m-ancho").value = m.ancho;
  $("m-alto").value = m.alto;
  $(m.veta === "libre" ? "m-veta-libre" : "m-veta-respetar").checked = true;
}

function limpiarFormulario() {
  editando = null;
  $("titulo-form").textContent = "Nuevo material";
  $("form-material").reset();
  $("error-material").classList.add("oculto");
}

$("btn-cancelar-material").onclick = limpiarFormulario;

$("form-material").onsubmit = async (evento) => {
  evento.preventDefault();
  $("error-material").classList.add("oculto");
  const cuerpo = {
    nombre: $("m-nombre").value.trim(),
    ancho: Number($("m-ancho").value),
    alto: Number($("m-alto").value),
    veta: $("m-veta-libre").checked ? "libre" : "respetar",
  };
  try {
    if (editando) {
      await apiJson(`/api/materiales/${encodeURIComponent(editando)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cuerpo),
      });
    } else {
      await postJson("/api/materiales", cuerpo);
    }
  } catch (error) {
    $("error-material").textContent = error.message || "No se pudo guardar.";
    $("error-material").classList.remove("oculto");
    return;
  }
  limpiarFormulario();
  await dibujarTabla();
};

async function borrar(nombre) {
  // Borrar no se deshace, y el material puede estar en uso en trabajos que
  // el usuario todavía no repitió.
  if (!confirm(`¿Borrar el material "${nombre}"? No se puede deshacer.`)) return;
  try {
    await apiJson(`/api/materiales/${encodeURIComponent(nombre)}`, { method: "DELETE" });
  } catch (error) {
    return mostrarError("No se pudo borrar", error.message);
  }
  await dibujarTabla();
}

$("btn-restaurar").onclick = async () => {
  if (!confirm("¿Volver al catálogo original? Se pierden los materiales que agregaste."))
    return;
  try {
    await postJson("/api/materiales/restaurar", {});
  } catch (error) {
    return mostrarError("No se pudo restaurar", error.message);
  }
  limpiarFormulario();
  await dibujarTabla();
};

})();
