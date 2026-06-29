"""
Módulo de Conectividad Multisalto Vehículo–RSU
==============================================
Implementa el documento "Construcción de matrices de conectividad multisalto
vehículo–RCU". A partir de las matrices de UN salto que ya genera el proyecto:

  - Matriz A (n×n): conectividad directa vehículo↔vehículo (V2V).
  - Matriz B (n×m): conectividad directa vehículo↔RSU       (V2I).

calcula, para CADA instante de tiempo de forma independiente, si un vehículo
puede alcanzar un RSU usando como máximo H "saltos" (rebotando a través de
otros vehículos):

      1 salto:  V_i ─────────────────────► R_k
      2 saltos: V_i ──► V_j ──────────────► R_k
      3 saltos: V_i ──► V_j ──► V_l ───────► R_k

Idea matemática (toda la teoría está en el PDF del proyecto):

  Ã  = A ∨ I        (se añade la identidad para "no perder" conexiones ya
                     halladas al subir el número de saltos; conserva monotonía)
  R₁ = B
  Rₕ = β(Ã · Rₕ₋₁)  (producto de matrices + binarización: solo importa si
                     existe AL MENOS un camino, no cuántos)
  Sₕ = Rₕ − Rₕ₋₁    (conexiones cuyo mínimo número de saltos es EXACTAMENTE h)
  D_H = J − R_H     (1 = el vehículo NO logró conectarse con ese RSU)
  dᵢ = 1 si la fila i de R_H es todo ceros (vehículo totalmente desconectado)

donde β(X)ᵢⱼ = 1 si Xᵢⱼ > 0, y 0 si Xᵢⱼ = 0 (operador de binarización).

--------------------------------------------------------------------------
Ejemplo del documento (4 vehículos, 3 RSU, H=3) — sirve como test mental:

  A = [[0,1,0,0],      B = [[1,0,0],
       [1,0,1,0],           [0,0,1],
       [0,1,0,0],           [0,1,0],
       [0,0,0,0]]           [0,0,0]]

  →  R₃ = [[1,1,1],   D₃ = [[0,0,0],   d = [0,0,0,1]
          [1,1,1],         [0,0,0],
          [1,1,1],         [0,0,0],
          [0,0,0]]         [1,1,1]]

  Interpretación: v1, v2 y v3 alcanzan las 3 RSU en ≤3 saltos; v4 queda
  totalmente aislado (no tiene ningún enlace, ni directo ni multisalto).
--------------------------------------------------------------------------
"""

import os
import json

import numpy as np


# ============================================================
# OPERADORES BÁSICOS (β, identidad)
# ============================================================

def binarizar(X) -> np.ndarray:
    """
    Operador de binarización β(X).

        β(X)ᵢⱼ = 1  si Xᵢⱼ > 0
        β(X)ᵢⱼ = 0  si Xᵢⱼ = 0

    Se usa después de cada multiplicación de matrices: no interesa CUÁNTOS
    caminos hay entre un vehículo y un RSU, solo si existe AL MENOS uno.

    Parámetros:
        X: matriz (lista de listas o np.ndarray) con enteros no negativos.

    Retorna:
        np.ndarray del mismo tamaño con valores en {0, 1}.
    """
    return (np.asarray(X) > 0).astype(int)


def agregar_identidad(A: np.ndarray) -> np.ndarray:
    """
    Calcula Ã = A ∨ Iₙ (OR entrada por entrada con la matriz identidad).

    En la práctica: pone 1 en toda la diagonal de A. Estos "lazos" (vᵢ→vᵢ)
    no son una transmisión física real; su único objetivo es matemático:
    garantizar que las matrices acumuladas Rₕ sean MONÓTONAS, es decir, que
    una conexión hallada a h saltos siga existiendo a h+1 saltos (no se pierda
    al aumentar el límite de saltos).

    Parámetros:
        A: matriz de adyacencia vehículo–vehículo n×n.

    Retorna:
        Ã = A ∨ Iₙ como np.ndarray binaria n×n.
    """
    A = np.asarray(A, dtype=int)
    n = A.shape[0]
    if n == 0:
        return A
    return binarizar(A + np.eye(n, dtype=int))


# ============================================================
# CONSTRUCCIÓN DE A y B ALINEADAS (mismo orden de vehículos)
# ============================================================

