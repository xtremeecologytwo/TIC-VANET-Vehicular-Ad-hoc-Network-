"""
mini_proyecto_vanet.py
======================
MINI-PROYECTO COMPLETO (de juguete) para entender TODO el flujo VANET de
este trabajo, de principio a fin y narrado paso a paso:

    1) Posiciones de coches + antenas + un edificio  (los "datos")
    2) Línea de vista (LoS)  →  ¿quién ve a quién sin que un edificio tape?
    3) Tuplas  →  Matriz B (V2I, coche↔antena) y Matriz A (V2V, coche↔coche)
    4) Multisalto  →  Ã, R_h, S_h, D_H, vector d

Es un escenario INVENTADO y pequeño (4 coches, 1 antena, 1 edificio), pero
usa EXACTAMENTE las mismas funciones que la aplicación real:
    · backend.visibilidad.tiene_linea_de_vista()   (la geometría de LoS)
    · backend.multisalto.*                          (el cálculo multisalto)

Uso:
    python mini_proyecto_vanet.py
"""

import sys
import math

import numpy as np

# UTF-8 en la consola de Windows (para los caracteres de caja y emojis).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# --- Funciones REALES del proyecto ---
from backend.visibilidad import tiene_linea_de_vista
from backend.multisalto import (
    agregar_identidad, calcular_R, calcular_S, calcular_D, calcular_vector_d,
)


# ============================================================
# Utilidades de impresión
# ============================================================

def titulo(txt):
    print("\n" + "═" * 66)
    print("  " + txt)
    print("═" * 66)


def mostrar(M, filas, columnas, nombre):
    M = np.asarray(M, dtype=int)
    print(f"\n{nombre}   ({M.shape[0]}×{M.shape[1]}, {int(M.sum())} unos)")
    print("       " + "".join(f"{c:>4}" for c in columnas))
    for i, f in enumerate(filas):
        fila = "".join(f"{M[i, j]:>4}" for j in range(len(columnas)))
        print(f"  {f:<4} |{fila}")


def distancia(ax, ay, bx, by):
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


# ============================================================
# 1) LOS DATOS DEL ESCENARIO (posiciones en metros)
# ============================================================

# Coches: id -> (x, y)
COCHES = {
    "V1": (0.0, 20.0),
    "V2": (65.0, 20.0),
    "V3": (130.0, 20.0),
    "V4": (500.0, 20.0),   # lejos y solo
}

# Antenas (RSU): id -> (x, y)
ANTENAS = {
    "R1": (0.0, 100.0),
}

# Edificios: id -> lista de esquinas [[x, y], ...]  (un rectángulo)
# Está colocado para TAPAR la vista de V2 hacia R1, pero no la de V1.
EDIFICIOS = {
    "EDIF": [[20.0, 45.0], [45.0, 45.0], [45.0, 70.0], [20.0, 70.0]],
}

RADIO_OBU = 120.0  # alcance de radio en metros


def dibujar_escenario():
    titulo("PASO 0 — LOS DATOS: posiciones de coches, antena y edificio")
    print(f"""
  (vista de arriba, coordenadas en metros; radio de radio_obu = {RADIO_OBU:.0f} m)

   y=100  R1●  (antena)
          │
    y=70  │      ┌────────┐
          │      │  EDIF  │   ← el edificio tapa la vista de V2 hacia R1
    y=45  │      └────────┘
          │
    y=20  V1●────────V2●────────V3●·············V4●  (V4 lejísimos, solo)
          x=0       x=65       x=130            x=500

  Coches:  V1(0,20)  V2(65,20)  V3(130,20)  V4(500,20)
  Antena:  R1(0,100)
  Edificio EDIF: rectángulo (20,45)-(45,70)
""")


# ============================================================
# 2) + 3)  CONSTRUIR LA MATRIZ B (V2I) DESDE LA GEOMETRÍA
# ============================================================

def construir_B_desde_geometria(coches, antenas, edificios, radio):
    """Recorre cada par (coche, antena), aplica distancia + LoS, narra la
    decisión, arma las tuplas y rellena la matriz B."""
    titulo("PASO 1 — V2I: ¿qué coche ve qué antena?  →  Matriz B")
    print("""
  Regla para conectar coche↔antena (las dos condiciones a la vez):
    (a) distancia ≤ radio_obu     (b) sin edificio tapando la línea (LoS)
""")
    ids_coches = list(coches.keys())
    ids_antenas = list(antenas.keys())
    lista_edif = list(edificios.values())

    B = np.zeros((len(ids_coches), len(ids_antenas)), dtype=int)
    tuplas = []

    for i, vc in enumerate(ids_coches):
        vx, vy = coches[vc]
        for k, ra in enumerate(ids_antenas):
            rx, ry = antenas[ra]
            d = distancia(vx, vy, rx, ry)

            if d > radio:
                print(f"  {vc} ↔ {ra}: dist {d:6.1f} m  (> {radio:.0f}) ✗ fuera de alcance  → sin conexión")
                continue

            hay_los = tiene_linea_de_vista(vx, vy, rx, ry, lista_edif)
            if hay_los:
                B[i, k] = 1
                tuplas.append((vc, ra))
                print(f"  {vc} ↔ {ra}: dist {d:6.1f} m  (≤ {radio:.0f}) ✓  y SIN edificio ✓  → ¡CONEXIÓN!  tupla ({vc},{ra})")
            else:
                print(f"  {vc} ↔ {ra}: dist {d:6.1f} m  (≤ {radio:.0f}) ✓  pero un EDIFICIO tapa ✗  → NLoS, sin conexión")

    print("\n  Tuplas V2I generadas:", tuplas if tuplas else "(ninguna)")
    mostrar(B, ids_coches, ids_antenas, "B =")
    return B, ids_coches, ids_antenas


