"""
Exportación de datos del backend a un archivo .dat de OPL/CPLEX
==============================================================
Este módulo es el "puente" entre la parte VANET del proyecto (que genera las
matrices de conectividad A y B por instante) y la parte de OPTIMIZACIÓN
(`optimizacion/rsu_model.mod`, resuelto con IBM CPLEX vía `oplrun`).

    tuplas_v2v.json  (Matriz A: V2V)  ─┐
                                        ├─► multisalto (S_h) ─► CVR ─► .dat
    tuplas_visibilidad.json (Matriz B) ─┘

El modelo OPL espera un archivo de datos `.dat` con estos conjuntos y
parámetros (ver `optimizacion/rsu_model.mod`):

    hmax, rInf, MaxR
    R  = { ids de RSU candidatos, incluyendo 0 = r_inf }
    S  = { ids de escenarios/snapshots }
    V  = { ids de todos los vehículos }
    Vs[S]      = vehículos presentes en cada escenario
    Cost[R]    = costo de instalar cada RSU  (Cost[r_inf] = 0)
    Cap[R]     = capacidad de cada RSU       (Cap[r_inf]  = grande)
    P[1..hmax] = penalización por nº de saltos (P[hmax] = grande: desconexión)
    L[S][V]    = carga de tráfico de cada vehículo en cada escenario
    CVR = { <s, h, v, r> }  tuplas de conectividad

La idea clave (documentada en `rsu_model.mod`) es:

    "La entrada CVR = {<s,h,v,r>} se construye desde las matrices S_h del
     proyecto (multisalto): un 1 en S_h[v][r] del escenario s -> <s,h,v,r>."

Es decir: cada INSTANTE de tiempo de la simulación se convierte en un
ESCENARIO s. Para ese instante se calculan las matrices de PRIMERA APARICIÓN
S_1..S_H (con `backend.multisalto`); cada 1 en S_h en la posición (vehículo,
RSU) produce una tupla <s, h, v, r>, donde h = mínimo nº de saltos con que ese
vehículo alcanza ese RSU.

Además, a cada vehículo presente en un escenario se le añade la opción de
"desconectarse" cayendo en el RSU artificial r_inf (id 0) al salto hmax = H+1,
con una penalización enorme (P[hmax]). Esto garantiza que el modelo SIEMPRE
sea factible (todo vehículo tiene al menos una opción) y que la desconexión
solo se use como último recurso.

--------------------------------------------------------------------------
IMPORTANTE: este módulo SOLO genera el .dat. No ejecuta el solver ni se
conecta con la interfaz (app.py). Ese es un paso posterior.
--------------------------------------------------------------------------

Uso rápido (línea de comandos):

    # Lee output/tuplas_v2v.json + output/tuplas_visibilidad.json,
    # calcula el multisalto y escribe optimizacion/rsu_backend.dat
    python -m backend.exportar_dat

    # Con parámetros:
    python -m backend.exportar_dat --H 3 --max-rsu 10
"""

import os
import re
import json

from backend.multisalto import analizar_todos


# ============================================================
# MAPEO DE IDs (string del backend  ->  entero para OPL)
# ============================================================
#
# El backend usa ids como "V0", "V12" (vehículos) y "268824778" (RSU). OPL
# trabaja con conjuntos de ENTEROS ({int} R, {int} V, ...). Por eso hay que
# traducir cada id a un entero estable y guardar el diccionario inverso para
# poder interpretar la solución del solver después.


def _id_vehiculo_a_int(v_str: str) -> int:
    """
    Convierte un id de vehículo del backend ("V0", "V12", ...) en un entero.

    Toma los dígitos del id: "V0" -> 0, "V137" -> 137. Como los ids de SUMO
    son únicos y numéricos, esto produce un entero estable por vehículo (no
    hace falta un contador). Si el id no tuviera dígitos, se lanza un error.

    Parámetros:
        v_str: id de vehículo tal como aparece en las matrices V2V.

    Retorna:
        Entero identificador del vehículo (para el conjunto V de OPL).
    """
    m = re.search(r"\d+", str(v_str))
    if m is None:
        raise ValueError(f"Id de vehículo sin dígitos, no se puede mapear: {v_str!r}")
    return int(m.group())