def construir_matriz_A(matriz_v2v_t: dict,
                        forzar_simetria: bool = True) -> tuple[list, np.ndarray]:
    """
    Construye la matriz A (vehículo×vehículo) de un instante a partir de la
    estructura que produce backend.visibilidad.generar_tuplas_v2v():

        matriz_v2v_t = {"vehiculos": ["V0", "V1", ...], "A": [[...], ...]}

    Parámetros:
        matriz_v2v_t: dict de un timestep con la lista de vehículos y la
                      matriz A cruda.
        forzar_simetria: si True (recomendado), simetriza A = β(A ∨ Aᵀ).
                      Físicamente, si el vehículo i ve al j, el j ve al i;
                      por eso A DEBE ser simétrica para que el multisalto
                      tenga sentido. Esto repara el caso en que la simulación
                      se haya corrido con la opción "dirigida" (no simétrica).

    Retorna:
        (vehiculos, A):
          - vehiculos: lista de IDs en el orden de filas/columnas de A.
          - A: np.ndarray n×n binaria, con diagonal en 0.
    """
    vehiculos = list(matriz_v2v_t.get("vehiculos", []))
    n = len(vehiculos)

    A = np.asarray(matriz_v2v_t.get("A", []), dtype=int)
    if A.size == 0:
        A = np.zeros((n, n), dtype=int)

    if forzar_simetria and A.size:
        A = binarizar(A + A.T)

    if A.size:
        np.fill_diagonal(A, 0)  # A modela enlaces entre vehículos DISTINTOS

    return vehiculos, A


def construir_matriz_B(tuplas_v2i: list, t: float,
                       vehiculos: list, rsu_ids: list) -> np.ndarray:
    """
    Construye la matriz B (vehículo×RSU) de un instante, ALINEADA al mismo
    orden de vehículos que la matriz A (esto es imprescindible para poder
    multiplicar Ã · B).

    Parámetros:
        tuplas_v2i: lista de tuplas V2I, cada una un dict
                    {"t": float, "vehiculo": "V0", "rsu": "<id>", ...}
                    (la lista que devuelve generar_tuplas_visibilidad()).
        t: instante de tiempo a construir.
        vehiculos: orden canónico de vehículos (filas). Normalmente el mismo
                   matriz_v2v_t["vehiculos"] usado para A.
        rsu_ids: orden canónico de RSU (columnas). Se recomienda sorted(rsus).

    Retorna:
        B: np.ndarray n×m binaria.
    """
    n, m = len(vehiculos), len(rsu_ids)
    B = np.zeros((n, m), dtype=int)

    v_idx = {v: i for i, v in enumerate(vehiculos)}
    r_idx = {r: j for j, r in enumerate(rsu_ids)}

    for tp in tuplas_v2i:
        if tp["t"] != t:
            continue
        i = v_idx.get(tp["vehiculo"])
        j = r_idx.get(tp["rsu"])
        if i is not None and j is not None:
            B[i, j] = 1

    return B


# ============================================================
# MATRICES ACUMULADAS (R), PRIMERA APARICIÓN (S), DESCONEXIÓN
# ============================================================

def calcular_R(A_tilde: np.ndarray, B: np.ndarray, H: int) -> list:
    """
    Calcula las matrices BRUTAS o ACUMULADAS de conectividad hasta h saltos.

        R₁ = B
        Rₕ = β(Ã · Rₕ₋₁)   para h = 2, 3, ..., H

    (Rₕ)ᵢₖ = 1 significa: el vehículo vᵢ puede conectarse con la RSU rₖ usando
    COMO MÁXIMO h saltos. Gracias a Ã = A ∨ I, se cumple R₁ ≤ R₂ ≤ ... ≤ R_H.

    Parámetros:
        A_tilde: matriz Ã = A ∨ I (n×n binaria).
        B: matriz vehículo–RSU directa (n×m binaria) = R₁.
        H: número máximo de saltos (≥ 1).

    Retorna:
        Lista [R₁, R₂, ..., R_H] de np.ndarray n×m.
    """
    R = [binarizar(B)]
    for _ in range(2, H + 1):
        R.append(binarizar(A_tilde @ R[-1]))
    return R


