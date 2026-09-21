import math
from dataclasses import replace

import pytest

from nesting.engine.oracle import NestConfig, Weights
from nesting.engine.packer import pack
from nesting.engine.raster.oracle import MAX_SHEET_PIXELS, RasterOracle
from nesting.engine.shelf_oracle import ShelfOracle
from nesting.geometry.verify import verify
from nesting.model.entities import Transform
from nesting.model.material import Material
from nesting.model.part import Part, Placement

MATERIAL = Material("test", 1000.0, 1000.0, grain_tolerance=180.0)
CONFIG = NestConfig(sep=10.0, margin=20.0, angles=(0.0, 90.0), mirror=False, resolution=2.0)


def rect_part(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def circle_part(part_id, radius, segments=48):
    ring = tuple(
        (radius * math.cos(2 * math.pi * i / segments),
         radius * math.sin(2 * math.pi * i / segments))
        for i in range(segments)
    )
    return Part(part_id, ring, (), (part_id,))


def ring_part(part_id, outer, inner):
    return Part(
        part_id,
        ((0.0, 0.0), (outer, 0.0), (outer, outer), (0.0, outer)),
        ((((outer - inner) / 2, (outer - inner) / 2),
          ((outer + inner) / 2, (outer - inner) / 2),
          ((outer + inner) / 2, (outer + inner) / 2),
          ((outer - inner) / 2, (outer + inner) / 2)),),
        (part_id,),
    )


def test_the_first_part_lands_near_the_bottom_left_margin():
    oracle = RasterOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 50.0)

    x, y, _ = oracle.best_placement(part, 0.0, False)
    assert x == pytest.approx(20.0, abs=CONFIG.resolution)
    assert y == pytest.approx(20.0, abs=CONFIG.resolution)


def test_best_placement_does_not_mutate_state():
    oracle = RasterOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 50.0)
    assert oracle.best_placement(part, 0.0, False) == oracle.best_placement(part, 0.0, False)


def test_a_placed_part_blocks_its_own_position():
    oracle = RasterOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 50.0)

    x, y, _ = oracle.best_placement(part, 0.0, False)
    oracle.place(part, 0.0, False, x, y)
    second = oracle.best_placement(part, 0.0, False)

    assert second is not None
    assert (second[0], second[1]) != (x, y)


def test_returns_none_when_the_part_cannot_fit():
    oracle = RasterOracle()
    oracle.reset(200.0, 200.0, CONFIG)
    assert oracle.best_placement(rect_part(0, 500.0, 500.0), 0.0, False) is None


def test_a_full_layout_passes_the_verifier():
    oracle = RasterOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)

    parts = [rect_part(i, 140.0, 90.0) for i in range(20)]
    placements = []
    for part in parts:
        spot = oracle.best_placement(part, 0.0, False)
        if spot is None:
            continue
        x, y, _ = spot
        oracle.place(part, 0.0, False, x, y)
        placements.append(Placement(part.id, 0, Transform(0.0, False, x, y)))

    assert len(placements) >= 15
    assert verify(parts, placements, 1000.0, 1000.0, sep=CONFIG.sep, margin=CONFIG.margin) == []


def test_rotated_and_mirrored_layouts_pass_the_verifier():
    config = NestConfig(sep=10.0, margin=20.0, angles=(0.0, 90.0), mirror=True, resolution=2.0)
    parts = [rect_part(i, 200.0, 70.0) for i in range(12)]
    result = pack(parts, MATERIAL, config, RasterOracle)

    assert verify(parts, result.placements, MATERIAL.sheet_w, MATERIAL.sheet_h,
                  sep=config.sep, margin=config.margin) == []


def test_curved_parts_pass_the_verifier():
    parts = [circle_part(i, 90.0) for i in range(12)]
    result = pack(parts, MATERIAL, CONFIG, RasterOracle)
    assert verify(parts, result.placements, MATERIAL.sheet_w, MATERIAL.sheet_h,
                  sep=CONFIG.sep, margin=CONFIG.margin) == []


