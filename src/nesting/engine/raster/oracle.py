"""The real nesting engine: bitmap collision, FFT search, contact scoring.

Implements the same three-method `Oracle` protocol as the throwaway shelf
engine, so the packer, the CLI, the bench and the verifier are unchanged.
"""

import math

import numpy as np

from nesting.engine.exact import ArbitroExacto
from nesting.engine.oracle import NestConfig
from nesting.engine.raster.masks import (
    MaskCache,
    PartMasks,
    contact_band_px,
    radio_optimista,
)
from nesting.engine.raster.scoring import contact_band, position_scores
from nesting.engine.raster.search import feasible_positions
from nesting.model.part import Part


MAX_SHEET_PIXELS = 200_000_000
"""Tope de la grilla de la PLACA, distinta de la de las piezas (MAX_GRID_PIXELS
en masks.py) y con su propio presupuesto.

Sin este tope, `reset` aloca lo que le pidan. Con resolución 0.005 mm/px sobre
una placa de 1000x1000 pide 196000x196000 = 35.8 GiB. En macOS y Linux eso NO
falla: el sistema entrega memoria virtual sin respaldarla, y `np.zeros` usa
calloc, que recibe páginas en cero de forma perezosa. El programa seguía
adelante y recién más tarde chocaba con el tope de la grilla de las piezas,
que sí levanta un ValueError con mensaje claro. O sea que el mensaje bueno
salía POR CASUALIDAD, por el orden de las dos asignaciones.

En Windows no hay sobrecompromiso: la asignación falla en el acto con
`MemoryError`, que no es ninguno de los errores que `nesting_app.jobs`
clasifica como problema del usuario. Resultado: alguien que escribía una
resolución muy fina veía "se rompió el programa" con un traceback, por una
decisión enteramente suya. Lo encontró la primera corrida de los tests en
Windows.

El tope se chequea acá, donde está la asignación, así que las dos plataformas
se comportan igual y el error sale antes de reservar un solo byte.

El valor, medido sobre la placa más grande del catálogo (1830x2600, margen 10,
o sea 1810x2580 mm útiles), en píxeles de la grilla -- un byte cada uno:

    2 mm/px (el valor por omisión)      1,2 M     1 MB
    1 mm/px                             4,7 M     4 MB
    0,5 mm/px                            19 M    18 MB
    0,25 mm/px                           75 M    71 MB
    0,2 mm/px                           117 M   111 MB
    0,1 mm/px                           467 M   445 MB   <- rechazada

200 millones (unos 190 MB) deja pasar hasta 0,2 mm/px en la placa más grande
y rechaza de ahí para abajo. Para cortar madera eso ya es absurdo: la fresa
más fina del taller mide varios milímetros, así que una grilla más fina que
medio milímetro no cambia ningún corte, sólo consume memoria.
"""


def _mejores(valores: np.ndarray, cuantos: int) -> np.ndarray:
    """Los índices de los `cuantos` valores más altos, de mayor a menor.

    Ignora los `-inf`, que son las posiciones no factibles o ya descartadas
    por una tanda anterior: si quedan menos finitos que `cuantos`, devuelve
    sólo esos, y un arreglo vacío cuando no queda ninguno.

    Usa `argpartition` (O(n)) y recién después ordena la tanda (unas pocas
    decenas de elementos): ordenar el arreglo entero sería O(n log n) sobre
    los cientos de miles de posiciones de una placa, y se tiraría casi todo.
    """
    finitos = int(np.count_nonzero(valores > -np.inf))
    cuantos = min(cuantos, finitos)
    if cuantos <= 0:
        return np.empty(0, dtype=np.intp)
    if cuantos >= valores.size:
        indices = np.arange(valores.size)
    else:
        indices = np.argpartition(valores, -cuantos)[-cuantos:]
    return indices[np.argsort(-valores[indices], kind="stable")]