def _construir_mapa_rsu(rsu_ids: list) -> tuple[dict, dict]:
    """
    Asigna un entero 1..m a cada RSU candidato (0 se reserva para r_inf).

    Parámetros:
        rsu_ids: lista ordenada (canónica) de ids de RSU del backend.

    Retorna:
        (rsu_a_int, int_a_rsu):
          - rsu_a_int: {id_backend -> entero 1..m}
          - int_a_rsu: {entero -> id_backend}  (para leer la solución)
    """
    rsu_a_int = {rid: i + 1 for i, rid in enumerate(rsu_ids)}
    int_a_rsu = {i + 1: rid for i, rid in enumerate(rsu_ids)}
    return rsu_a_int, int_a_rsu


# ============================================================
# CONSTRUCCIÓN DE LA ESTRUCTURA DE DATOS OPL
# ============================================================


def construir_datos_opl(matrices_v2v: dict, tuplas_v2i: list, rsu_ids: list,
                        H: int = 3, max_rsu: int | None = None,
                        cap_real: float = 100.0, cap_inf: float = 1000.0,
                        penal_desconexion: float = 1000.0,
                        carga_default: float = 1.0,
                        forzar_simetria: bool = True,
                        solo_rsu_conectados: bool = True,
                        timesteps: list | None = None) -> dict:
    """
    Construye, en memoria, TODOS los conjuntos y parámetros que necesita el
    modelo OPL, a partir de las matrices de conectividad del backend.

    Cada instante de tiempo se transforma en un escenario s (numerado 1, 2, …
    en orden temporal). Para cada escenario se corre el análisis multisalto y
    se leen sus matrices de primera aparición S_h para poblar CVR.

    Parámetros:
        matrices_v2v: dict {t: {"vehiculos": [...], "A": [[...]]}} (V2V).
                      Es el campo "matrices" de tuplas_v2v.json.
        tuplas_v2i: lista de tuplas V2I [{"t","vehiculo","rsu","distancia"}].
                    Es el campo "tuplas" de tuplas_visibilidad.json.
        rsu_ids: orden canónico de ids de RSU (columnas de B).
        H: nº máximo de saltos REALES (1..H). El salto de desconexión es H+1.
        max_rsu: nº máximo de RSU reales a desplegar (MaxR). Si es None, se usa
                 el nº de RSU candidatos incluidos (sin límite efectivo).
        cap_real: capacidad Cap[r] de cada RSU real.
        cap_inf: capacidad Cap[r_inf] del RSU artificial (debe ser grande).
        penal_desconexion: penalización P[hmax] del salto de desconexión.
        carga_default: carga de tráfico L[s][v] por defecto para cada vehículo.
        forzar_simetria: simetriza la matriz A (recomendado, ver multisalto).
        solo_rsu_conectados: si True (recomendado), el conjunto R solo incluye
                     los RSU que algún vehículo alcanza en algún escenario. Los
                     RSU que nadie alcanza jamás son inútiles (el modelo nunca
                     los elegiría) y solo inflan el archivo. Si es False, se
                     incluyen TODOS los rsu_ids como candidatos.
        timesteps: lista de instantes (claves de matrices_v2v) a exportar. Si
                   es None, se exportan todos.

    Retorna:
        dict con las claves listas para escribir el .dat:
          "hmax", "rInf", "MaxR",
          "R" (list[int] incluye 0), "S" (list[int]), "V" (list[int]),
          "Vs" ({s: [v ...]}), "Cost" ({r: c}), "Cap" ({r: c}),
          "P" (list[float] longitud hmax), "L" ({s: {v: carga}}),
          "CVR" (list[(s, h, v, r)]),
          "mapas": {
              "escenario_a_t": {s: t}, "int_a_rsu": {r: id}, ...
          },
          "resumen": { contadores para logging }
    """
    hmax = H + 1
    r_inf = 0

    # ---- Elegir qué instantes exportar y numerarlos como escenarios ----
    claves = list(matrices_v2v.keys()) if timesteps is None else list(timesteps)
    # ordenar temporalmente (las claves pueden ser str "120.0" o float)
    claves_ordenadas = sorted(claves, key=lambda k: float(k))

    escenario_a_t = {}   # s (int)  -> t (clave original)
    s_de_clave = {}      # clave    -> s (int)
    for s, clave in enumerate(claves_ordenadas, start=1):
        escenario_a_t[s] = clave
        s_de_clave[clave] = s

    # ---- Correr el multisalto en cada instante seleccionado ----
    subset = {clave: matrices_v2v[clave] for clave in claves_ordenadas}
    # analizar_todos usa la clave t tal cual para filtrar las tuplas V2I; las
    # tuplas traen t como float, así que pasamos las claves ya como float.
    subset_float = {float(k): v for k, v in subset.items()}
    resultados = analizar_todos(subset_float, tuplas_v2i, rsu_ids, H,
                                forzar_simetria)

    rsu_a_int, int_a_rsu = _construir_mapa_rsu(rsu_ids)

    # ---- Recorrer resultados y poblar CVR + conjuntos ----
    CVR = []                     # lista de (s, h, v_int, r_int)
    Vs = {}                      # s -> set de vehículos (int)
    vehiculos_globales = set()   # V
    rsu_int_usados = set()       # RSU reales que aparecen en algún CVR

    for clave in claves_ordenadas:
        s = s_de_clave[clave]
        res = resultados[float(clave)]
        vehiculos = res["vehiculos"]           # orden de filas de S_h
        S_list = res["S"]                      # [S_1, ..., S_H]
        rsu_orden = res["rsu_ids"]             # == rsu_ids

        Vs[s] = set()
        for v_str in vehiculos:
            v_int = _id_vehiculo_a_int(v_str)
            Vs[s].add(v_int)
            vehiculos_globales.add(v_int)

        # --- Tuplas reales desde S_h (primera aparición = mínimo nº saltos) ---
        for h in range(1, H + 1):
            S_h = S_list[h - 1]
            # S_h es n×m: recorrer sus 1s
            for i, v_str in enumerate(vehiculos):
                fila = S_h[i]
                for j, valor in enumerate(fila):
                    if valor:
                        v_int = _id_vehiculo_a_int(v_str)
                        r_int = rsu_a_int[rsu_orden[j]]
                        CVR.append((s, h, v_int, r_int))
                        rsu_int_usados.add(r_int)

        # --- Opción de desconexión (r_inf) para CADA vehículo presente ---
        for v_str in vehiculos:
            v_int = _id_vehiculo_a_int(v_str)
            CVR.append((s, hmax, v_int, r_inf))

    # ---- Conjunto de RSU R (incluye r_inf) ----
    if solo_rsu_conectados:
        rsu_reales = sorted(rsu_int_usados)
    else:
        rsu_reales = sorted(rsu_a_int.values())
    R = [r_inf] + rsu_reales

    # ---- Parámetros por RSU ----
    Cost = {r_inf: 0.0}
    Cap = {r_inf: cap_inf}
    for r in rsu_reales:
        Cost[r] = 1.0        # cada RSU real cuesta 1 -> minimizar CANTIDAD
        Cap[r] = cap_real

    # ---- Penalización por saltos P[1..hmax] ----
    # 1..H: penalización creciente (h); hmax: desconexión (grande)
    P = [float(h) for h in range(1, H + 1)] + [float(penal_desconexion)]

    # ---- Carga L[s][v] (por defecto igual para todos) ----
    V_ordenados = sorted(vehiculos_globales)
    S_ordenados = sorted(escenario_a_t.keys())
    L = {s: {v: float(carga_default) for v in V_ordenados} for s in S_ordenados}

    # ---- MaxR ----
    if max_rsu is None:
        max_rsu = len(rsu_reales)

    return {
        "hmax": hmax,
        "rInf": r_inf,
        "MaxR": int(max_rsu),
        "R": R,
        "S": S_ordenados,
        "V": V_ordenados,
        "Vs": {s: sorted(Vs[s]) for s in S_ordenados},
        "Cost": Cost,
        "Cap": Cap,
        "P": P,
        "L": L,
        "CVR": CVR,
        "mapas": {
            "escenario_a_t": {s: escenario_a_t[s] for s in S_ordenados},
            "int_a_rsu": {r: int_a_rsu[r] for r in rsu_reales},
        },
        "resumen": {
            "H": H,
            "n_escenarios": len(S_ordenados),
            "n_vehiculos": len(V_ordenados),
            "n_rsu_candidatos": len(rsu_reales),
            "n_rsu_totales_backend": len(rsu_ids),
            "n_tuplas_CVR": len(CVR),
            "max_rsu": int(max_rsu),
        },
    }


