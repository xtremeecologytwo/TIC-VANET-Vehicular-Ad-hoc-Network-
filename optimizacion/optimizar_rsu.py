"""
optimizar_rsu.py  —  Optimización de despliegue de RSU con docplex (Python)
==========================================================================
ANTES este módulo llamaba al binario `oplrun` de IBM CPLEX Optimization
Studio, pasándole el modelo OPL (`rsu_model.mod`) + un archivo de datos
`.dat`. AHORA el modelo se construye y se resuelve **directamente en Python**
con la librería `docplex` (IBM Decision Optimization CPLEX Modeling for
Python), que usa el motor CPLEX como backend.

Ventajas de la migración OPL/oplrun -> docplex:
  - No hace falta invocar un ejecutable externo ni generar/parsear texto:
    todo ocurre en memoria dentro de Python.
  - Los datos de entrada son el MISMO dict que ya construye
    `backend/exportar_dat.py::construir_datos_opl()`. El archivo `.dat` de
    OPL se sigue pudiendo generar para inspección/compatibilidad, pero para
    resolver ya no se necesita.
  - La solución (RSU elegidos, valor objetivo) vuelve como objetos Python.

El modelo matemático es EXACTAMENTE el de `optimizacion/rsu_model.mod`
(Urquiza-Aguiar et al., 2016). Se traduce término por término:

    Variables:
        Sel[r] ∈ {0,1}    1 si se despliega el RSU r         (1ª etapa)
        Rts[t] ∈ [0,1]    fracción de carga servida (t ∈ CVR) (2ª etapa)

    minimizar:  Σ_r Sel[r]·Cost[r]  +  Σ_t Rts[t]·P[t.h]·L[t.s][t.v]

    s.a.
      (Ec.2)  ∀s, ∀v∈Vs[s]:  Σ_{t: t.s=s, t.v=v} Rts[t] == 1
      (Ec.3)  ∀t∈CVR:        Rts[t] ≤ Sel[t.r]
      (Ec.4)  ∀s, ∀r≠rInf:   Σ_{t: t.s=s, t.r=r} Rts[t]·P[t.h]·L[t.s][t.v] ≤ Cap[r]
      (Ec.5)  Σ_{r≠rInf} Sel[r] ≤ MaxR
              Sel[rInf] == 1

--------------------------------------------------------------------------
Requisitos:
    pip install docplex cplex
  `docplex` es la capa de modelado; `cplex` es el motor (viene con IBM CPLEX
  Optimization Studio; también hay una edición community limitada a 1000
  variables/restricciones). Como ya tenías CPLEX Studio para `oplrun`, la
  forma más directa de instalar el motor es, desde su carpeta:
    python <CPLEX_Studio>/python/setup.py install

Uso rápido (línea de comandos):

    # 1) Genera el .dat y RESUELVE con docplex, leyendo output/*.json
    python optimizacion/optimizar_rsu.py --H 3 --max-rsu 10

    # 2) Auto-test con el micro-ejemplo (no necesita output/, valida la
    #    lógica del modelo: debe elegir {R1, R3})
    python optimizacion/optimizar_rsu.py --micro
"""

import os
import sys
from collections import defaultdict

# El paquete backend/ está en la raíz del repo; lo añadimos al path para
# poder importar la construcción de datos que ya existe.
AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

# UTF-8 en consola de Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ============================================================
# CONSTRUCCIÓN + RESOLUCIÓN DEL MODELO CON docplex
# ============================================================


