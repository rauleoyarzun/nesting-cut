"""La interfaz gráfica sobre el motor de nesting.

Este paquete conoce a `nesting`. `nesting` no conoce a este. Esa dirección
es la que permite que la CLI, los tests del motor y el motor mismo sigan
existiendo sin saber que hay una interfaz, y la que va a permitir que el día
de mañana la misma API se sirva desde un servidor web en vez de desde una
ventana.
"""
