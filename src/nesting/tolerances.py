"""Tolerancias calibradas para la geometría.

`params.py` necesita estas constantes para validar parámetros sin cargar el
motor. Viven aquí separadas para que no arrastren Shapely ni ezdxf: son dos
números y nada más.
"""

DEFAULT_FLATTEN_TOL = 0.02
"""Millimetres. Well below the raster resolution, so it never dominates error.

`flatten` bounds the *chord* deviation, not the enclosed area, and the two
diverge fast on a curve: at the spec's original 0.2 mm, a 50 mm-radius circle
already loses about half a percent of its true area to the inscribed polygon
(sagitta-based error scales roughly with tolerance / radius). That is fine for
cut geometry but not for the area comparisons the pipeline (and its tests)
run downstream, so this default is ten times tighter than the raster
resolution suggests it needs to be, trading a modest bump in point count for
area error safely under a tenth of a percent on ordinary parts.
"""

DEFAULT_CHAIN_TOL = 0.1
"""Millimetres. Corel exports routinely leave gaps of a few microns."""