def test_a_small_part_is_nested_inside_a_big_hole():
    """La ganancia de la spec 5.2, verificada end to end."""
    parts = [ring_part(0, 600.0, 400.0), rect_part(1, 200.0, 200.0)]
    result = pack(parts, MATERIAL, CONFIG, RasterOracle)

    assert result.sheets_used == 1
    assert len(result.placements) == 2
    assert verify(parts, result.placements, MATERIAL.sheet_w, MATERIAL.sheet_h,
                  sep=CONFIG.sep, margin=CONFIG.margin) == []

    # La pieza chica tiene que haber caido adentro del agujero de la grande.
    from nesting.geometry.verify import placed_polygon
    big = placed_polygon(parts[0], result.placements[0].transform)
    small = placed_polygon(parts[1], result.placements[1].transform)
    hole = big.interiors[0]
    from shapely.geometry import Polygon
    assert Polygon(hole).contains(small)


def notched_circle_part(part_id, radius, mouth_deg=70.0, segments=40):
    """A circle with a wedge bitten out of it: curved AND concave.

    Used alongside `circle_part` below so the density test isn't exercising
    only convex shapes -- real jobs mix curves with concavities.
    """
    start = math.radians(mouth_deg / 2)
    end = 2 * math.pi - math.radians(mouth_deg / 2)
    ring = [(0.0, 0.0)]
    for i in range(segments + 1):
        theta = start + (end - start) * i / segments
        ring.append((radius * math.cos(theta), radius * math.sin(theta)))
    return Part(part_id, tuple(ring), (), (part_id,))


def test_the_raster_engine_fits_more_parts_on_a_single_sheet_than_the_shelf_engine():
    """Reemplaza a `test_the_raster_engine_beats_the_shelf_engine_on_circles`.

    Ese test exigia un `total_utilization` que solo se alcanza a 0.7 mm del
    optimo geometrico global para estos 14 circulos -- una holgura que ni
    siquiera sobrevive la cuantizacion de la grilla de 2 mm. Ningun nester
    heuristico encuentra un empaquetamiento asi de ajustado, y la resolucion
    del raster ni siquiera puede representarlo. El test pedia lo imposible,
    no el motor.

    La metrica que si importa, y que este test mide, es cuantas piezas entran
    en UNA placa antes de tener que abrir la siguiente: es la que se traduce
    directamente en placas ahorradas, que es lo que le cuesta plata al
    usuario. No depende de alcanzar ningun optimo, solo de que el raster
    aproveche el espacio mejor que el shelf -- que es exactamente lo que el
    hito 3 se propuso demostrar.

    Medido: shelf mete 9 circulos en la primera placa, raster mete 12 (un 33%
    mas). Pedir solo +2 deja aire de sobra sin volverse una comparacion vacia.
    """
    parts = [circle_part(i, 120.0) for i in range(14)]
    config = NestConfig(sep=8.0, margin=15.0, angles=(0.0,), mirror=False, resolution=2.0)

    shelf = pack(parts, MATERIAL, config, ShelfOracle)
    raster = pack(parts, MATERIAL, config, RasterOracle)

    shelf_on_first_sheet = sum(1 for p in shelf.placements if p.sheet == 0)
    raster_on_first_sheet = sum(1 for p in raster.placements if p.sheet == 0)

    assert raster_on_first_sheet >= shelf_on_first_sheet + 2


def test_the_raster_engine_packs_the_first_sheet_denser_with_curved_and_concave_parts():
    """Complementa al test anterior con piezas mas realistas: curvas y
    concavas, no solo circulos.

    `total_utilization` no sirve para esto: como el conjunto de piezas es el
    mismo para los dos motores, esa metrica solo puede cambiar si cambia la
    cantidad de placas usadas. Con la misma cantidad de placas da identica
    por construccion, aunque un motor haya llenado la primera placa mucho
    mejor que el otro. Por eso hay que comparar el aprovechamiento de la
    PRIMERA placa (`utilization[0]`), que es donde se ve la calidad real del
    empaquetado.

    El conjunto de piezas alcanza y sobra para llenar una placa -- por eso
    los dos motores terminan abriendo una segunda -- asi que la comparacion
    es sobre que tan bien aprovecho cada uno la primera, no sobre cuantas
    placas hacen falta en total.
    """
    parts = [circle_part(i, 120.0) for i in range(12)]
    parts += [notched_circle_part(12 + i, 120.0) for i in range(4)]
    config = NestConfig(sep=8.0, margin=15.0, angles=(0.0,), mirror=False, resolution=2.0)

    shelf = pack(parts, MATERIAL, config, ShelfOracle)
    raster = pack(parts, MATERIAL, config, RasterOracle)

    # Ambos deben haber tenido que abrir una segunda placa: si no, la
    # comparacion de la primera placa no tendria sentido (no hubo sobrante
    # que forzara a cada motor a elegir que dejar afuera).
    assert shelf.sheets_used >= 2
    assert raster.sheets_used >= 2
    assert raster.utilization[0] > shelf.utilization[0] * 1.10


