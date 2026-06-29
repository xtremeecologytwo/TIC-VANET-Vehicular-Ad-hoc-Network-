"""
ejemplo_multisalto.py
=====================
EJEMPLO MÍNIMO y AUTOCONTENIDO para entender el multisalto, pensado para
explicárselo a otra persona (p. ej. tu tutor) sin el ruido de los datos
reales de la simulación.

Escenario inventado, muy pequeño:

        R1  (antena / RSU)
        │
        │  (V1 está cerca de la antena y la ve)
      ┌─V1─┐         ┌─────┐
      │    │ ve      │ EDIF│   (un edificio tapa a V2 y V3 de la antena)
      │    ▼         └─────┘
     [V1]───[V2]───[V3]            [V4]  (lejos y solo: no ve a nadie)
      │  ve   │  ve   │
      └───────┴───────┘
   V1 ve R1      V2 NO ve R1      V3 NO ve R1
   V1 ve V2      V2 ve V1 y V3    V3 solo ve V2

Idea: V2 y V3 NO ven la antena directamente, pero pueden llegar a ella
"rebotando" a través de V1:
        V2 → V1 → R1            (2 saltos)
        V3 → V2 → V1 → R1       (3 saltos)
V4 está completamente solo, así que queda aislado pase lo que pase.

Este script usa las MISMAS funciones del proyecto (backend/multisalto.py),
así que no es un cálculo "de mentira": es exactamente lo que hace la app.

Uso:
    python ejemplo_multisalto.py
"""

import sys

import numpy as np

# La consola de Windows no soporta los caracteres de caja ni emojis con su
# codificación por defecto (cp1252). Forzamos UTF-8 para que se vea bien.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from backend.multisalto import (
    agregar_identidad, calcular_R, calcular_S, calcular_D, calcular_vector_d,
)


# ============================================================
# Pequeñas utilidades para imprimir bonito
# ============================================================

def titulo(txt):
    print("\n" + "═" * 64)
    print("  " + txt)
    print("═" * 64)


def mostrar(M, filas, columnas, nombre):
    """Imprime una matriz con etiquetas de fila y columna."""
    M = np.asarray(M, dtype=int)
    print(f"\n{nombre}   ({M.shape[0]}×{M.shape[1]}, {int(M.sum())} unos)")
    # cabecera
    print("       " + "".join(f"{c:>4}" for c in columnas))
    for i, f in enumerate(filas):
        fila = "".join(f"{M[i, j]:>4}" for j in range(len(columnas)))
        print(f"  {f:<4} |{fila}")


# ============================================================
# 1) Definimos el escenario a mano
# ============================================================

