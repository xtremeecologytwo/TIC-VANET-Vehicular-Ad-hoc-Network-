"""
explicar_multisalto.py
======================
Script DIDÁCTICO que imprime por consola, paso a paso, cómo se pasa de las
tuplas a las matrices A (V2V) y B (V2I), y de ahí a la conectividad
multisalto (R_h, S_h, D_H, vector d).

Usa un instante real de la simulación (output/tuplas_v2v.json y
output/tuplas_visibilidad.json).

Uso:
    python explicar_multisalto.py            # elige un instante "didáctico" solo
    python explicar_multisalto.py 120        # usa el instante t=120 s
    python explicar_multisalto.py 120 3      # instante t=120 s con H=3 saltos
"""

import os
import sys
import json

import numpy as np

# La consola de Windows usa cp1252 y no soporta los caracteres de caja (─ ═)
# ni los emojis. Forzamos UTF-8 en la salida para que se vea bien.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from backend.multisalto import (
    construir_matriz_A, construir_matriz_B, agregar_identidad,
    calcular_R, calcular_S, calcular_D, calcular_vector_d, analizar_timestep,
)

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


# ============================================================
# Utilidades de impresión
# ============================================================

def linea(c="─", n=70):
    print(c * n)


def titulo(txt):
    print()
    linea("═")
    print(f"  {txt}")
    linea("═")


def imprimir_matriz(M, filas, columnas, nombre, nota=""):
    """Imprime una matriz con etiquetas de fila y columna, alineada."""
    M = np.asarray(M, dtype=int)
    print(f"\n{nombre}   (tamaño {M.shape[0]}×{M.shape[1]}, {int(M.sum())} unos){'  — ' + nota if nota else ''}")

    if M.size == 0:
        print("   (matriz vacía)")
        return

    ancho_fila = max((len(str(f)) for f in filas), default=3)
    ancho_col = max((len(str(c)) for c in columnas), default=1)
    ancho_col = max(ancho_col, 1)

    # Cabecera de columnas
    cabecera = " " * (ancho_fila + 3)
    for c in columnas:
        cabecera += str(c).rjust(ancho_col) + " "
    print(cabecera)

    # Filas
    for i, f in enumerate(filas):
        fila_txt = str(f).ljust(ancho_fila) + " | "
        for j in range(len(columnas)):
            fila_txt += str(M[i, j]).rjust(ancho_col) + " "
        print(fila_txt)


def columnas_interesantes(B, R_H, max_cols=14):
    """Devuelve los índices de RSU que tienen al menos un 1 (en B o en R_H),
    para no imprimir matrices de 79 columnas vacías."""
    B = np.asarray(B, dtype=int)
    R_H = np.asarray(R_H, dtype=int)
    relevantes = (B.sum(axis=0) + R_H.sum(axis=0)) > 0
    idx = [j for j in range(len(relevantes)) if relevantes[j]]
    return idx[:max_cols], len(idx)


# ============================================================
# Carga de datos
# ============================================================

def cargar_datos():
    ruta_v2v = os.path.join(OUTPUT_DIR, "tuplas_v2v.json")
    ruta_v2i = os.path.join(OUTPUT_DIR, "tuplas_visibilidad.json")

    if not os.path.isfile(ruta_v2v) or not os.path.isfile(ruta_v2i):
        print("❌ No encuentro los JSON en output/. Ejecuta primero la simulación V2I + V2V en la app.")
        sys.exit(1)

    v2v = json.load(open(ruta_v2v, encoding="utf-8"))
    v2i = json.load(open(ruta_v2i, encoding="utf-8"))

    # Las claves de tiempo en el JSON son strings → pasarlas a float
    matrices = {float(k): val for k, val in v2v["matrices"].items()}
    tuplas_v2i = v2i["tuplas"]
    rsu_ids = sorted(v2i["rsus"].keys())
    return matrices, tuplas_v2i, rsu_ids


def elegir_instante_didactico(matrices, tuplas_v2i, rsu_ids, H=3):
    """Busca un instante con pocos vehículos (2–8) donde el multisalto
    SÍ aporte conexiones nuevas (para que el ejemplo sea ilustrativo)."""
    mejor = None
    for t, mat in matrices.items():
        n = len(mat["vehiculos"])
        if not (2 <= n <= 8):
            continue
        res = analizar_timestep(mat, tuplas_v2i, t, rsu_ids, H=H)
        nuevos_multisalto = sum(p["pares_nuevos"] for p in res["resumen"]["por_salto"] if p["h"] >= 2)
        if nuevos_multisalto > 0:
            score = (nuevos_multisalto, -n)  # más conexiones nuevas, menos coches
            if mejor is None or score > mejor[0]:
                mejor = (score, t)
    if mejor:
        return mejor[1]
    # Si ninguno aporta multisalto, usar el de más vehículos
    return max(matrices.keys(), key=lambda t: len(matrices[t]["vehiculos"]))


