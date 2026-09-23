"""Cuántos procesos puede correr la cartera en esta máquina.

El tope no es sólo la cantidad de núcleos: cada proceso arma su propio
`MaskCache` y sus grillas de placa, así que doce procesos en una máquina de
8 GB la dejarían sin memoria antes de terminar la primera tanda. No se
agregan dependencias para leer la memoria: `os.sysconf` en macOS y Linux,
`GlobalMemoryStatusEx` por `ctypes` en Windows.
"""

import os
import sys
from dataclasses import dataclass

MEMORY_PER_WORKER_BYTES = 2300 * 1024 * 1024
"""Lo que ocupa, como mucho, un proceso de la cartera.

El `MaskCache` tiene un presupuesto de 256 MB (`DEFAULT_CACHE_BUDGET_BYTES`),
y a eso se suman las grillas de la placa (la del oráculo y las
correlaciones de la búsqueda, del orden de decenas de MB a 1 mm/px en la
placa más grande del catálogo) y el propio intérprete con numpy, scipy y
shapely cargados. Ese "decenas de MB" subestimaba la búsqueda por
correlación: a 1 mm/px, con FFT de por medio, las grillas de la placa se
redondean a la potencia de 2 siguiente y se duplican para la parte
compleja, y con 8 orientaciones (4 ángulos, con espejo) el total escala
rápido.

MEDIDO: 2277 MB sobre `bench/files/muestra.dxf` replicado 6 veces (72
piezas), placa 1830x2600, sep 8, borde 5, 1 mm/px, 4 ángulos con espejo,
esfuerzo normal, workers=2, el 2026-09-23. Redondeado hacia arriba a 50 MB:
2300 MB. Se usó la muestra y no `bench/files/banqueta-alta.ai` -- la
banqueta, con 16 orientaciones, superó dos veces el tope de 600 s del
`timeout` de la herramienta sin terminar una sola tanda; la muestra
replicada ya alcanza para medir el pico de un proceso real de la cartera.
"""

MEMORY_SHARE = 0.5
"""Qué parte de la memoria total se deja usar a la cartera. La otra mitad es
del sistema, de la interfaz y de lo que el usuario tenga abierto."""


@dataclass(frozen=True)
class Machine:
    cpus: int
    cap: int
    default: int


def cpu_count() -> int:
    return os.cpu_count() or 1


def total_memory_bytes() -> int | None:
    """La memoria física total, o None si la plataforma no la dice."""
    if sys.platform == "win32":
        return _windows_total_memory()
    try:
        return int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (ValueError, OSError, AttributeError):
        return None


def _windows_total_memory() -> int | None:
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return int(status.ullTotalPhys)


def worker_cap(cpus: int, memory: int | None) -> int:
    """El máximo de procesos: los núcleos, o lo que entra en la mitad de la memoria."""
    by_memory = cpus if memory is None else int(memory * MEMORY_SHARE // MEMORY_PER_WORKER_BYTES)
    return max(1, min(cpus, by_memory))


def default_workers(cpus: int, cap: int) -> int:
    """Todos menos dos, para que la máquina se pueda seguir usando; nunca más que el tope."""
    return max(1, min(cpus - 2, cap))


def machine() -> Machine:
    cpus = cpu_count()
    cap = worker_cap(cpus, total_memory_bytes())
    return Machine(cpus=cpus, cap=cap, default=default_workers(cpus, cap))