# ============================================================
# 2) + 3)  CONSTRUIR LA MATRIZ A (V2V) DESDE LA GEOMETRÍA
# ============================================================

def construir_A_desde_geometria(coches, edificios, radio):
    """Igual que B, pero entre pares de coches. La matriz A es simétrica."""
    titulo("PASO 2 — V2V: ¿qué coche ve qué coche?  →  Matriz A")
    print("""
  Misma regla (distancia ≤ radio_obu  y  LoS), pero coche↔coche.
  Solo evaluamos pares i<j (si i ve a j, j ve a i → matriz simétrica).
""")
    ids = list(coches.keys())
    lista_edif = list(edificios.values())
    n = len(ids)
    A = np.zeros((n, n), dtype=int)

    for i in range(n):
        for j in range(i + 1, n):
            xi, yi = coches[ids[i]]
            xj, yj = coches[ids[j]]
            d = distancia(xi, yi, xj, yj)

            if d > radio:
                print(f"  {ids[i]} ↔ {ids[j]}: dist {d:6.1f} m  (> {radio:.0f}) ✗ fuera de alcance")
                continue

            hay_los = tiene_linea_de_vista(xi, yi, xj, yj, lista_edif)
            if hay_los:
                A[i, j] = 1
                A[j, i] = 1   # simetría
                print(f"  {ids[i]} ↔ {ids[j]}: dist {d:6.1f} m  (≤ {radio:.0f}) ✓  y SIN edificio ✓  → ¡CONEXIÓN!")
            else:
                print(f"  {ids[i]} ↔ {ids[j]}: dist {d:6.1f} m  (≤ {radio:.0f}) ✓  pero un EDIFICIO tapa ✗  → NLoS")

    mostrar(A, ids, ids, "A =")
    return A, ids


# ============================================================
# 4)  MULTISALTO
# ============================================================

def correr_multisalto(A, B, coches_ids, antenas_ids, H=3):
    titulo("PASO 3 — MULTISALTO: combinar A y B para llegar 'rebotando'")
    print("""
  Hasta aquí, B solo dice quién ve la antena DIRECTAMENTE (1 salto).
  El multisalto usa A para permitir que un coche llegue a la antena a
  través de otros coches (repetidores).
""")

    A_tilde = agregar_identidad(A)
    print("  Ã = A ∨ I  (1s en la diagonal, para acumular conexiones):")
    mostrar(A_tilde, coches_ids, coches_ids, "Ã =")

    R = calcular_R(A_tilde, B, H)
    print("\n  R_1 = B ;  R_h = binarizar(Ã · R_{h-1})  → ¿llega usando hasta h saltos?")
    notas = {1: "directo", 2: "rebotando en 1 coche", 3: "rebotando en 2 coches"}
    for h in range(1, H + 1):
        mostrar(R[h - 1], coches_ids, antenas_ids, f"R_{h} =")
        conectados = [coches_ids[i] for i in range(len(coches_ids)) if R[h - 1][i].sum() > 0]
        print(f"  → con ≤{h} salto(s) ({notas[h]}) llegan a una antena: {conectados}")

    S = calcular_S(R)
    print("\n  S_h = R_h − R_{h-1}  → quién aparece JUSTO con h saltos:")
    for h in range(1, H + 1):
        nuevos = [coches_ids[i] for i in range(len(coches_ids)) if S[h - 1][i].sum() > 0]
        print(f"     S_{h}: se conectan por primera vez a {h} salto(s): {nuevos if nuevos else '(nadie)'}")

    D = calcular_D(R[-1])
    d = calcular_vector_d(R[-1])
    print()
    mostrar(D, coches_ids, antenas_ids, f"D_{H} = J − R_{H}  (1 = NO conecta)")

    titulo("RESULTADO FINAL — ¿quién queda conectado y quién aislado?")
    for i, v in enumerate(coches_ids):
        if d[i] == 1:
            print(f"  {v}:  🚫 AISLADO (no alcanza ninguna antena ni con {H} saltos)")
        else:
            # ¿con cuántos saltos mínimo se conectó?
            min_h = next(h for h in range(1, H + 1) if R[h - 1][i].sum() > 0)
            print(f"  {v}:  ✅ conectado — mínimo {min_h} salto(s)")


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():
    print("\n" + "#" * 66)
    print("#  MINI-PROYECTO VANET  —  del mapa al multisalto, paso a paso")
    print("#" * 66)

    dibujar_escenario()
    B, coches_ids, antenas_ids = construir_B_desde_geometria(COCHES, ANTENAS, EDIFICIOS, RADIO_OBU)
    A, _ = construir_A_desde_geometria(COCHES, EDIFICIOS, RADIO_OBU)
    correr_multisalto(A, B, coches_ids, antenas_ids, H=3)

    print("\n" + "#" * 66)
    print("#  FIN. Cambia las posiciones en COCHES/ANTENAS/EDIFICIOS arriba")
    print("#  y vuelve a correr para ver cómo cambia todo.")
    print("#" * 66 + "\n")


if __name__ == "__main__":
    main()