def construir_modelo(datos: dict):
    """
    Construye el modelo de optimización con docplex a partir del dict de
    datos que produce `backend.exportar_dat.construir_datos_opl()`.

    Es la traducción 1:1 de `rsu_model.mod`.

    Parámetros:
        datos: dict con las claves hmax, rInf, MaxR, R, S, V, Vs, Cost, Cap,
               P, L, CVR (ver construir_datos_opl).

    Retorna:
        (mdl, Sel, Rts):
          - mdl: instancia docplex.mp.model.Model lista para resolver.
          - Sel: dict {r -> var binaria}.
          - Rts: dict {(s,h,v,r) -> var continua en [0,1]}.
    """
    # Import perezoso: así el resto del módulo (y el --micro sin resolver)
    # no fallan si docplex no está instalado; solo falla al construir.
    try:
        from docplex.mp.model import Model
    except ImportError as e:
        raise ImportError(
            "No se encontró 'docplex'. Instálalo con:  pip install docplex cplex\n"
            "El motor 'cplex' viene con IBM CPLEX Optimization Studio (el mismo "
            "que usabas para oplrun): python <CPLEX_Studio>/python/setup.py install"
        ) from e

    hmax = datos["hmax"]
    rInf = datos["rInf"]
    MaxR = datos["MaxR"]
    R = datos["R"]
    S = datos["S"]
    Vs = datos["Vs"]      # {s: [v, ...]}
    Cost = datos["Cost"]  # {r: costo}
    Cap = datos["Cap"]    # {r: capacidad}
    P = datos["P"]        # lista de longitud hmax; P[h-1] = penalización de h saltos
    L = datos["L"]        # {s: {v: carga}}
    CVR = datos["CVR"]    # lista de tuplas (s, h, v, r)

    def Ph(h: int) -> float:
        """P está indexado 1..hmax en OPL; en la lista Python es P[h-1]."""
        return P[h - 1]

    mdl = Model(name="rsu_placement")

    # ---- Variables ----
    Sel = mdl.binary_var_dict(R, name="Sel")
    Rts = {
        t: mdl.continuous_var(lb=0.0, ub=1.0, name=f"Rts_{t[0]}_{t[1]}_{t[2]}_{t[3]}")
        for t in CVR
    }

    # ---- Pre-indexado de CVR para que las restricciones sean eficientes ----
    cvr_por_sv = defaultdict(list)   # (s, v) -> [tuplas]
    cvr_por_sr = defaultdict(list)   # (s, r) -> [tuplas]
    for t in CVR:
        s, h, v, r = t
        cvr_por_sv[(s, v)].append(t)
        cvr_por_sr[(s, r)].append(t)

    # ---- Objetivo (Ec. 1) ----
    coste_instalacion = mdl.sum(Sel[r] * Cost[r] for r in R)
    coste_trafico = mdl.sum(Rts[t] * Ph(t[1]) * L[t[0]][t[2]] for t in CVR)
    mdl.minimize(coste_instalacion + coste_trafico)

    # ---- (Ec. 2) toda la carga de cada vehículo de cada escenario se sirve ----
    for s in S:
        for v in Vs[s]:
            mdl.add_constraint(
                mdl.sum(Rts[t] for t in cvr_por_sv[(s, v)]) == 1,
                ctname=f"servir_s{s}_v{v}",
            )

    # ---- (Ec. 3) solo se puede usar un RSU si está seleccionado ----
    for t in CVR:
        mdl.add_constraint(Rts[t] <= Sel[t[3]])

    # ---- (Ec. 4) capacidad de cada RSU real (no aplica a rInf) ----
    for s in S:
        for r in R:
            if r == rInf:
                continue
            terms = [Rts[t] * Ph(t[1]) * L[t[0]][t[2]] for t in cvr_por_sr[(s, r)]]
            if terms:
                mdl.add_constraint(mdl.sum(terms) <= Cap[r],
                                   ctname=f"cap_s{s}_r{r}")

    # ---- (Ec. 5) nº máximo de RSU reales desplegados ----
    mdl.add_constraint(mdl.sum(Sel[r] for r in R if r != rInf) <= MaxR,
                       ctname="max_rsu")

    # ---- El RSU artificial siempre está "disponible" ----
    mdl.add_constraint(Sel[rInf] == 1, ctname="rinf_siempre")

    return mdl, Sel, Rts