# ============================================================
# ESCRITURA DEL ARCHIVO .dat EN SINTAXIS OPL
# ============================================================


def _fmt_set(valores) -> str:
    """Formatea un conjunto OPL: [1, 2, 3] -> '{ 1, 2, 3 }'."""
    return "{ " + ", ".join(str(v) for v in valores) + " }"


def _fmt_num(x) -> str:
    """Formatea un número: enteros sin decimales, floats con ellos."""
    xf = float(x)
    return str(int(xf)) if xf.is_integer() else repr(xf)


def _fmt_mapa(mapa: dict) -> str:
    """Formatea un array asociativo OPL: {0:0, 1:1} -> '#[ 0:0, 1:1 ]#'."""
    partes = [f"{k}:{_fmt_num(v)}" for k, v in mapa.items()]
    return "#[ " + ", ".join(partes) + " ]#"


def escribir_dat(datos: dict, dat_path: str) -> str:
    """
    Escribe la estructura devuelta por construir_datos_opl() en un archivo
    `.dat` con la sintaxis exacta que consume `rsu_model.mod`.

    Parámetros:
        datos: dict devuelto por construir_datos_opl().
        dat_path: ruta del archivo .dat de salida.

    Retorna:
        La ruta del archivo escrito.
    """
    res = datos["resumen"]
    mapas = datos["mapas"]

    lineas = []
    A = lineas.append

    # ---- Cabecera con la trazabilidad de dónde salió cada dato ----
    A("/" + "*" * 69)
    A(" * Archivo de datos generado automáticamente por backend/exportar_dat.py")
    A(" * a partir de las matrices de conectividad del backend VANET.")
    A(" *")
    A(f" * Escenarios (snapshots)........: {res['n_escenarios']}")
    A(f" * Vehículos (universo)..........: {res['n_vehiculos']}")
    A(f" * RSU candidatos incluidos......: {res['n_rsu_candidatos']} "
      f"(de {res['n_rsu_totales_backend']} en el backend)")
    A(f" * Saltos máximos H.............: {res['H']}  (hmax = H+1 = {datos['hmax']})")
    A(f" * Tuplas de conectividad CVR....: {res['n_tuplas_CVR']}")
    A(" *")
    A(" * Un escenario = un instante de tiempo de la simulación SUMO.")
    A(" * Cada 1 en la matriz de primera aparición S_h[v][r] del instante")
    A(" * produce una tupla <s, h, v, r>. El salto hmax cae en r_inf (id 0).")
    A(" *")
    A(" * Mapa escenario -> instante t (segundos):")
    for s, t in mapas["escenario_a_t"].items():
        A(f" *   escenario {s:>3}  ->  t = {t}")
    A(" *")
    A(" * Mapa id_RSU_OPL -> id_RSU_backend (para leer la solución):")
    for r, rid in mapas["int_a_rsu"].items():
        A(f" *   R{r:<4} ->  {rid}")
    A(" " + "*" * 68 + "/")
    A("")

    # ---- Escalares ----
    A(f"hmax = {datos['hmax']};")
    A(f"rInf = {datos['rInf']};")
    A(f"MaxR = {datos['MaxR']};")
    A("")

    # ---- Conjuntos ----
    A(f"R = {_fmt_set(datos['R'])};")
    A(f"S = {_fmt_set(datos['S'])};")
    A(f"V = {_fmt_set(datos['V'])};")
    A("")

    # ---- Vs[S]: vehículos por escenario ----
    A("Vs = #[")
    filas_vs = [f"  {s} : {_fmt_set(datos['Vs'][s])}" for s in datos["S"]]
    A(",\n".join(filas_vs))
    A("]#;")
    A("")

    # ---- Cost[R], Cap[R] ----
    A(f"Cost = {_fmt_mapa(datos['Cost'])};")
    A(f"Cap  = {_fmt_mapa(datos['Cap'])};")
    A("")

    # ---- P[1..hmax] ----
    A("P = [ " + ", ".join(_fmt_num(p) for p in datos["P"]) + " ];")
    A("")

    # ---- L[S][V] ----
    A("L = #[")
    filas_l = []
    for s in datos["S"]:
        filas_l.append(f"  {s} : {_fmt_mapa(datos['L'][s])}")
    A(",\n".join(filas_l))
    A("]#;")
    A("")

    # ---- CVR: tuplas <s, h, v, r> ----
    A("CVR = {")
    # agrupar por escenario para legibilidad
    por_s = {}
    for (s, h, v, r) in datos["CVR"]:
        por_s.setdefault(s, []).append((s, h, v, r))
    bloques = []
    for s in sorted(por_s):
        tuplas_txt = ", ".join(f"<{a},{b},{c},{d}>" for (a, b, c, d) in por_s[s])
        bloques.append(f"  // escenario {s}\n  {tuplas_txt}")
    A(",\n".join(bloques))
    A("};")
    A("")

    contenido = "\n".join(lineas)
    os.makedirs(os.path.dirname(os.path.abspath(dat_path)), exist_ok=True)
    with open(dat_path, "w", encoding="utf-8") as f:
        f.write(contenido)

    return dat_path