def test_the_raster_engine_is_deterministic():
    parts = [rect_part(i, 140.0, 90.0) for i in range(10)]
    first = pack(parts, MATERIAL, CONFIG, RasterOracle)
    second = pack(parts, MATERIAL, CONFIG, RasterOracle)
    assert first.placements == second.placements


def test_contact_weight_produces_tighter_packing_than_bottom_left_alone():
    parts = [circle_part(i, 100.0) for i in range(12)]
    base = NestConfig(sep=8.0, margin=15.0, angles=(0.0,), mirror=False, resolution=2.0)

    bl_only = pack(parts, MATERIAL, replace(base, weights=Weights(1.0, 0.0)), RasterOracle)
    with_contact = pack(parts, MATERIAL, replace(base, weights=Weights(1.0, 1.0)),
                        RasterOracle)

    assert with_contact.total_utilization >= bl_only.total_utilization


def test_a_finer_resolution_does_not_break_the_verifier():
    parts = [circle_part(i, 80.0) for i in range(8)]
    config = NestConfig(sep=6.0, margin=10.0, angles=(0.0,), mirror=False, resolution=0.5)
    result = pack(parts, MATERIAL, config, RasterOracle)
    assert verify(parts, result.placements, MATERIAL.sheet_w, MATERIAL.sheet_h,
                  sep=config.sep, margin=config.margin) == []


# --- el tope de la grilla de la placa ---------------------------------------


def test_una_resolucion_absurda_se_rechaza_antes_de_pedir_la_memoria():
    """Lo encontró la primera corrida de los tests en Windows.

    Sin este tope, `reset` pide lo que le digan: 1000x1000 mm a 0.005 mm/px
    son 196000x196000 = 35.8 GiB. En macOS y Linux esa asignación NO falla
    -- hay sobrecompromiso y `np.zeros` recibe páginas en cero de forma
    perezosa --, así que el programa seguía adelante y el mensaje bueno salía
    más tarde y por casualidad, desde el tope de la grilla de las PIEZAS.

    En Windows no hay sobrecompromiso: `MemoryError` en el acto. Y
    `MemoryError` no está entre los errores que `nesting_app.jobs` clasifica
    como problema del usuario, así que la interfaz decía "se rompió el
    programa" y mostraba un traceback por una decisión enteramente suya.

    Se chequea donde está la asignación, así que las dos plataformas se
    comportan igual y nadie reserva un byte antes de saber que sobra.
    """
    oracle = RasterOracle()
    config = replace(CONFIG, resolution=0.005)

    with pytest.raises(ValueError) as capturado:
        oracle.reset(1000.0, 1000.0, config)

    assert not isinstance(capturado.value, MemoryError)
    mensaje = str(capturado.value)
    assert "grilla" in mensaje and "resolución" in mensaje
    assert "más gruesa" in mensaje, "el error tiene que decir qué hacer"


def test_la_resolucion_por_omision_sobre_la_placa_mas_grande_pasa_holgada():
    """Un tope que estorba el uso normal es peor que no tenerlo. La placa más
    grande del catálogo que viene con el programa mide 1830x2600."""
    oracle = RasterOracle()
    oracle.reset(1830.0, 2600.0, replace(CONFIG, margin=10.0, resolution=2.0))

    usados = oracle._sheet.size
    assert usados < MAX_SHEET_PIXELS // 100, (
        f"el uso normal consume {usados:,} de un tope de {MAX_SHEET_PIXELS:,}: "
        "el margen se achicó demasiado"
    )


