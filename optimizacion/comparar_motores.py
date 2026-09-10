"""
comparar_motores.py — ¿docplex y oplrun dan lo mismo?
======================================================
Resuelve **los mismos datos** con los dos motores y compara los resultados
campo a campo:

  * docplex  — el modelo construido en memoria por `optimizar_rsu.py`
  * oplrun   — el modelo en lenguaje OPL (`rsu_model_lex.mod`) ejecutado por
               el binario de IBM ILOG CPLEX Optimization Studio

Ambos resuelven la misma formulación (Urquiza-Aguiar et al., 2016) con el mismo
multi-objetivo lexicográfico de tres niveles. Si coinciden, el modelo está bien
traducido a las dos herramientas. Si no, una de las dos está mal.

QUÉ SE COMPARA Y QUÉ NO
-----------------------
Se comparan las magnitudes que tienen que ser IGUALES: los tres valores
objetivo, el número de RSU, la cobertura y el reparto por saltos.

**El CONJUNTO de RSU elegidas NO tiene por qué coincidir**, y que difiera no es
un error. El problema tiene muchas soluciones óptimas equivalentes —RSU
candidatas casi intercambiables— y cada motor puede quedarse con una distinta
según cómo recorra el árbol de búsqueda. Lo que debe coincidir es el VALOR, no
la elección concreta. Por eso se informa aparte, como dato, no como fallo.

Uso:
    python optimizacion/comparar_motores.py --micro
    python optimizacion/comparar_motores.py --dat optimizacion/rsu_backend.dat
"""

import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
for p in (RAIZ, AQUI):
    if p not in sys.path:
        sys.path.insert(0, p)

from explicar_optimizacion import leer_dat          # noqa: E402
from optimizar_rsu import optimizar                 # noqa: E402
import resolver_opl                                 # noqa: E402

# Tolerancia al comparar flotantes. Los dos motores usan el mismo CPLEX, pero
# el valor llega por caminos distintos (API en memoria vs texto impreso por
# OPL), así que conviene un margen para el redondeo de la impresión.
TOL_REL = 1e-6
TOL_ABS = 1e-6


def _iguales(a, b) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= max(TOL_ABS, TOL_REL * max(abs(a), abs(b)))


def _fmt(v, dec=2):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:,.{dec}f}".replace(",", " ")
    return str(v)


def comparar(dat_path: str, limite_tiempo: float | None = None) -> bool:
    """
    Resuelve `dat_path` con los dos motores y compara. Devuelve True si todo
    lo que debe coincidir coincide.
    """
    print(f"datos : {dat_path}")
    datos = leer_dat(dat_path)
    n_pares = sum(len(datos["Vs"][s]) for s in datos["S"])
    print(f"        {len(datos['CVR'])} tuplas CVR | {len(datos['R']) - 1} RSU "
          f"candidatas | {n_pares} pares (instante, vehiculo)\n")

    print("resolviendo con docplex...")
    t0 = time.perf_counter()
    a = optimizar(datos, limite_tiempo=limite_tiempo, lexicografico=True)
    ta = time.perf_counter() - t0
    print(f"   {ta:.1f} s  ({a['status']})")

    print("resolviendo con oplrun...")
    t0 = time.perf_counter()
    b = resolver_opl.resolver(dat_path, limite_tiempo=limite_tiempo)
    tb = time.perf_counter() - t0
    print(f"   {tb:.1f} s  ({b['status']})\n")

    if a["reparto"] is None or b["reparto"] is None:
        print("Alguno de los motores no devolvió solución; no hay nada que comparar.")
        print(f"   docplex: {a['status']}")
        print(f"   oplrun : {b['status']}")
        return False

    ra, rb = a["reparto"], b["reparto"]
    oa = a["objetivos"] or [None, None, None]
    ob = b["objetivos"] or [None, None, None]

    filas = [
        ("obj 1 - desconexion", oa[0], ob[0]),
        ("obj 2 - instalacion", oa[1], ob[1]),
        ("obj 3 - trafico", oa[2], ob[2]),
        ("objetivo (Ec. 1)", a["objetivo"], b["objetivo"]),
        ("RSU desplegadas", float(a["n_rsu_elegidos"]), float(b["n_rsu_elegidos"])),
        ("pares totales", float(ra["n_pares"]), float(rb["n_pares"])),
        ("desconectados", ra["desconectados"], rb["desconectados"]),
        ("directos (1 salto)", ra["directos"], rb["directos"]),
        ("multisalto", ra["multisalto"], rb["multisalto"]),
        ("cobertura %", ra["cobertura_pct"], rb["cobertura_pct"]),
    ]

    print(f"{'magnitud':<22} {'docplex':>16} {'oplrun':>16}   ")
    print("-" * 62)
    todo_ok = True
    for nombre, va, vb in filas:
        ok = _iguales(va, vb)
        todo_ok = todo_ok and ok
        print(f"{nombre:<22} {_fmt(va):>16} {_fmt(vb):>16}   {'OK' if ok else 'DIFIERE'}")

    # El conjunto concreto de RSU es informativo, NO un criterio de fallo.
    sa, sb = set(a["seleccionados"]), set(b["seleccionados"])
    comunes = len(sa & sb)
    print()
    print(f"{'RSU en comun':<22} {comunes} de {len(sa)} / {len(sb)}")
    if sa != sb:
        print("   (conjuntos distintos: NORMAL. Hay muchas soluciones optimas")
        print("    equivalentes y cada motor puede quedarse con una. Lo que debe")
        print("    coincidir es el VALOR objetivo, no que elijan las mismas antenas.)")

    print()
    print(f"{'tiempo':<22} {ta:>15.1f}s {tb:>15.1f}s")
    print()
    print("VEREDICTO:", "los dos motores COINCIDEN" if todo_ok
          else "HAY DIFERENCIAS -> revisar la traduccion del modelo")
    return todo_ok


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Compara docplex contra oplrun")
    ap.add_argument("--dat", default=None, help="archivo .dat a comparar")
    ap.add_argument("--micro", action="store_true",
                    help="usa el micro-ejemplo de validacion")
    ap.add_argument("--tope", type=float, default=None,
                    help="limite de tiempo por motor, en segundos")
    args = ap.parse_args()

    dat = args.dat or os.path.join(
        AQUI, "rsu_micro.dat" if args.micro else "rsu_backend.dat")
    if not os.path.exists(dat):
        print(f"No existe {dat}. Genera un escenario primero, o usa --micro.")
        sys.exit(1)

    sys.exit(0 if comparar(dat, limite_tiempo=args.tope) else 1)


if __name__ == "__main__":
    main()