def calcular_S(lista_R: list) -> list:
    """
    Calcula las matrices de PRIMERA APARICIÓN.

        S₁ = R₁
        Sₕ = Rₕ − Rₕ₋₁   para h ≥ 2

    (Sₕ)ᵢₖ = 1 significa: el MÍNIMO número de saltos para que vᵢ alcance rₖ
    es EXACTAMENTE h. La resta nunca da negativos porque Rₕ₋₁ ≤ Rₕ.

    Las Sₕ son mutuamente excluyentes: cada par (vehículo, RSU) aparece en
    una sola Sₕ, la del menor número de saltos con que se logra.

    Parámetros:
        lista_R: lista [R₁, ..., R_H] devuelta por calcular_R().

    Retorna:
        Lista [S₁, ..., S_H] de np.ndarray n×m.
    """
    if not lista_R:
        return []
    S = [lista_R[0].copy()]
    for h in range(1, len(lista_R)):
        S.append(lista_R[h] - lista_R[h - 1])
    return S


def calcular_D(R_H: np.ndarray) -> np.ndarray:
    """
    Matriz de DESCONEXIÓN D_H = J − R_H (J = matriz de unos).

        (D_H)ᵢₖ = 1  si vᵢ NO logró conectarse con rₖ usando hasta H saltos
        (D_H)ᵢₖ = 0  si sí lo logró

    Parámetros:
        R_H: matriz acumulada hasta H saltos (n×m binaria).

    Retorna:
        D_H como np.ndarray n×m binaria.
    """
    return 1 - np.asarray(R_H, dtype=int)


def calcular_vector_d(R_H: np.ndarray) -> np.ndarray:
    """
    Vector de vehículos TOTALMENTE desconectados.

        dᵢ = 1  si la fila i de R_H es todo ceros (vᵢ no alcanza NINGÚN RSU)
        dᵢ = 0  en caso contrario

    Equivale a dᵢ = 1 si Σₖ (D_H)ᵢₖ = m (toda la fila de D_H son unos).

    Parámetros:
        R_H: matriz acumulada hasta H saltos (n×m binaria).

    Retorna:
        d como np.ndarray de longitud n con valores en {0, 1}.
    """
    R_H = np.asarray(R_H, dtype=int)
    if R_H.size == 0:
        return np.zeros((R_H.shape[0],), dtype=int)
    return (R_H.sum(axis=1) == 0).astype(int)


# ============================================================
# PIPELINE COMPLETO PARA UN INSTANTE
# ============================================================

def analizar_timestep(matriz_v2v_t: dict, tuplas_v2i: list, t: float,
                      rsu_ids: list, H: int = 3,
                      forzar_simetria: bool = True) -> dict:
    """
    Ejecuta el procedimiento completo del documento (pasos 1–5) para UN
    instante de tiempo t y devuelve todas las matrices más un resumen.

    Parámetros:
        matriz_v2v_t: dict {"vehiculos": [...], "A": [[...]]} del instante t.
        tuplas_v2i: lista de tuplas V2I (para construir B en ese instante).
        t: instante de tiempo.
        rsu_ids: orden canónico de RSU (columnas de B). Usar sorted(rsus).
        H: número máximo de saltos.
        forzar_simetria: simetrizar A (recomendado, ver construir_matriz_A).

    Retorna:
        dict con:
          "t", "H", "vehiculos", "rsu_ids",
          "A", "A_tilde", "B",                       (np.ndarray)
          "R": [R₁..R_H], "S": [S₁..S_H],            (listas de np.ndarray)
          "D": D_H, "d": vector d,                    (np.ndarray)
          "resumen": {
              "n_vehiculos", "m_rsus",
              "por_salto": [ {"h", "pares_acumulados", "vehiculos_conectados",
                              "pares_nuevos"} ... ],
              "vehiculos_desconectados": int,
              "ids_desconectados": [ ... ],
          }
    """
    vehiculos, A = construir_matriz_A(matriz_v2v_t, forzar_simetria)
    n = len(vehiculos)
    m = len(rsu_ids)

    B = construir_matriz_B(tuplas_v2i, t, vehiculos, rsu_ids)
    A_tilde = agregar_identidad(A)

    if n == 0:
        # Sin vehículos activos: todo vacío
        vacio_nm = np.zeros((0, m), dtype=int)
        return {
            "t": t, "H": H, "vehiculos": [], "rsu_ids": list(rsu_ids),
            "A": A, "A_tilde": A_tilde, "B": vacio_nm,
            "R": [], "S": [], "D": vacio_nm, "d": np.zeros((0,), dtype=int),
            "resumen": {
                "n_vehiculos": 0, "m_rsus": m, "por_salto": [],
                "vehiculos_desconectados": 0, "ids_desconectados": [],
            },
        }

    R = calcular_R(A_tilde, B, H)
    S = calcular_S(R)
    D = calcular_D(R[-1])
    d = calcular_vector_d(R[-1])

    # ---- Resumen por salto ----
    por_salto = []
    for h in range(1, H + 1):
        R_h = R[h - 1]
        S_h = S[h - 1]
        por_salto.append({
            "h": h,
            "pares_acumulados": int(R_h.sum()),                  # 1s en R_h
            "vehiculos_conectados": int((R_h.sum(axis=1) > 0).sum()),
            "pares_nuevos": int(S_h.sum()),                      # 1s en S_h
        })

    ids_desconectados = [vehiculos[i] for i in range(n) if d[i] == 1]

    return {
        "t": t, "H": H, "vehiculos": vehiculos, "rsu_ids": list(rsu_ids),
        "A": A, "A_tilde": A_tilde, "B": B,
        "R": R, "S": S, "D": D, "d": d,
        "resumen": {
            "n_vehiculos": n,
            "m_rsus": m,
            "por_salto": por_salto,
            "vehiculos_desconectados": int(d.sum()),
            "ids_desconectados": ids_desconectados,
        },
    }