def optimizar(datos: dict, mostrar_log: bool = False,
              limite_tiempo: float | None = None) -> dict:
    """
    Construye y resuelve el modelo con docplex/CPLEX.

    Parámetros:
        datos: dict de datos (de construir_datos_opl / exportar_dat).
        mostrar_log: si True, imprime el log del motor CPLEX.
        limite_tiempo: límite de tiempo en segundos (None = sin límite).

    Retorna:
        dict:
          "objetivo": valor de la función objetivo (float) o None si infactible,
          "seleccionados": [ids OPL de los RSU reales elegidos] (list[int]),
          "seleccionados_backend": [ids reales del backend] (usa el mapa inverso),
          "status": estado del solver (str),
          "n_rsu_elegidos": int,
    """
    mdl, Sel, Rts = construir_modelo(datos)

    if limite_tiempo is not None:
        mdl.set_time_limit(limite_tiempo)

    # La edición COMMUNITY de CPLEX limita a 1000 variables/restricciones.
    # El problema real (miles de tuplas CVR) la supera: hay que usar el motor
    # COMPLETO de CPLEX Studio. Capturamos ese caso con un mensaje claro en
    # vez de un traceback.
    try:
        from docplex.mp.utils import DOcplexLimitsExceeded
    except Exception:  # versión de docplex sin esa clase
        DOcplexLimitsExceeded = ()

    try:
        sol = mdl.solve(log_output=mostrar_log)
    except DOcplexLimitsExceeded as e:
        n_v = mdl.number_of_variables
        n_c = mdl.number_of_constraints
        return {
            "objetivo": None,
            "seleccionados": [],
            "seleccionados_backend": [],
            "status": (
                f"community-limit-exceeded ({n_v} vars, {n_c} restricciones > 1000). "
                "Usa el motor COMPLETO de CPLEX Studio (Python 3.7–3.10), o reduce "
                "el problema (--max-rsu menor, menos escenarios, o prueba --micro)."
            ),
            "n_rsu_elegidos": 0,
        }

    if sol is None:
        return {
            "objetivo": None,
            "seleccionados": [],
            "seleccionados_backend": [],
            "status": mdl.solve_details.status if mdl.solve_details else "sin solución",
            "n_rsu_elegidos": 0,
        }

    rInf = datos["rInf"]
    seleccionados = sorted(
        r for r in datos["R"] if r != rInf and sol.get_value(Sel[r]) > 0.5
    )

    # Mapa entero_OPL -> id_backend para reportar RSU reales
    int_a_rsu = datos.get("mapas", {}).get("int_a_rsu", {})
    seleccionados_backend = [int_a_rsu.get(r, r) for r in seleccionados]

    return {
        "objetivo": sol.get_objective_value(),
        "seleccionados": seleccionados,
        "seleccionados_backend": seleccionados_backend,
        "status": mdl.solve_details.status,
        "n_rsu_elegidos": len(seleccionados),
    }


# ============================================================
# MICRO-EJEMPLO EN MEMORIA (auto-test, réplica de rsu_micro.dat)
# ============================================================


def _datos_micro() -> dict:
    """
    Reproduce en Python el contenido de `optimizacion/rsu_micro.dat`.

    Sirve para validar que el modelo docplex da la MISMA respuesta que el
    OPL original: con MaxR=2 el óptimo debe elegir {R1, R3}.
    """
    return {
        "hmax": 3,
        "rInf": 0,
        "MaxR": 2,
        "R": [0, 1, 2, 3],
        "S": [1, 2],
        "V": [1, 2, 3, 4],
        "Vs": {1: [1, 2, 3], 2: [1, 2, 4]},
        "Cost": {0: 0.0, 1: 1.0, 2: 1.0, 3: 1.0},
        "Cap": {0: 1000.0, 1: 100.0, 2: 100.0, 3: 100.0},
        "P": [1.0, 2.0, 1000.0],  # P[1..3]
        "L": {1: {1: 1, 2: 1, 3: 1, 4: 1},
              2: {1: 1, 2: 1, 3: 1, 4: 1}},
        "CVR": [
            # escenario 1
            (1, 1, 1, 1), (1, 2, 2, 1), (1, 1, 2, 2), (1, 1, 3, 2), (1, 2, 3, 1),
            # escenario 2
            (2, 1, 1, 1), (2, 2, 2, 1), (2, 1, 4, 3),
            # r_inf (desconexión) para cada vehículo presente
            (1, 3, 1, 0), (1, 3, 2, 0), (1, 3, 3, 0),
            (2, 3, 1, 0), (2, 3, 2, 0), (2, 3, 4, 0),
        ],
        "mapas": {"int_a_rsu": {1: "R1", 2: "R2", 3: "R3"}},
        "resumen": {"H": 2, "n_escenarios": 2, "n_vehiculos": 4,
                    "n_rsu_candidatos": 3, "n_rsu_totales_backend": 3,
                    "n_tuplas_CVR": 14, "max_rsu": 2},
    }