def test_la_separacion_real_es_la_pedida_no_la_inflada():
    """La razón de ser del motor híbrido.

    Antes, la grilla conservadora dejaba 16 mm reales entre dos piezas
    cuando se le pedían 10 a 2 mm/px, porque cada pieza se rasteriza 3 mm
    más grande por lado y las dos pagan. Medido sobre los polígonos
    exactos, no sobre la grilla.
    """
    from nesting.engine.raster.masks import MaskCache
    from nesting.geometry.verify import placed_polygon

    lado = 100.0
    pts = ((0.0, 0.0), (lado, 0.0), (lado, lado), (0.0, lado))
    material = Material(name="t", sheet_w=1000.0, sheet_h=1000.0, grain_tolerance=180.0)
    config = NestConfig(sep=10.0, margin=10.0, angles=(0.0,), mirror=False,
                        resolution=2.0, effort="rapido")

    oracle = RasterOracle(MaskCache())
    oracle.reset(material.sheet_w, material.sheet_h, config)
    parts = []
    placements = []
    polys = []
    for i in range(2):
        part = Part(id=i, outer=pts, holes=(), entity_ids=())
        spot = oracle.best_placement(part, 0.0, False)
        assert spot is not None
        x, y, _ = spot
        oracle.place(part, 0.0, False, x, y)
        parts.append(part)
        placements.append(Placement(part.id, 0, Transform(0.0, False, x, y)))
        polys.append(placed_polygon(part, Transform(0.0, False, x, y)))

    # Dos asserts, no uno de dos lados: sólo el piso es un requisito -- por
    # debajo de 10.00 mm es una violación real de la separación pedida, y el
    # test tiene que reprobar sin importar qué tan cerca del techo quede eso.
    # El techo (mucho más flojo) es la métrica de densidad: cuánto se acerca
    # el motor híbrido a los 10 mm exactos en vez de los 16 que dejaba la
    # grilla conservadora, no un límite de corrección.
    real = polys[0].distance(polys[1])
    assert real >= 10.0 - 1e-6, (
        f"la separación real quedó en {real:.2f} mm: por debajo de los 10.00 mm "
        "pedidos, una violación real de la separación"
    )
    assert real <= 10.51, (
        f"la separación real quedó en {real:.2f} mm: muy por encima de los "
        "10.00 mm pedidos, la ganancia de densidad del motor híbrido no se "
        "estaría notando"
    )

    assert verify(parts, placements, material.sheet_w, material.sheet_h,
                  sep=config.sep, margin=config.margin) == []


def test_si_se_agota_el_presupuesto_de_candidatos_se_cae_al_camino_conservador(
    monkeypatch,
):
    """La red de seguridad del motor híbrido, ejercitada de verdad.

    Con el presupuesto real (`MAX_CANDIDATOS`) esto casi no pasa, así que
    acá se lo baja a un solo candidato: el mejor de la grilla optimista
    queda demasiado cerca de la pieza anterior, el árbitro lo rechaza, y no
    queda presupuesto para probar el siguiente. Lo que el tope NUNCA puede
    hacer es dejar una pieza sin colocar -- se reintenta con la holgura
    conservadora, que no necesita árbitro porque ya es segura. O sea que el
    motor híbrido nunca coloca menos piezas que el viejo.
    """
    from nesting.engine.raster.masks import MaskCache
    from nesting.geometry.verify import placed_polygon

    monkeypatch.setattr(RasterOracle, "MAX_CANDIDATOS", 1)
    monkeypatch.setattr(RasterOracle, "CANDIDATOS_POR_TANDA", 1)

    pts = ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0))
    config = NestConfig(sep=10.0, margin=10.0, angles=(0.0,), mirror=False,
                        resolution=2.0, effort="rapido")
    oracle = RasterOracle(MaskCache())
    oracle.reset(1000.0, 1000.0, config)

    polys = []
    for i in range(2):
        part = Part(id=i, outer=pts, holes=(), entity_ids=())
        spot = oracle.best_placement(part, 0.0, False)
        assert spot is not None, "el tope de candidatos dejó una pieza sin colocar"
        x, y, _ = spot
        oracle.place(part, 0.0, False, x, y)
        polys.append(placed_polygon(part, Transform(0.0, False, x, y)))

    real = polys[0].distance(polys[1])
    assert real >= 10.0 - 1e-6, f"la separación quedó en {real:.2f} mm, se pidieron 10"
    assert real > 12.0, (
        f"la separación quedó en {real:.2f} mm: con un solo candidato permitido "
        "esto tendría que haber caído al camino conservador, que deja la "
        "separación inflada de siempre"
    )