# ============================================================
# PROCESAMIENTO DE TODOS LOS INSTANTES + EXPORTACIÓN JSON
# ============================================================

def analizar_todos(matrices_v2v: dict, tuplas_v2i: list, rsu_ids: list,
                   H: int = 3, forzar_simetria: bool = True) -> dict:
    """
    Aplica analizar_timestep() a TODOS los instantes disponibles.

    Cada instante se procesa de forma independiente (la conectividad en t_a
    no impone ninguna restricción sobre la de t_b), tal como exige el modelo.

    Parámetros:
        matrices_v2v: dict {t: {"vehiculos": [...], "A": [[...]]}} (V2V).
        tuplas_v2i: lista de tuplas V2I.
        rsu_ids: orden canónico de RSU.
        H: número máximo de saltos.
        forzar_simetria: simetrizar A.

    Retorna:
        dict {t: resultado_de_analizar_timestep}.
    """
    resultados = {}
    for t, matriz_t in matrices_v2v.items():
        resultados[t] = analizar_timestep(
            matriz_t, tuplas_v2i, t, rsu_ids, H, forzar_simetria
        )
    return resultados


def _matriz_a_lista(M) -> list:
    """Convierte np.ndarray a lista de listas de int (serializable en JSON)."""
    return np.asarray(M, dtype=int).tolist()


def guardar_multisalto_json(resultados: dict, output_dir: str,
                            incluir_matrices: bool = True) -> str:
    """
    Guarda el análisis multisalto de todos los instantes en multisalto.json.

    Parámetros:
        resultados: salida de analizar_todos() {t: resultado}.
        output_dir: directorio de salida.
        incluir_matrices: si True, guarda también R_H, D_H y el vector d por
                          instante (puede ser pesado). El resumen siempre se
                          guarda.

    Retorna:
        Ruta al archivo JSON generado.
    """
    serializable = {}
    H_global = None
    for t, res in resultados.items():
        H_global = res["H"]
        entrada = {
            "vehiculos": res["vehiculos"],
            "resumen": res["resumen"],
        }
        if incluir_matrices and res["vehiculos"]:
            entrada["R_H"] = _matriz_a_lista(res["R"][-1])
            entrada["D_H"] = _matriz_a_lista(res["D"])
            entrada["d"] = _matriz_a_lista(res["d"])
        serializable[str(t)] = entrada

    datos = {
        "parametros": {
            "H": H_global,
            "rsu_ids": list(next(iter(resultados.values()))["rsu_ids"]) if resultados else [],
            "total_timesteps": len(resultados),
        },
        "instantes": serializable,
    }

    json_path = os.path.join(output_dir, "multisalto.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)

    return json_path