# ============================================================
# IMPRESIÓN DE RESULTADOS
# ============================================================


def _imprimir_resultado(res: dict):
    """Imprime la solución con el mismo espíritu que el bloque IMPRIMIR de OPL."""
    print("=" * 60)
    print("  RESULTADO DE LA OPTIMIZACIÓN (docplex / CPLEX)")
    print("=" * 60)
    if res["objetivo"] is None:
        print(f"\n  ⚠️  Sin solución. Estado del solver: {res['status']}\n")
        return
    print(f"\n  OBJETIVO = {res['objetivo']:.4f}   (estado: {res['status']})")
    if res["seleccionados"]:
        print(f"\n  ✅ RSU a desplegar (ids OPL):     {res['seleccionados']}")
        print(f"     RSU a desplegar (ids backend):  {res['seleccionados_backend']}")
        print(f"     Total desplegados: {res['n_rsu_elegidos']}")
    else:
        print("\n  (No se seleccionó ninguna RSU real.)")
    print("\n  — La función objetivo combina el costo de instalar las RSU con el")
    print("    tráfico penalizado por número de saltos; CPLEX minimiza ese total.\n")


# ============================================================
# CLI
# ============================================================


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Optimiza el despliegue de RSU con docplex/CPLEX.")
    parser.add_argument("--output-dir", default=os.path.join(RAIZ, "output"),
                        help="Carpeta con tuplas_v2v.json y tuplas_visibilidad.json")
    parser.add_argument("--dat", default=os.path.join(AQUI, "rsu_backend.dat"),
                        help="Ruta del .dat de OPL a (re)generar para inspección")
    parser.add_argument("--H", type=int, default=3, help="Nº máximo de saltos reales")
    parser.add_argument("--max-rsu", type=int, default=None,
                        help="MaxR: nº máximo de RSU reales a desplegar")
    parser.add_argument("--todos-los-rsu", action="store_true",
                        help="Incluir TODOS los RSU candidatos (no solo los conectados)")
    parser.add_argument("--log", action="store_true",
                        help="Mostrar el log del motor CPLEX")
    parser.add_argument("--tiempo", type=float, default=None,
                        help="Límite de tiempo del solver en segundos")
    parser.add_argument("--micro", action="store_true",
                        help="Resolver el micro-ejemplo de validación (esperado: {R1, R3})")
    args = parser.parse_args()

    if args.micro:
        print("▶ Micro-ejemplo de validación (réplica de rsu_micro.dat)\n")
        datos = _datos_micro()
        res = optimizar(datos, mostrar_log=args.log, limite_tiempo=args.tiempo)
        _imprimir_resultado(res)
        esperado = [1, 3]
        ok = res["seleccionados"] == esperado
        print(f"  Validación: esperado {esperado}, obtenido {res['seleccionados']} "
              f"-> {'✅ OK' if ok else '❌ DISTINTO'}")
        sys.exit(0 if ok else 1)

    # ---- Caso real: leer los JSON del backend, generar el .dat y resolver ----
    from backend.exportar_dat import exportar_dat_desde_json

    print("▶ Generando el .dat desde output/ (backend.exportar_dat) ...")
    datos = exportar_dat_desde_json(
        args.output_dir, args.dat, H=args.H, max_rsu=args.max_rsu,
        solo_rsu_conectados=not args.todos_los_rsu,
    )
    r = datos["resumen"]
    print(f"  .dat escrito en: {args.dat}")
    print(f"  Escenarios: {r['n_escenarios']} | Vehículos: {r['n_vehiculos']} | "
          f"RSU candidatos: {r['n_rsu_candidatos']} | CVR: {r['n_tuplas_CVR']} | "
          f"MaxR: {r['max_rsu']}\n")

    print("▶ Resolviendo con docplex/CPLEX ...")
    res = optimizar(datos, mostrar_log=args.log, limite_tiempo=args.tiempo)
    _imprimir_resultado(res)


if __name__ == "__main__":
    main()
