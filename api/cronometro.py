"""
Cronómetro de etapas (instrumentación de tiempos por consola)
=============================================================
Mide cuánto tarda **cada acción del usuario** (cada clic de la interfaz) y lo
imprime en la consola donde corre `uvicorn`. No devuelve nada al frontend: es
una herramienta de medición para el propio desarrollo/experimentación.

Qué imprime, para una corrida completa:

    ================================================================
      SmartCityNet - CRONOMETRO DE ETAPAS   (nueva sesion)
    ================================================================

    [1] M1 - Generar escenario
          - Descarga OSM ...........................    2.913 s
          - SUMO (netconvert/polyconvert/trips) ....    8.402 s
          - Parseo junctions + edificios ...........    0.512 s
        > etapa  11.827 s  |  acumulado  11.827 s

    ...

    ================================================================
      RESUMEN DE TIEMPOS
    ================================================================
      1. M1 - Generar escenario ..............   11.827 s   ( 37.1 %)
      ...
      ----------------------------------------------------------
      TOTAL ..................................   31.890 s
    ================================================================

Dos niveles de medición:

* `etapa(...)`   → una acción del usuario (un clic). Suma al TOTAL.
* `subetapa(...)`→ una fase interna de esa acción (descarga, SUMO, LoS, solver…).
                   Es informativa: **no** se suma aparte, ya está dentro de la
                   etapa que la contiene.

Uso:

    from api import cronometro as cron

    cron.nueva_sesion("Escenario nuevo")          # opcional: reinicia contadores
    with cron.etapa("M1 - Generar escenario"):
        with cron.subetapa("Descarga OSM"):
            ...
    cron.resumen()                                 # tabla final con la suma

Nota sobre caracteres: la consola de Windows no siempre puede imprimir símbolos
fuera de su página de códigos, así que el marco es ASCII puro y `_emitir()`
degrada con elegancia si algún acento no se pudiera representar.
"""

import sys
import time
from contextlib import contextmanager

# Ancho de la columna del nombre (para que los puntos suspensivos alineen).
_ANCHO_NOMBRE = 58
_ANCHO_MARCO = 80


# ============================================================
# ESTADO DE LA SESIÓN DE MEDICIÓN
# ============================================================
# Una "sesión" es una corrida del flujo: normalmente empieza al generar un
# escenario nuevo y termina cuando se optimiza. Se guarda en memoria del
# proceso de la API (igual que STATE en api/main.py).

_SESION: dict = {
    "titulo": None,
    "pasos": [],     # [{"n", "nombre", "segundos", "ok"}]
    "total": 0.0,
    "abierta": False,
}


def _emitir(linea: str = "") -> None:
    """`print` a prueba de consolas con codificación limitada (cp1252, cp850…)."""
    try:
        print(linea, flush=True)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        print(linea.encode(enc, errors="replace").decode(enc), flush=True)


def _seg(segundos: float) -> str:
    """Formatea segundos con 3 decimales y ancho fijo: '  11.827 s'."""
    return f"{segundos:9.3f} s"


def _rellenar(texto: str, ancho: int = _ANCHO_NOMBRE) -> str:
    """'Descarga OSM' -> 'Descarga OSM .....................' (ancho fijo)."""
    if len(texto) >= ancho:
        return texto[:ancho - 1] + " "
    return texto + " " + "." * (ancho - len(texto) - 2) + " "


def nueva_sesion(titulo: str = "nueva sesion") -> None:
    """Reinicia los contadores e imprime la cabecera de una corrida nueva."""
    _SESION["titulo"] = titulo
    _SESION["pasos"] = []
    _SESION["total"] = 0.0
    _SESION["abierta"] = True
    _emitir()
    _emitir("=" * _ANCHO_MARCO)
    _emitir(f"  SmartCityNet - CRONOMETRO DE ETAPAS   ({titulo})")
    _emitir("=" * _ANCHO_MARCO)


