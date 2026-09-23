"""Cuántos núcleos puede usar la cartera en esta máquina."""

from nesting.engine import workers
from nesting.engine.workers import (
    MEMORY_PER_WORKER_BYTES,
    Machine,
    default_workers,
    machine,
    worker_cap,
)

GB = 1024**3


def test_con_memoria_de_sobra_el_tope_son_los_nucleos():
    assert worker_cap(14, 64 * GB) == 14


def test_con_poca_memoria_el_tope_lo_pone_la_memoria():
    """La mitad de la memoria, dividida por lo que ocupa un proceso."""
    memoria = 12 * MEMORY_PER_WORKER_BYTES * 2
    assert worker_cap(14, memoria) == 12


def test_el_tope_nunca_baja_de_uno():
    assert worker_cap(14, 1) == 1
    assert worker_cap(1, 64 * GB) == 1


def test_sin_saber_la_memoria_el_tope_son_los_nucleos():
    assert worker_cap(8, None) == 8


def test_por_omision_se_dejan_dos_nucleos_libres():
    assert default_workers(14, 14) == 12
    assert default_workers(14, 10) == 10, "y nunca por encima del tope"
    assert default_workers(2, 2) == 1
    assert default_workers(1, 1) == 1


def test_la_maquina_se_lee_una_vez_con_las_tres_cifras(monkeypatch):
    monkeypatch.setattr(workers, "cpu_count", lambda: 14)
    monkeypatch.setattr(workers, "total_memory_bytes", lambda: 64 * GB)
    assert machine() == Machine(cpus=14, cap=14, default=12)


def test_la_memoria_de_esta_maquina_se_puede_leer():
    """En macOS y Linux por `os.sysconf`, en Windows por
    `GlobalMemoryStatusEx`. Si una plataforma no la da, el tope cae a la
    cantidad de núcleos, pero en las tres donde corre esto sí la da."""
    memoria = workers.total_memory_bytes()
    assert memoria is not None and memoria > GB