class RasterOracle:
    """Collision by bitmap overlap, position search by cross-correlation.

    La grilla propone y la geometría exacta dispone: la búsqueda usa una
    holgura OPTIMISTA (admite posiciones de más) y un árbitro exacto decide
    cuál de los candidatos vale. Ver `_buscar_con` para el argumento de por
    qué eso no pierde ninguna posición buena.
    """

    CANDIDATOS_POR_TANDA = 64
    """Cuántos candidatos se verifican exactamente por vez.

    El árbitro cuesta ~312 µs por consulta contra cada vecino cercano, así
    que verificar la placa entera es imposible; y verificar uno solo deja al
    motor sin salida cuando el mejor candidato de la grilla resulta inválido.
    Se recorren de a tandas, en orden de puntaje, hasta el tope de abajo.
    """

    MAX_CANDIDATOS = 1024
    """Tope duro de candidatos verificados antes de rendirse y caer al
    camino conservador.

    Sin tope, una placa casi llena puede hacer que una sola pieza pague
    cientos de miles de consultas exactas. Con tope, el peor caso es
    acotado y además NO se pierde nada: si ninguno de los candidatos
    optimistas pasó, se reintenta con la holgura conservadora de siempre,
    que no necesita árbitro porque ya es segura por construcción. O sea que
    el motor híbrido nunca coloca menos piezas que el motor viejo.
    """

    def __init__(self, cache: MaskCache | None = None) -> None:
        self._cache = cache if cache is not None else MaskCache()
        self._config = NestConfig()
        self._sheet = np.zeros((0, 0), dtype=bool)
        self._frontier = 0
        """Highest row index reached by placed material, for the active region."""

        self._arbitro: ArbitroExacto | None = None
        """La geometría exacta de lo ya colocado EN ESTA placa.

        Lo crea `reset`, o sea que vive y muere con la placa: `_pack_once`
        pide un oráculo nuevo por placa y lo resetea, así que nunca arrastra
        piezas de la placa anterior.
        """

        self._radio_optimista = 0

    def reset(self, sheet_w: float, sheet_h: float, config: NestConfig) -> None:
        self._config = config
        resolution = config.resolution

        # The grid covers ONLY the usable area, so "valid" correlation positions
        # are inside the margin by construction. No bounds code anywhere.
        usable_w = sheet_w - 2 * config.margin
        usable_h = sheet_h - 2 * config.margin
        cols = max(0, math.floor(usable_w / resolution))
        rows = max(0, math.floor(usable_h / resolution))

        if rows * cols > MAX_SHEET_PIXELS:
            raise ValueError(
                "la grilla de la placa es demasiado grande: una placa de "
                f"{sheet_w:.0f}x{sheet_h:.0f} mm a resolución {resolution} mm/px "
                f"necesita {cols}x{rows} = {rows * cols:,} píxeles "
                f"(tope: {MAX_SHEET_PIXELS:,}). "
                "Probá con una resolución más gruesa."
            )

        self._sheet = np.zeros((rows, cols), dtype=bool)
        self._frontier = 0
        self._arbitro = ArbitroExacto(sheet_w, sheet_h, config.sep, config.margin)
        self._radio_optimista = radio_optimista(config.sep, config.resolution)

    def best_placement(
        self, part: Part, angle: float, mirror: bool
    ) -> tuple[float, float, float] | None:
        masks = self._masks(part, angle, mirror)
        height = masks.clearance.shape[0]

        result = self._search(
            part, angle, mirror, masks, limit_rows=self._frontier + height
        )
        if result is None and self._frontier + height < self._sheet.shape[0]:
            result = self._search(
                part, angle, mirror, masks, limit_rows=self._sheet.shape[0]
            )
        if result is None:
            return None

        px, py, score = result
        dx, dy = masks.translation_for(px, py)
        return (dx + self._config.margin, dy + self._config.margin, score)

    def place(self, part: Part, angle: float, mirror: bool, x: float, y: float) -> None:
        masks = self._masks(part, angle, mirror)
        px, py = self._to_pixels(masks, x, y)
        height, width = masks.occupied.shape

        # `px`/`py` locate mask pixel [0, 0], which - now that `_search` pads
        # the sheet before correlating (see its docstring) - can legitimately
        # fall just before the sheet's own [0, 0] (up to `masks.pad` pixels
        # negative): that is the zero-padding region, never real material,
        # since `occupied` never uses those outermost `pad` pixels of its own
        # array (see `PartMasks.pad`). A plain `self._sheet[py:...]` slice
        # would silently wrap on a negative start (numpy/Python slicing
        # semantics), stamping the wrong rows/columns instead of erroring, so
        # both ends are clipped explicitly here and the source slice of
        # `occupied` is shifted to match - it stamps nothing but zeros there
        # regardless, but this keeps the two slices' shapes aligned.
        dst_row0, dst_col0 = max(py, 0), max(px, 0)
        dst_row1 = min(py + height, self._sheet.shape[0])
        dst_col1 = min(px + width, self._sheet.shape[1])
        src_row0, src_col0 = dst_row0 - py, dst_col0 - px
        src_row1 = src_row0 + max(dst_row1 - dst_row0, 0)
        src_col1 = src_col0 + max(dst_col1 - dst_col0, 0)

        self._sheet[dst_row0:dst_row1, dst_col0:dst_col1] |= (
            masks.occupied[src_row0:src_row1, src_col0:src_col1]
        )
        self._frontier = max(self._frontier, py + height)

        # La grilla ya no alcanza para decidir: quien decide es el árbitro, y
        # para eso necesita ver la geometría exacta de todo lo colocado. Va
        # acá y no en `best_placement`, que es de sólo lectura a propósito
        # (el empacador pregunta por varias orientaciones antes de elegir una).
        if self._arbitro is not None:
            self._arbitro.agregar(part, angle, mirror, x, y)

    def _search(
        self,
        part: Part,
        angle: float,
        mirror: bool,
        masks: PartMasks,
        limit_rows: int,
    ) -> tuple[int, int, float] | None:
        """Search within the first `limit_rows` rows of the sheet.

        `margin` and `sep` are different constraints: `margin` bounds the
        *material*, `sep` (via `clearance`, material dilated by the
        separation) only matters against other material already on the
        sheet. Correlating `clearance` in "valid" mode against the bare
        usable-area window would demand that the whole clearance halo -
        including the part that has nothing to collide with beyond the
        sheet's edge - land inside that area too, which double-charges the
        edge: material would need to sit `margin + sep` from the physical
        border instead of `margin`.

        The fix is to pad the window with `masks.pad` pixels of zeros on
        every side before correlating. `clearance` can then use that
        padding for its halo without it costing anything (padding is zero,
        never a collision), while `occupied` - always `masks.pad` pixels
        narrower than `clearance`'s own array on every side, by
        construction (see `PartMasks.pad`) - ends up exactly bounded by the
        real, unpadded area. A "valid" correlation of shape `(Hm, Wm)`
        against a window padded by `pad` on every side has
        `rows + 2*pad - Hm + 1 == rows - (Hm - 2*pad) + 1` output rows,
        i.e. exactly one entry per position where the material's own tight
        footprint (Hm - 2*pad rows) fits in the unpadded window - same for
        columns.

        The output index (i, j) of that padded correlation directly gives
        the position of that tight footprint in the unpadded window (see
        the task-18 report for the arithmetic), while `translation_for` and
        `place` both work in "mask [0, 0] pixel, unpadded-window frame"
        terms - `pad` pixels before that. So (i, j) is shifted by `-pad`
        before it leaves this method.

        La búsqueda se hace en dos pasadas sobre esa misma ventana: primero
        con la holgura optimista y el árbitro exacto decidiendo, y si de ahí
        no sale nada, con la holgura conservadora de siempre. Ver
        `_buscar_con`.
        """
        pad = masks.pad
        rows = min(max(limit_rows, masks.clearance.shape[0]), self._sheet.shape[0])
        window = self._sheet[:rows]
        padded = np.pad(window, pad, mode="constant", constant_values=False)

        if self._arbitro is not None:
            optimista = self._buscar_con(
                part,
                angle,
                mirror,
                masks,
                padded,
                masks.holgura_optimista(self._radio_optimista),
                arbitrar=True,
            )
            if optimista is not None:
                return optimista

        # Red de seguridad: la holgura conservadora no necesita árbitro,
        # porque ya es segura por construcción. Ver `MAX_CANDIDATOS`.
        return self._buscar_con(
            part, angle, mirror, masks, padded, masks.clearance, arbitrar=False
        )

    def _buscar_con(
        self,
        part: Part,
        angle: float,
        mirror: bool,
        masks: PartMasks,
        padded: np.ndarray,
        holgura: np.ndarray,
        *,
        arbitrar: bool,
    ) -> tuple[int, int, float] | None:
        """Buscar la mejor posición usando `holgura` como máscara de colisión.

        POR QUÉ LA GRILLA PUEDE SER OPTIMISTA SIN PERDER NADA

        `occupied` sobre-representa el material exacto en a lo sumo
        `masks.py::INFLACION_MAX_PX` píxeles por lado -- uno del
        `_downsample_any` y uno de la dilatación de seguridad de 3x3. Llamemos
        `e = INFLACION_MAX_PX * resolution` a eso, en mm.

        Si la holgura usa un radio `r` con `r * resolution <= sep - 2e`,
        entonces TODA posición realmente factible (distancia exacta entre los
        polígonos >= `sep`) pasa el test de la grilla: las dos piezas están
        infladas en a lo sumo `e` cada una, así que entre sus `occupied` queda
        todavía >= `sep - 2e >= r * resolution`, que es exactamente lo que el
        halo de radio `r` exige. Eso es lo que calcula `radio_optimista`.

        Al revés no vale: el test optimista también admite posiciones que
        violan la separación real. O sea que el conjunto de candidatos es un
        SUPERCONJUNTO del factible real -- no se pierde ninguna posición
        buena, y las malas las tiene que filtrar alguien más. Ese alguien es
        `self._arbitro`, que mide sobre los polígonos exactos con el mismo
        criterio que el verificador final.

        EL HUECO HONESTO DEL ARGUMENTO. La cota `INFLACION_MAX_PX` es por
        eje (L∞: a lo sumo `e` de más en x, a lo sumo `e` de más en y, cada
        uno medido por separado -- ver su docstring en `masks.py`), porque
        así es como se mide sobre una grilla cuadriculada. Pero el halo que
        arma `radio_optimista` a partir de `e` se aplica sobre
        `disk_kernel`, que es una dilatación EUCLÍDEA (un disco, no un
        cuadrado). En una esquina, una posición podría en principio necesitar
        hasta `2√2 * e` de inflación en vez de los `2 * e` que da la cota por
        eje -- el argumento de arriba no cierra ese caso por aritmética pura,
        y no conviene fingir que sí. Lo que sostiene la conclusión es
        empírico, no una demostración: miles de posiciones factibles
        barridas a 2 mm/px y a 1 mm/px, sin encontrar un solo caso donde se
        pierda una posición buena por esa esquina. La conclusión (no se
        pierde nada, en la práctica) se sostiene; lo que no se sostiene es
        llamarla una prueba.

        De ahí sale, además, que esta pasada nunca elige peor que la
        conservadora: la mejor posición conservadora también es candidata acá
        (superconjunto) y el árbitro la acepta seguro (es segura por
        construcción), así que cualquier candidato que se devuelva antes que
        ella puntúa al menos tan bien. Lo único que puede hacer que no se
        llegue hasta ella es el tope `MAX_CANDIDATOS`, y para eso está la
        pasada conservadora de `_search`.

        Con `arbitrar=False` no hay nada de esto: se devuelve el máximo
        directamente, que es el comportamiento de siempre.
        """
        pad = masks.pad
        feasible = feasible_positions(padded, holgura)
        if feasible.size == 0 or not feasible.any():
            return None

        score = position_scores(
            feasible, padded, self._banda_de_contacto(masks), self._config.weights
        )
        cols = score.shape[1]

        if not arbitrar:
            plano = int(np.argmax(score))
            row, col = divmod(plano, cols)
            return (col - pad, row - pad, float(score[row, col]))

        # Los candidatos se recorren en orden de puntaje -- el puntaje real,
        # con su término de contacto, que es lo que hace que las piezas
        # curvas se encastren -- y no simplemente de abajo a la izquierda.
        pendientes = score.ravel()
        vistos = 0
        while vistos < self.MAX_CANDIDATOS:
            tanda = _mejores(
                pendientes, min(self.CANDIDATOS_POR_TANDA, self.MAX_CANDIDATOS - vistos)
            )
            if tanda.size == 0:
                return None
            for indice in tanda:
                row, col = divmod(int(indice), cols)
                dx, dy = masks.translation_for(col - pad, row - pad)
                x = dx + self._config.margin
                y = dy + self._config.margin
                if self._arbitro.entra(part, angle, mirror, x, y):
                    return (col - pad, row - pad, float(pendientes[indice]))
            # Tachados: la próxima tanda son los mejores de lo que queda.
            pendientes[tanda] = -np.inf
            vistos += int(tanda.size)
        return None

    def _banda_de_contacto(self, masks: PartMasks) -> np.ndarray:
        """Dónde tiene que haber material ajeno para que la pieza cuente como
        apoyada. Sale de `clearance` -- la conservadora -- siempre.

        Es tentador armarla sobre la holgura que se esté usando para la
        factibilidad, y es lo primero que se probó acá. Está mal, y lo agarró
        `test_a_small_part_is_nested_inside_a_big_hole`: la holgura optimista
        es tan fina que se TRAGA la zona de contacto. `contact_band` devuelve
        el anillo que queda justo afuera de la máscara que recibe, o sea que
        los píxeles de adentro no cuentan; con la holgura optimista el anillo
        queda pegado al material y una vecina a la distancia pedida exacta se
        vuelve invisible. Medido sobre dos rectángulos, con la banda armada
        sobre la holgura optimista el término de contacto vale 0.239 a 0-8 mm
        (distancias que el árbitro rechaza), 0.119 a los 10 mm pedidos y CERO
        de 12 mm en adelante; armada sobre `clearance` vale 0.215 parejo
        hasta los 16 mm. Con la primera, la pieza chica del test dejaba de
        encastrar en el agujero de la grande y se iba al costado.

        Lo único que hay que cuidar es la forma del arreglo, que tiene que
        coincidir con la de la holgura para que las dos correlaciones salgan
        del mismo tamaño (`position_scores` lo exige). Coincide siempre:
        todas las máscaras de una `PartMasks` viven en la misma grilla y
        dilatar no cambia el tamaño del arreglo.
        """
        return contact_band(masks.clearance, contact_band_px(self._config.resolution))

    def _masks(self, part: Part, angle: float, mirror: bool) -> PartMasks:
        return self._cache.get(
            part, angle, mirror, self._config.resolution, self._config.sep
        )

    def _to_pixels(self, masks: PartMasks, x: float, y: float) -> tuple[int, int]:
        """Inverse of `translation_for`, plus the margin offset."""
        resolution = self._config.resolution
        px = round((x - self._config.margin + masks.origin[0]) / resolution)
        py = round((y - self._config.margin + masks.origin[1]) / resolution)
        return (px, py)
