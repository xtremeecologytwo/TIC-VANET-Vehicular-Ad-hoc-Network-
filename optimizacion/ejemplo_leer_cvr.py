"""
ejemplo_leer_cvr.py — leer y analizar las tuplas de conectividad
================================================================
Ejemplo AUTOCONTENIDO de cómo consumir, desde una función independiente, las
estructuras que el proyecto le pasa al solver. No modifica nada: solo lee.

La estructura central es `CVR`, una **lista de tuplas de 4 enteros**:

    CVR: list[tuple[int, int, int, int]]
    #                 s     h     v     r
    #   s = escenario (instante), numerado desde 1
    #   h = nº de saltos; 1..H reales, hmax = H+1 significa "sin servicio"
    #   v = vehículo (el número del id: 'V12' -> 12)
    #   r = RSU; 0 es la RSU artificial r_inf

La descripción completa de todas las estructuras, sus tipos y su ORDEN está en
`ESTRUCTURA_DATOS.md`, en esta misma carpeta.

Uso:
    python optimizacion/ejemplo_leer_cvr.py                    # micro-ejemplo
    python optimizacion/ejemplo_leer_cvr.py --dat ruta/al.dat  # un .dat real
"""

import os
import sys
from collections import defaultdict

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
for p in (RAIZ, AQUI):
    if p not in sys.path:
        sys.path.insert(0, p)


# ======================================================================
# LAS FUNCIONES DE ANÁLISIS — no dependen de docplex ni de archivos
# ======================================================================

def resumen_por_escenario(datos: dict) -> list[dict]:
    """
    Recorre el CVR y resume la conectividad de cada escenario (instante).

    Es el ejemplo de "función independiente que coge esa entrada y la analiza":
    recibe el mismo `dict` que se le pasa al solver y no necesita nada más.

    Parámetros:
        datos: el dict que devuelve `construir_datos_opl()`.

    Retorna:
        Una lista de dicts, uno por escenario y en orden temporal, con:
          "s", "t", "n_vehiculos", "pares_por_salto", "pares_reales",
          "sin_servicio", "vehiculos_sin_ninguna_rsu".
    """
    hmax = datos["hmax"]
    # Los .dat escritos a mano no traen la cabecera de trazabilidad, asi que
    # `mapas` puede faltar. En ese caso se usa el propio numero de escenario.
    t_de_s = datos.get("mapas", {}).get("escenario_a_t", {})

    acumulado = defaultdict(lambda: {"por_salto": defaultdict(int),
                                     "vehiculos": set(),
                                     "con_alguna_rsu": set(),
                                     "sin_servicio": 0})

    # --- El recorrido: aquí se ve lo simple que es consumir la estructura ---
    for s, h, v, r in datos["CVR"]:
        info = acumulado[s]
        info["vehiculos"].add(v)
        if h == hmax:                 # tupla artificial: siempre lleva r == 0
            info["sin_servicio"] += 1
        else:                         # par real vehículo–RSU
            info["por_salto"][h] += 1
            info["con_alguna_rsu"].add(v)

    salida = []
    for s in sorted(acumulado):
        info = acumulado[s]
        salida.append({
            "s": s,
            "t": t_de_s.get(s, float(s)),
            "n_vehiculos": len(info["vehiculos"]),
            "pares_por_salto": dict(sorted(info["por_salto"].items())),
            "pares_reales": sum(info["por_salto"].values()),
            "sin_servicio": info["sin_servicio"],
            # Un vehículo que no aparece en ninguna tupla real no alcanza
            # NINGUNA RSU en ese instante, ni siquiera por multisalto.
            "vehiculos_sin_ninguna_rsu": len(info["vehiculos"] - info["con_alguna_rsu"]),
        })
    return salida


def alcances_de_un_vehiculo(datos: dict, vehiculo: int, escenario: int) -> list[tuple]:
    """
    Todas las RSU que un vehículo alcanza en un escenario, con su nº de saltos
    y el id original de la junction de SUMO.

    Muestra cómo volver de los enteros del modelo a los identificadores reales
    usando `datos["mapas"]`.

    Retorna:
        Lista de (h, r_int, id_junction), ordenada por saltos.
    """
    rsu_de_int = datos.get("mapas", {}).get("int_a_rsu", {})
    hmax = datos["hmax"]
    encontrados = [(h, r, rsu_de_int.get(r, ""))
                   for (s, h, v, r) in datos["CVR"]
                   if s == escenario and v == vehiculo and h != hmax]
    return sorted(encontrados)


