"use strict";

/* Los globos de ayuda de cada opción.
 *
 * El texto de estas diez opciones ya estaba en el README, que es donde nadie
 * lo lee: la duda aparece parado frente a la máquina, con el archivo abierto
 * y la placa cargada. Acá está al lado de la etiqueta.
 *
 * No comparte nada con `app.js` -- ni estado, ni red, ni el trabajo en
 * curso -- así que vive aparte. */

// Todo el archivo va adentro de una IIFE. Un <script> clásico comparte el
// ámbito global con los demás, así que declarar acá un `const` que app.js ya
// declaró es un SyntaxError que mata este archivo ENTERO antes de registrar
// un solo handler. Pasó con materiales.js.
(() => {

/* Una clave por opción, igual al `data-info` de su botón en el HTML. Los
   tests verifican que los dos conjuntos sean el mismo: un botón sin texto
   abre un globo vacío y no falla en ningún otro lado. */
const TEXTOS = {
  "archivo": "El dibujo con los contornos de las piezas. Acepta .dxf, .ai (los de texto plano) y .3dm de Rhino; .cdr no, hay que exportarlo antes.",
  "material": "La placa de la que vas a cortar: de acá salen el ancho, el alto y si hay que respetar la veta. Si te falta una medida, \"Agregar o editar\" abre el catálogo.",
  "sep": "Los milímetros mínimos que quedan entre una pieza y la de al lado. Poné al menos el diámetro de la fresa, o el corte de una se come el borde de la otra.",
  "borde": "El margen que se deja libre contra el filo de la placa. Sirve para las grampas y para que una placa astillada no arruine una pieza.",
  "copias": "Cuántas veces se repite el contenido entero del archivo. Si el archivo trae 12 piezas y ponés 3, acomoda 36.",
  "esfuerzo": "Cuántas veces intenta acomodar antes de quedarse con la mejor. Más esfuerzo nunca da un resultado peor, pero tarda más: Normal alcanza casi siempre.",
  "angulos": "Las rotaciones que puede probar en cada pieza, separadas por comas. Menos ángulos es más rápido; sumar 45 suele ganar lugar en piezas largas. Si el material respeta la veta, sólo se usan 0 y 180.",
  "tol-cierre": "Cuánto puede separarse la punta de un contorno de su principio y todavía contar como cerrado. Si te descarta piezas que a ojo están cerradas, subila.",
  "resolucion": "Cuántos milímetros mide cada píxel con el que el programa \"ve\" la placa. Más fino acomoda apenas mejor y tarda mucho más; 2 mm es buen punto.",
  "espejo": "Deja dar vuelta la pieza como un guante, no sólo rotarla. Gana lugar, pero si el material tiene una cara buena o el dibujo es asimétrico, apagalo.",
};

const globo = document.getElementById("globo-info");

/* El botón que tiene el globo abierto, o null. Uno solo a la vez: dos
   globos abiertos se pisan y no se sabe cuál explica qué. */
let abierto = null;

const MARGEN = 8;

function ubicar(boton) {
  const b = boton.getBoundingClientRect();
  // Medirlo exige mostrarlo, y mostrarlo antes de ubicarlo lo hace
  // parpadear en la esquina. `visibility` lo deja medible e invisible.
  globo.style.visibility = "hidden";
  globo.classList.remove("oculto");
  const g = globo.getBoundingClientRect();

  // A la derecha del ícono si entra; si no, a la izquierda. En una ventana
  // angosta el panel ya se come casi todo y la derecha no alcanza.
  let x = b.right + MARGEN;
  if (x + g.width > window.innerWidth - MARGEN) x = b.left - MARGEN - g.width;
  let y = b.top;
  if (y + g.height > window.innerHeight - MARGEN) {
    y = window.innerHeight - MARGEN - g.height;
  }

  globo.style.left = `${Math.round(Math.max(MARGEN, x))}px`;
  globo.style.top = `${Math.round(Math.max(MARGEN, y))}px`;
  globo.style.visibility = "";
}

function abrir(boton) {
  const texto = TEXTOS[boton.dataset.info];
  if (!texto) return;
  globo.textContent = texto;
  ubicar(boton);
  boton.setAttribute("aria-expanded", "true");
  boton.setAttribute("aria-describedby", "globo-info");
  abierto = boton;
}

function cerrar() {
  if (!abierto) return;
  globo.classList.add("oculto");
  abierto.setAttribute("aria-expanded", "false");
  abierto.removeAttribute("aria-describedby");
  abierto = null;
}

document.addEventListener("click", (e) => {
  const boton = e.target.closest?.(".boton-info");
  // El mismo botón cierra el que tenía abierto. Sin esto, apretar dos veces
  // lo cierra y lo vuelve a abrir en el mismo gesto y parece que no hace
  // nada.
  if (boton && boton === abierto) { cerrar(); return; }
  cerrar();
  if (boton) abrir(boton);
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || !abierto) return;
  const boton = abierto;
  cerrar();
  boton.focus();
});

// En captura: el que scrollea es `.panel-opciones`, y el scroll de un
// elemento no burbujea hasta document.
document.addEventListener("scroll", cerrar, true);
window.addEventListener("resize", cerrar);

})();