# ============================================================
# FUNCIONES DE ALTO NIVEL (leen los JSON del backend)
# ============================================================


def exportar_dat_desde_memoria(matrices_v2v: dict, tuplas_v2i: list,
                               rsus, dat_path: str, H: int = 3,
                               **kwargs) -> dict:
    """
    Genera el .dat directamente desde las estructuras en memoria que produce
    el backend (útil para llamarlo desde app.py en un paso futuro, sin pasar
    por disco).

    Parámetros:
        matrices_v2v: campo "matrices" de tuplas_v2v.json.
        tuplas_v2i: campo "tuplas" de tuplas_visibilidad.json.
        rsus: dict de RSU {id: {...}} o lista de ids. Se ordena para fijar
              el orden canónico de columnas.
        dat_path: ruta de salida del .dat.
        H: nº máximo de saltos reales.
        **kwargs: se pasan a construir_datos_opl() (max_rsu, cap_real, ...).

    Retorna:
        El dict de datos OPL (incluye "resumen" y "mapas").
    """
    rsu_ids = sorted(rsus.keys()) if isinstance(rsus, dict) else sorted(rsus)
    datos = construir_datos_opl(matrices_v2v, tuplas_v2i, rsu_ids, H=H, **kwargs)
    escribir_dat(datos, dat_path)
    return datos