# ============================================================
# Programa principal
# ============================================================

def main():
    matrices, tuplas_v2i, rsu_ids = cargar_datos()

    # Argumentos opcionales: [timestep] [H]
    H = 3
    if len(sys.argv) >= 3:
        H = int(sys.argv[2])

    if len(sys.argv) >= 2:
        t = float(sys.argv[1])
        if t not in matrices:
            # buscar el más cercano
            t = min(matrices.keys(), key=lambda x: abs(x - t))
            print(f"(El instante pedido no existe; uso el más cercano: t={t}s)")
    else:
        t = elegir_instante_didactico(matrices, tuplas_v2i, rsu_ids, H)
        print(f"(No diste instante; elegí uno didáctico automáticamente: t={t}s)")

    mat_t = matrices[t]
    vehiculos = mat_t["vehiculos"]

    titulo(f"INSTANTE t = {t} s   —   {len(vehiculos)} vehículos, {len(rsu_ids)} RSU, H = {H} saltos")
    print("\nCada instante se procesa por separado: las posiciones de los coches")
    print("se consideran FIJAS en este momento del tiempo.")
    print(f"\nVehículos activos (este es el ORDEN de filas en todas las matrices):")
    print("   " + ", ".join(vehiculos))

    # ----------------------------------------------------------
    # PASO 0: las tuplas crudas de este instante
    # ----------------------------------------------------------
    titulo("PASO 0 — De las TUPLAS a las matrices")

    tuplas_v2v_t = []  # las tuplas V2V de este instante (reconstruidas desde A)
    A_cruda = np.asarray(mat_t["A"], dtype=int)
    for i in range(len(vehiculos)):
        for j in range(len(vehiculos)):
            if A_cruda[i, j] == 1:
                tuplas_v2v_t.append((vehiculos[i], vehiculos[j]))

    print("\n▶ Tuplas V2V <t, Vi, Vj> en este instante (coche ve coche):")
    if tuplas_v2v_t:
        for vi, vj in tuplas_v2v_t:
            print(f"     ({t}, {vi}, {vj})")
    else:
        print("     (ninguna)")

    tuplas_v2i_t = [tp for tp in tuplas_v2i if tp["t"] == t]
    print("\n▶ Tuplas V2I <t, V, RSU> en este instante (coche ve antena):")
    if tuplas_v2i_t:
        for tp in tuplas_v2i_t[:20]:
            print(f"     ({t}, {tp['vehiculo']}, RSU {tp['rsu']})   dist={tp['distancia']} m")
        if len(tuplas_v2i_t) > 20:
            print(f"     ... y {len(tuplas_v2i_t) - 20} tuplas más")
    else:
        print("     (ninguna)")

    print("\n→ Una TUPLA es solo 'fulano se conecta con mengano'. La MATRIZ pone")
    print("  esas conexiones en una tabla de 0s y 1s para poder operar con ellas.")

    # ----------------------------------------------------------
    # PASO 1: Matriz A (V2V)
    # ----------------------------------------------------------
    titulo("PASO 1 — Matriz A (V2V): coche ↔ coche")

    vehiculos, A = construir_matriz_A(mat_t, forzar_simetria=True)
    print("\nRegla:  A[i][j] = 1  si el coche i ve directamente al coche j.")
    print("        Diagonal = 0 (un coche no se conecta consigo mismo).")
    print("        Es simétrica: si i ve a j, j ve a i.")
    imprimir_matriz(A, vehiculos, vehiculos, "A =")

    # ----------------------------------------------------------
    # PASO 2: Matriz B (V2I)  — alias cortos para las RSU
    # ----------------------------------------------------------
    titulo("PASO 2 — Matriz B (V2I): coche ↔ antena")

    B = construir_matriz_B(tuplas_v2i, t, vehiculos, rsu_ids)

    # Para no imprimir 79 columnas, mostramos solo las RSU "con algo"
    R_provisional = calcular_R(agregar_identidad(A), B, H)
    idx_cols, total_rel = columnas_interesantes(B, R_provisional[-1])
    alias = [f"r{k}" for k in range(len(idx_cols))]

    print("\nRegla:  B[i][k] = 1  si el coche i ve directamente a la antena k.")
    print(f"\nHay {len(rsu_ids)} RSU en total; muestro solo las {len(idx_cols)} relevantes")
    print("(las que alguien alcanza). Uso alias cortos:")
    for a, k in zip(alias, idx_cols):
        print(f"     {a}  =  RSU {rsu_ids[k]}")

    B_vis = B[:, idx_cols]
    imprimir_matriz(B_vis, vehiculos, alias, "B =", "solo columnas relevantes")

    # ----------------------------------------------------------
    # PASO 3: Ã = A ∨ I
    # ----------------------------------------------------------
    titulo("PASO 3 — Ã = A ∨ I  (añadir la identidad)")

    A_tilde = agregar_identidad(A)
    print("\nSe pone un 1 en la DIAGONAL de A. Esto hace que un coche 'se incluya")
    print("a sí mismo' al multiplicar, para NO perder las conexiones cortas")
    print("cuando subimos el número de saltos (propiedad de monotonía).")
    imprimir_matriz(A_tilde, vehiculos, vehiculos, "Ã =")

    # ----------------------------------------------------------
    # PASO 4: R_1, R_2, ..., R_H
    # ----------------------------------------------------------
    titulo("PASO 4 — Matrices acumuladas R_h = β(Ã · R_{h-1})")

    R = calcular_R(A_tilde, B, H)
    print("\nR_1 = B  (1 salto, directo).")
    print("R_h = binarizar(Ã · R_{h-1})  → ¿llega usando HASTA h saltos?")
    print("'binarizar' = cualquier número > 0 se vuelve 1 (solo importa si EXISTE camino).")

    for h in range(1, H + 1):
        R_h = R[h - 1]
        veh_conectados = int((R_h.sum(axis=1) > 0).sum())
        imprimir_matriz(
            R_h[:, idx_cols], vehiculos, alias,
            f"R_{h} =",
            f"hasta {h} salto(s) — {veh_conectados}/{len(vehiculos)} coches con ≥1 antena"
        )

    # Mostrar UN cálculo de celda a mano (didáctico) para R_2
    if H >= 2 and len(vehiculos) > 0 and len(idx_cols) > 0:
        print("\n  ── ¿De dónde sale un 1 en R_2? Ejemplo de una celda ──")
        # buscar una celda (i,k) que sea 0 en R_1 y 1 en R_2 (apareció por multisalto)
        nuevos = (R[1] - R[0])
        encontrado = False
        for i in range(len(vehiculos)):
            for k in idx_cols:
                if nuevos[i, k] == 1:
                    # explicar via qué coche intermedio
                    intermedios = [vehiculos[j] for j in range(len(vehiculos))
                                   if A_tilde[i, j] == 1 and R[0][j, k] == 1]
                    print(f"  R_2[{vehiculos[i]}][r{idx_cols.index(k)}] pasó de 0 a 1.")
                    print(f"  Motivo: {vehiculos[i]} no veía esa antena directo, pero llega")
                    print(f"          rebotando a través de: {', '.join(intermedios)}")
                    print(f"          (ese coche intermedio SÍ ve la antena en R_1).")
                    encontrado = True
                    break
            if encontrado:
                break
        if not encontrado:
            print("  (En este instante R_2 no agregó conexiones nuevas respecto a R_1.)")

    # ----------------------------------------------------------
    # PASO 5: S_h (primera aparición)
    # ----------------------------------------------------------
    titulo("PASO 5 — Matrices de primera aparición S_h = R_h − R_{h-1}")

    S = calcular_S(R)
    print("\nS_h marca las conexiones cuyo MÍNIMO número de saltos es EXACTAMENTE h.")
    print("(una conexión aparece en una sola S_h: la del camino más corto).")
    for h in range(1, H + 1):
        imprimir_matriz(
            S[h - 1][:, idx_cols], vehiculos, alias,
            f"S_{h} =", f"conexiones nuevas justo a {h} salto(s)"
        )

    # ----------------------------------------------------------
    # PASO 6: D_H y vector d
    # ----------------------------------------------------------
    titulo("PASO 6 — Desconexión: D_H = J − R_H  y  vector d")

    D = calcular_D(R[-1])
    d = calcular_vector_d(R[-1])
    print(f"\nD_{H}[i][k] = 1  significa: el coche i NO logró conectarse con la antena k")
    print(f"             ni siquiera usando {H} saltos.")
    imprimir_matriz(D[:, idx_cols], vehiculos, alias, f"D_{H} =", "1 = NO conecta")

    print(f"\nVector d:  d[i] = 1  si el coche i no alcanza NINGUNA antena (aislado total).")
    print()
    for i, v in enumerate(vehiculos):
        estado = "🚫 AISLADO" if d[i] == 1 else "✅ conectado"
        print(f"     {v:<5} d = {d[i]}   {estado}")

    aislados = [vehiculos[i] for i in range(len(vehiculos)) if d[i] == 1]
    titulo("CONCLUSIÓN")
    if aislados:
        print(f"\n  En t={t}s, con hasta {H} saltos, quedan AISLADOS: {', '.join(aislados)}")
    else:
        print(f"\n  En t={t}s, con hasta {H} saltos, TODOS los coches alcanzan alguna antena.")
    print()


if __name__ == "__main__":
    main()