def main():
    vehiculos = ["V1", "V2", "V3", "V4"]
    rsus = ["R1"]

    titulo("EL ESCENARIO (inventado, para entender)")
    print("""
    R1  ← la antena (RSU)
    │
   [V1]───[V2]───[V3]          [V4]   (solo, no ve a nadie)
    │       │       │
  ve R1   ve V1   ve V2
          ve V3

  · V1 ve la antena R1 y ve a V2.
  · V2 ve a V1 y a V3, pero NO ve la antena (hay un edificio).
  · V3 solo ve a V2.
  · V4 está lejos y solo: no ve ni coches ni antena.
""")

    # ----- Tuplas (así salen de la simulación) -----
    titulo("PASO 0 — Las TUPLAS (lo que entrega la simulación)")
    print("""
  Tuplas V2V  <t, Vi, Vj>  (un coche ve a otro):
       (t, V1, V2)        (t, V2, V3)

  Tuplas V2I  <t, V, RSU>  (un coche ve la antena):
       (t, V1, R1)

  Una tupla es solo "fulano ve a mengano". Para CALCULAR, las ponemos
  en tablas de 0s y 1s: las matrices A y B.
""")

    # ----- Matriz A (V2V): quién ve a quién -----
    # Filas y columnas = V1, V2, V3, V4
    A = np.array([
        # V1 V2 V3 V4
        [0, 1, 0, 0],   # V1 ve a V2
        [1, 0, 1, 0],   # V2 ve a V1 y V3
        [0, 1, 0, 0],   # V3 ve a V2
        [0, 0, 0, 0],   # V4 no ve a nadie
    ])

    # ----- Matriz B (V2I): quién ve la antena -----
    B = np.array([
        [1],   # V1 ve R1
        [0],   # V2 no
        [0],   # V3 no
        [0],   # V4 no
    ])

    titulo("PASO 1 — Matriz A (coche ↔ coche)  y  Matriz B (coche ↔ antena)")
    print("\n  A[i][j] = 1  si el coche i ve al coche j.  (simétrica, diagonal 0)")
    mostrar(A, vehiculos, vehiculos, "A =")
    print("\n  B[i][k] = 1  si el coche i ve la antena k.  (1 salto, directo)")
    mostrar(B, vehiculos, rsus, "B =")

    # ============================================================
    # 2) Multisalto, paso a paso
    # ============================================================

    titulo("PASO 2 — Ã = A ∨ I  (poner 1 en la diagonal)")
    A_tilde = agregar_identidad(A)
    print("""
  Ponemos 1 en la diagonal: cada coche "se incluye a sí mismo".
  Esto sirve para que, al subir de saltos, NO se pierdan las conexiones
  que ya teníamos (lo que da la propiedad de acumulación).
""")
    mostrar(A_tilde, vehiculos, vehiculos, "Ã =")

    H = 3
    R = calcular_R(A_tilde, B, H)

    titulo("PASO 3 — R_h: ¿quién llega a la antena usando HASTA h saltos?")
    print("""
  R_1 = B                         (directo, 1 salto)
  R_h = binarizar(Ã · R_{h-1})    (rebotando, h saltos)
  'binarizar' = cualquier número > 0 se vuelve 1 (solo importa SI existe
  un camino, no cuántos).
""")

    explicaciones = {
        1: "Solo V1 ve la antena directamente.",
        2: "V2 NO veía la antena, pero V2→V1→R1 son 2 saltos. ¡Ahora V2 llega!",
        3: "V3 tampoco veía la antena, pero V3→V2→V1→R1 son 3 saltos. ¡V3 llega!",
    }
    for h in range(1, H + 1):
        mostrar(R[h - 1], vehiculos, rsus, f"R_{h} =")
        print(f"  → {explicaciones[h]}")

    # Mostrar el cálculo de una celda "a mano"
    titulo("¿De dónde sale el 1 nuevo de R_2?  (cálculo a mano)")
    print("""
  R_2 = binarizar(Ã · R_1).  Veamos la fila de V2:

      Ã[V2] = [1, 1, 1, 0]      (V2 se incluye a sí mismo, a V1 y a V3)
      R_1   = [1, 0, 0, 0]^T    (solo V1 llega a la antena)

      V2 → R1 = (1·1) + (1·0) + (1·0) + (0·0) = 1

  El primer término (1·1) significa: "V2 ve a V1"  ×  "V1 ve la antena".
  Es decir, V2 alcanza la antena PASANDO por V1. Ese es el 2º salto.
""")

    # ----- S_h: primera aparición -----
    S = calcular_S(R)
    titulo("PASO 4 — S_h: ¿con cuántos saltos aparece CADA conexión por 1ª vez?")
    print("""
  S_h = R_h − R_{h-1}.  Marca las conexiones cuyo número MÍNIMO de saltos
  es EXACTAMENTE h. Cada conexión aparece en una sola S_h (la más corta).
""")
    nombres_s = {1: "se conectan a 1 salto (directo)",
                 2: "se conectan justo a 2 saltos",
                 3: "se conectan justo a 3 saltos"}
    for h in range(1, H + 1):
        mostrar(S[h - 1], vehiculos, rsus, f"S_{h} =")
        print(f"  → quién {nombres_s[h]}")

    # ----- D_H y d -----
    D = calcular_D(R[-1])
    d = calcular_vector_d(R[-1])

    titulo("PASO 5 — Desconexión: D_H y vector d")
    print(f"""
  D_{H} = J − R_{H}.   D[i][k] = 1 significa: el coche i NO logró conectarse
  con la antena k ni con {H} saltos.
""")
    mostrar(D, vehiculos, rsus, f"D_{H} =")

    print(f"""
  Vector d:  d[i] = 1 si el coche i no alcanza NINGUNA antena (aislado total).
""")
    for i, v in enumerate(vehiculos):
        estado = "🚫 AISLADO" if d[i] == 1 else "✅ conectado"
        print(f"     {v}:  d = {d[i]}   {estado}")

    titulo("CONCLUSIÓN")
    print(f"""
  · V1 llega a la antena en 1 salto (la ve directo).
  · V2 llega en 2 saltos:  V2 → V1 → R1.
  · V3 llega en 3 saltos:  V3 → V2 → V1 → R1.
  · V4 queda AISLADO: no tiene ningún vecino, así que ni el multisalto
    lo puede ayudar (su fila en R_{H} es todo ceros → d = 1).

  Moraleja: el multisalto permite que coches SIN línea directa a la antena
  sigan conectados usando a otros coches como "repetidores".
""")


if __name__ == "__main__":
    main()