def comprobar_integridad(datos: dict) -> dict:
    """
    Comprueba las invariantes que debe cumplir todo CVR bien formado.

    Sirve como validación de que la estructura se leyó (o se construyó) bien.
    """
    hmax = datos["hmax"]
    cvr = datos["CVR"]
    artificiales = [t for t in cvr if t[1] == hmax]
    reales = [t for t in cvr if t[1] != hmax]
    N = sum(len(vs) for vs in datos["Vs"].values())

    return {
        "n_tuplas": len(cvr),
        "reales (K)": len(reales),
        "artificiales (N)": len(artificiales),
        "|CVR| = K + N": len(cvr) == len(reales) + len(artificiales),
        "artificiales == instancias vehiculo-escenario": len(artificiales) == N,
        "h == hmax  <=>  r == 0": all((h == hmax) == (r == 0) for _, h, _, r in cvr),
        "sin tuplas repetidas": len(set(cvr)) == len(cvr),
        "s dentro de S": all(s in set(datos["S"]) for s, _, _, _ in cvr),
        "r dentro de R": all(r in set(datos["R"]) for _, _, _, r in cvr),
    }


# ======================================================================
# DEMOSTRACIÓN
# ======================================================================

def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(
        description="Lee las tuplas de conectividad y las analiza")
    ap.add_argument("--dat", default=os.path.join(AQUI, "rsu_micro.dat"),
                    help="archivo .dat del que leer los datos")
    args = ap.parse_args()

    # `leer_dat` reconstruye el MISMO dict que produce construir_datos_opl(),
    # así que el análisis de abajo sirve igual venga de un .dat o de memoria.
    from explicar_optimizacion import leer_dat
    datos = leer_dat(args.dat)

    print("=" * 70)
    print("  ESTRUCTURA RECIBIDA")
    print("=" * 70)
    print("  CVR es %s de %d elementos" % (type(datos["CVR"]).__name__, len(datos["CVR"])))
    print("  cada elemento: %s -> %s"
          % (type(datos["CVR"][0]).__name__,
             tuple(type(x).__name__ for x in datos["CVR"][0])))
    print("  significado  : (s = escenario, h = saltos, v = vehiculo, r = RSU)")
    print("  primeras 5   :", datos["CVR"][:5])
    print("  hmax = %d  (h == %d significa SIN SERVICIO, y ahi r siempre es 0)"
          % (datos["hmax"], datos["hmax"]))

    print()
    print("=" * 70)
    print("  RESUMEN POR ESCENARIO")
    print("=" * 70)
    print("  %3s %9s %6s %7s %-26s %s"
          % ("s", "t (s)", "veh.", "pares", "pares por salto", "sin RSU"))
    print("  " + "-" * 66)
    for fila in resumen_por_escenario(datos):
        print("  %3d %9.1f %6d %7d %-26s %d"
              % (fila["s"], fila["t"], fila["n_vehiculos"], fila["pares_reales"],
                 fila["pares_por_salto"], fila["vehiculos_sin_ninguna_rsu"]))

    print()
    print("=" * 70)
    print("  UN VEHICULO EN DETALLE")
    print("=" * 70)
    s0 = datos["S"][0]
    v0 = datos["Vs"][s0][0]
    t0 = datos.get("mapas", {}).get("escenario_a_t", {}).get(s0, float(s0))
    print("  escenario %d (t = %.1f s), vehiculo V%d:" % (s0, t0, v0))
    alcances = alcances_de_un_vehiculo(datos, v0, s0)
    if alcances:
        for h, r, junction in alcances[:8]:
            print("     %d salto(s) -> RSU %-4d (junction %s)"
                  % (h, r, junction if junction else "(sin mapa de ids)"))
        if len(alcances) > 8:
            print("     ... y %d mas" % (len(alcances) - 8))
    else:
        print("     no alcanza ninguna RSU en ese instante")

    print()
    print("=" * 70)
    print("  INTEGRIDAD")
    print("=" * 70)
    for clave, valor in comprobar_integridad(datos).items():
        print("  %-46s %s" % (clave, valor))


if __name__ == "__main__":
    main()