@contextmanager
def etapa(nombre: str):
    """
    Mide una acción del usuario (un clic) y la suma al total de la sesión.

    Imprime el nombre de la etapa al empezar (para ver en vivo qué está
    corriendo) y, al terminar, su duración y el acumulado de la sesión. Si la
    acción falla, igual registra el tiempo y lo marca como fallida.

    Parámetros:
        nombre: etiqueta de la etapa, p. ej. "M2 - Simular conectividad".
    """
    if not _SESION["abierta"]:
        # Alguien empezó por la mitad del flujo (p. ej. retomando un escenario
        # ya guardado en output/): abrimos sesión sin perder la medición.
        nueva_sesion("sesion iniciada sobre escenario existente")

    n = len(_SESION["pasos"]) + 1
    _emitir()
    _emitir(f"[{n}] {nombre}")
    t0 = time.perf_counter()
    ok = True
    try:
        yield
    except Exception:
        ok = False
        raise
    finally:
        dt = time.perf_counter() - t0
        _SESION["pasos"].append({"n": n, "nombre": nombre, "segundos": dt, "ok": ok})
        _SESION["total"] += dt
        marca = "> etapa" if ok else "> etapa (FALLO)"
        _emitir(f"    {marca} {_seg(dt)}  |  acumulado {_seg(_SESION['total'])}")


class Medicion:
    """Objeto que devuelve `subetapa`: al salir del `with` trae `.segundos`."""

    def __init__(self) -> None:
        self.segundos = 0.0


@contextmanager
def subetapa(nombre: str):
    """
    Mide una fase interna de la etapa en curso (descarga, SUMO, LoS, solver…).

    Su tiempo ya está contenido en el de la etapa: se imprime indentado y
    **no** se suma al total, solo sirve para ver dónde se va el tiempo.

    Cede un objeto `Medicion`; al terminar el bloque, `m.segundos` guarda lo que
    tardó (útil para devolvérselo al frontend, p. ej. el tiempo del solver):

        with cron.subetapa("Solver CPLEX") as m:
            res = optimizar(...)
        print(m.segundos)
    """
    m = Medicion()
    t0 = time.perf_counter()
    try:
        yield m
    finally:
        m.segundos = time.perf_counter() - t0
        _emitir(f"      - {_rellenar(nombre, _ANCHO_NOMBRE - 4)}{_seg(m.segundos)}")


def nota(texto: str) -> None:
    """
    Imprime una línea informativa indentada bajo la subetapa recién medida.

    Sirve para dejar constancia de algo que no es un tiempo pero explica el que
    se acaba de medir, p. ej. cómo terminó el solver.
    """
    _emitir(f"        ({texto})")


def resumen(titulo: str = "RESUMEN DE TIEMPOS") -> dict:
    """
    Imprime la tabla final con el tiempo de cada etapa, su peso relativo y la
    SUMA total de la sesión. Se llama al terminar el flujo (tras optimizar).

    Retorna:
        dict con los pasos y el total, por si se quisiera exponer o registrar.
    """
    pasos = _SESION["pasos"]
    total = _SESION["total"]
    if not pasos:
        return {"pasos": [], "total": 0.0}

    _emitir()
    _emitir("=" * _ANCHO_MARCO)
    _emitir(f"  {titulo}")
    _emitir("=" * _ANCHO_MARCO)
    for p in pasos:
        pct = (100.0 * p["segundos"] / total) if total else 0.0
        estado = "" if p["ok"] else "  (fallo)"
        _emitir(f"  {p['n']:>2}. {_rellenar(p['nombre'])}{_seg(p['segundos'])}"
                f"   ({pct:5.1f} %){estado}")
    _emitir("  " + "-" * (_ANCHO_MARCO - 4))
    _emitir(f"  {'':>2}  {_rellenar('TOTAL')}{_seg(total)}")
    _emitir("=" * _ANCHO_MARCO)
    _emitir()
    return {"pasos": list(pasos), "total": total}