def exportar_dat_desde_json(output_dir: str, dat_path: str, H: int = 3,
                            **kwargs) -> dict:
    """
    Punto de entrada principal: lee los dos JSON que deja el backend en
    `output_dir`, calcula el multisalto y escribe el `.dat`.

    Archivos de entrada esperados en output_dir:
        - tuplas_v2v.json          (Matriz A, campo "matrices")
        - tuplas_visibilidad.json  (Matriz B, campos "tuplas" y "rsus")

    Parámetros:
        output_dir: carpeta con los JSON del backend (normalmente "output").
        dat_path: ruta de salida del archivo .dat.
        H: nº máximo de saltos reales.
        **kwargs: se pasan a construir_datos_opl() (max_rsu, cap_real, ...).

    Retorna:
        El dict de datos OPL (incluye "resumen" y "mapas").
    """
    ruta_v2v = os.path.join(output_dir, "tuplas_v2v.json")
    ruta_v2i = os.path.join(output_dir, "tuplas_visibilidad.json")

    with open(ruta_v2v, encoding="utf-8") as f:
        data_v2v = json.load(f)
    with open(ruta_v2i, encoding="utf-8") as f:
        data_v2i = json.load(f)

    matrices_v2v = data_v2v["matrices"]
    tuplas_v2i = data_v2i["tuplas"]
    rsus = data_v2i["rsus"]

    return exportar_dat_desde_memoria(matrices_v2v, tuplas_v2i, rsus,
                                      dat_path, H=H, **kwargs)


# ============================================================
# CLI
# ============================================================


def main():
    """CLI mínima para generar el .dat desde output/ sin tocar la interfaz."""
    import argparse

    aqui = os.path.dirname(os.path.abspath(__file__))
    raiz = os.path.dirname(aqui)

    parser = argparse.ArgumentParser(
        description="Genera un .dat de OPL desde los JSON del backend VANET.")
    parser.add_argument("--output-dir", default=os.path.join(raiz, "output"),
                        help="Carpeta con tuplas_v2v.json y tuplas_visibilidad.json")
    parser.add_argument("--dat", default=os.path.join(raiz, "optimizacion", "rsu_backend.dat"),
                        help="Ruta del .dat de salida")
    parser.add_argument("--H", type=int, default=3, help="Nº máximo de saltos reales")
    parser.add_argument("--max-rsu", type=int, default=None,
                        help="MaxR: nº máximo de RSU reales a desplegar")
    parser.add_argument("--todos-los-rsu", action="store_true",
                        help="Incluir TODOS los RSU candidatos (no solo los conectados)")
    args = parser.parse_args()

    datos = exportar_dat_desde_json(
        args.output_dir, args.dat, H=args.H, max_rsu=args.max_rsu,
        solo_rsu_conectados=not args.todos_los_rsu,
    )

    r = datos["resumen"]
    print("=" * 60)
    print("  .dat GENERADO CORRECTAMENTE")
    print("=" * 60)
    print(f"  Archivo........: {args.dat}")
    print(f"  Escenarios.....: {r['n_escenarios']}")
    print(f"  Vehículos......: {r['n_vehiculos']}")
    print(f"  RSU candidatos.: {r['n_rsu_candidatos']} (de {r['n_rsu_totales_backend']})")
    print(f"  Saltos H.......: {r['H']}  (hmax = {datos['hmax']})")
    print(f"  Tuplas CVR.....: {r['n_tuplas_CVR']}")
    print(f"  MaxR...........: {r['max_rsu']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
