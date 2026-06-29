"""
Módulo de Visibilidad V2I — Line of Sight (LoS)
================================================
Implementa el algoritmo de detección de línea de vista directa entre
vehículos y RSU (Road Side Units), considerando edificios como
obstrucciones.

Concepto clave:
  Un vehículo V tiene LoS (Line of Sight) con un RSU si:
    1. La distancia euclidiana V↔RSU ≤ radio_obu
    2. El segmento recto V→RSU NO intersecta ningún polígono de edificio

  Las conexiones se generan considerando únicamente la cobertura del
  OBU (On Board Unit) del vehículo. Es decir, un vehículo se conecta
  a un RSU solo si este se encuentra dentro del radio de cobertura
  del OBU del vehículo.

Algoritmo de intersección segmento–polígono:
  Para determinar si un segmento (línea recta V→RSU) atraviesa un edificio,
  se descompone el polígono del edificio en sus aristas y se comprueba si
  ALGUNA arista del polígono intersecta el segmento. También se verifica si
  alguno de los extremos del segmento está DENTRO del polígono.

  Se usa el método de la orientación de puntos (CCW — Counter-Clockwise)
  para el test de intersección de dos segmentos, que es O(1) por par de
  segmentos y numéricamente estable.
"""

import math
import json
import os


# ============================================================
# GEOMETRÍA COMPUTACIONAL — Tests de intersección
# ============================================================

def _ccw(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
    """
    Calcula la orientación de tres puntos A, B, C.

    Retorna:
      > 0 si A→B→C gira en sentido antihorario (CCW)
      < 0 si A→B→C gira en sentido horario (CW)
      = 0 si A, B, C son colineales

    Fórmula: determinante de la matriz 2×2
        | (Bx - Ax)  (Cx - Ax) |
        | (By - Ay)  (Cy - Ay) |

    Esta es la base del test de intersección de segmentos.
    """
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _segmentos_intersectan(p1x: float, p1y: float, p2x: float, p2y: float,
                            p3x: float, p3y: float, p4x: float, p4y: float) -> bool:
    """
    Determina si el segmento P1P2 intersecta con el segmento P3P4.

    Usa el test de orientación (CCW) para determinar si los extremos de
    un segmento están en lados opuestos del otro segmento.

    Dos segmentos se intersectan si y solo si:
      - P1 y P2 están en lados opuestos de la línea P3P4, Y
      - P3 y P4 están en lados opuestos de la línea P1P2

    Caso especial: si algún punto es colineal con el otro segmento,
    se verifica si está contenido dentro del segmento (geometría exacta).

    Parámetros:
        p1x, p1y — Primer extremo del segmento 1
        p2x, p2y — Segundo extremo del segmento 1
        p3x, p3y — Primer extremo del segmento 2
        p4x, p4y — Segundo extremo del segmento 2

    Retorna:
        True si los segmentos se intersectan, False si no.
    """
    d1 = _ccw(p3x, p3y, p4x, p4y, p1x, p1y)
    d2 = _ccw(p3x, p3y, p4x, p4y, p2x, p2y)
    d3 = _ccw(p1x, p1y, p2x, p2y, p3x, p3y)
    d4 = _ccw(p1x, p1y, p2x, p2y, p4x, p4y)

    # Caso general: extremos en lados opuestos
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True

    # Casos colineales: verificar si un punto está sobre el otro segmento
    if d1 == 0 and _punto_en_segmento(p3x, p3y, p4x, p4y, p1x, p1y):
        return True
    if d2 == 0 and _punto_en_segmento(p3x, p3y, p4x, p4y, p2x, p2y):
        return True
    if d3 == 0 and _punto_en_segmento(p1x, p1y, p2x, p2y, p3x, p3y):
        return True
    if d4 == 0 and _punto_en_segmento(p1x, p1y, p2x, p2y, p4x, p4y):
        return True

    return False


def _punto_en_segmento(sx: float, sy: float, ex: float, ey: float,
                        px: float, py: float) -> bool:
    """
    Verifica si el punto P está contenido dentro del segmento S→E.
    Asume que P ya es colineal con S y E (verificado previamente por CCW).

    Comprueba que las coordenadas de P estén dentro del bounding box del segmento.
    """
    return (min(sx, ex) <= px <= max(sx, ex) and
            min(sy, ey) <= py <= max(sy, ey))


def _punto_dentro_poligono(px: float, py: float, poligono: list) -> bool:
    """
    Determina si un punto P está dentro de un polígono usando el algoritmo
    de Ray Casting (lanzamiento de rayo).

    El algoritmo traza un rayo horizontal desde el punto P hacia la derecha
    y cuenta cuántas veces cruza las aristas del polígono. Si el número de
    cruces es impar, el punto está dentro; si es par, está fuera.

    Parámetros:
        px, py: Coordenadas del punto a evaluar.
        poligono: Lista de vértices [[x1,y1], [x2,y2], ...].

    Retorna:
        True si el punto está dentro del polígono.
    """
    n = len(poligono)
    dentro = False

    j = n - 1
    for i in range(n):
        xi, yi = poligono[i][0], poligono[i][1]
        xj, yj = poligono[j][0], poligono[j][1]

        # Si la arista cruza la línea horizontal del punto
        if ((yi > py) != (yj > py)) and \
           (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            dentro = not dentro

        j = i

    return dentro


# ============================================================
# LINE OF SIGHT (LoS) — Detección de visibilidad
# ============================================================

def _calcular_bbox_edificio(vertices: list) -> tuple:
    """
    Calcula el bounding box (rectángulo envolvente) de un polígono de edificio.

    Se usa para pre-filtrar rápidamente qué edificios pueden estar en el
    camino del segmento V→RSU, sin tener que hacer el test de intersección
    completo (que es más costoso).

    Retorna: (x_min, y_min, x_max, y_max)
    """
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    return (min(xs), min(ys), max(xs), max(ys))


def _bboxes_se_solapan(ax_min: float, ay_min: float, ax_max: float, ay_max: float,
                        bx_min: float, by_min: float, bx_max: float, by_max: float) -> bool:
    """
    Verifica si dos bounding boxes se solapan (tienen intersección no vacía).

    Dos rectángulos NO se solapan si uno está completamente a la izquierda,
    derecha, arriba o abajo del otro. Si ninguna de esas condiciones se cumple,
    entonces sí se solapan.
    """
    return not (ax_max < bx_min or bx_max < ax_min or
                ay_max < by_min or by_max < ay_min)


def tiene_linea_de_vista(vx: float, vy: float, rx: float, ry: float,
                          edificios_cercanos: list) -> bool:
    """
    Determina si existe línea de vista directa entre un vehículo en (vx, vy)
    y un RSU en (rx, ry), considerando los edificios como obstrucciones.

    Algoritmo:
      1. Calcular el bounding box del segmento V→RSU
      2. Para cada edificio cercano:
         a. Si el bbox del edificio no se solapa con el del segmento → ignorar
         b. Si sí se solapa, verificar intersección del segmento con
            cada arista del polígono del edificio
         c. También verificar si V o RSU están DENTRO del edificio
      3. Si algún edificio intersecta → return False (NLoS)
      4. Si ninguno intersecta → return True (LoS)

    Parámetros:
        vx, vy: Posición del vehículo (coordenadas SUMO en metros).
        rx, ry: Posición del RSU (coordenadas SUMO en metros).
        edificios_cercanos: Lista de polígonos de edificios a evaluar.
                           Cada elemento es una lista de vértices [[x,y], ...].

    Retorna:
        True si hay línea de vista directa (LoS).
        False si un edificio bloquea la vista (NLoS).
    """
    # Bounding box del segmento V→RSU
    seg_xmin = min(vx, rx)
    seg_ymin = min(vy, ry)
    seg_xmax = max(vx, rx)
    seg_ymax = max(vy, ry)

    for edificio in edificios_cercanos:
        # Pre-filtro: bounding box del edificio vs bounding box del segmento
        bbox = _calcular_bbox_edificio(edificio)
        if not _bboxes_se_solapan(seg_xmin, seg_ymin, seg_xmax, seg_ymax,
                                   bbox[0], bbox[1], bbox[2], bbox[3]):
            continue

        # Test completo: verificar si alguna arista del edificio
        # intersecta con el segmento V→RSU
        n_vertices = len(edificio)
        for i in range(n_vertices):
            j = (i + 1) % n_vertices
            ex1, ey1 = edificio[i][0], edificio[i][1]
            ex2, ey2 = edificio[j][0], edificio[j][1]

            if _segmentos_intersectan(vx, vy, rx, ry, ex1, ey1, ex2, ey2):
                return False  # NLoS — un edificio bloquea la vista

        # Verificar si algún extremo está dentro del edificio
        if _punto_dentro_poligono(vx, vy, edificio):
            return False
        if _punto_dentro_poligono(rx, ry, edificio):
            return False

    return True  # LoS confirmado — ningún edificio bloquea


# ============================================================
# GENERACIÓN DE TUPLAS DE VISIBILIDAD
# ============================================================

def _precalcular_edificios_por_rsu(rsus: dict, edificios: dict,
                                    radio: float) -> dict:
    """
    Pre-calcula qué edificios están cerca de cada RSU para evitar
    evaluar TODOS los edificios en cada test de LoS.

    Para cada RSU, filtra los edificios cuyo bounding box se solapa con
    el círculo de cobertura del RSU (aproximado por un cuadrado).

    Este pre-cálculo se hace UNA SOLA VEZ y reduce el número de
    edificios a evaluar en cada timestep de ~500 a ~20-50 por RSU.

    Parámetros:
        rsus: Dict {id: {"x": float, "y": float, ...}}
        edificios: Dict {id: [[x, y], ...]}
        radio: Radio de cobertura efectivo en metros.

    Retorna:
        Dict {rsu_id: [lista_de_poligonos_cercanos]}
    """
    edificios_por_rsu = {}

    for rsu_id, rsu_datos in rsus.items():
        rx, ry = rsu_datos["x"], rsu_datos["y"]

        # Cuadrado envolvente del círculo de cobertura
        rsu_bbox = (rx - radio, ry - radio, rx + radio, ry + radio)

        cercanos = []
        for e_id, vertices in edificios.items():
            bbox = _calcular_bbox_edificio(vertices)
            if _bboxes_se_solapan(rsu_bbox[0], rsu_bbox[1], rsu_bbox[2], rsu_bbox[3],
                                   bbox[0], bbox[1], bbox[2], bbox[3]):
                cercanos.append(vertices)

        edificios_por_rsu[rsu_id] = cercanos

    return edificios_por_rsu


def generar_tuplas_visibilidad(datos_fcd: dict, rsus: dict, edificios: dict,
                                radio_obu: float = 300.0) -> tuple[list, dict]:
    """
    Genera la matriz de tuplas <t, V, RSU> que representan los momentos
    en que un vehículo tiene línea de vista directa (LoS) con un RSU.

    Las conexiones se generan considerando únicamente la cobertura del
    OBU (On Board Unit) del vehículo. Un vehículo se conecta a un RSU
    solo si este se encuentra dentro del radio de cobertura de su OBU.

    Algoritmo principal:
      Para cada timestep t en los datos FCD:
        Para cada vehículo V activo en t:
          Para cada RSU:
            1. Calcular distancia euclidiana V↔RSU
            2. Si distancia > radio_obu → no hay contacto
            3. Si distancia ≤ radio_obu:
               a. Verificar LoS (sin edificios bloqueando)
               b. Si LoS confirmado → añadir tupla <t, V, RSU>

    Solo se añaden tuplas con LoS CONFIRMADO (no se incluyen NLoS).

    Parámetros:
        datos_fcd: Diccionario {timestep: [{id, x, y, speed, angle}, ...]}
                  obtenido de parsear_fcd().
        rsus: Diccionario de RSU candidatos {id: {x, y, grado}}.
        edificios: Diccionario de edificios {id: [[x, y], ...]}.
        radio_obu: Radio de cobertura del OBU del vehículo en metros (~300m).

    Retorna:
        Tupla (lista_tuplas, estadisticas):
        - lista_tuplas: Lista de diccionarios, cada uno representando una tupla:
            {"t": float, "vehiculo": str, "rsu": str, "distancia": float}
        - estadisticas: Diccionario con resumen por RSU y general.
    """
    # Pre-calcular edificios cercanos a cada RSU (optimización O(1) por RSU)
    edificios_cercanos = _precalcular_edificios_por_rsu(rsus, edificios, radio_obu)

    tuplas = []
    # Estadísticas por RSU
    stats_rsu = {rsu_id: {"contactos": 0, "vehiculos": set()} for rsu_id in rsus}

    # Ordenar timesteps para procesamiento secuencial
    timesteps_ordenados = sorted(datos_fcd.keys())

    for t in timesteps_ordenados:
        vehiculos = datos_fcd[t]

        for vehiculo in vehiculos:
            vx, vy = vehiculo["x"], vehiculo["y"]
            v_id = vehiculo["id"]

            for rsu_id, rsu_datos in rsus.items():
                rx, ry = rsu_datos["x"], rsu_datos["y"]

                # Paso 1: Test rápido de distancia (O(1))
                distancia = math.sqrt((vx - rx) ** 2 + (vy - ry) ** 2)

                if distancia > radio_obu:
                    continue  # Fuera de rango del OBU — no hay contacto

                # Paso 2: Test de LoS — verificar que no haya edificios bloqueando
                edificios_del_rsu = edificios_cercanos.get(rsu_id, [])

                if tiene_linea_de_vista(vx, vy, rx, ry, edificios_del_rsu):
                    # LoS confirmado → añadir tupla
                    tuplas.append({
                        "t": t,
                        "vehiculo": f"V{v_id}",
                        "rsu": rsu_id,
                        "distancia": round(distancia, 2)
                    })

                    # Actualizar estadísticas
                    stats_rsu[rsu_id]["contactos"] += 1
                    stats_rsu[rsu_id]["vehiculos"].add(v_id)

    # Convertir sets a conteos para serialización JSON
    estadisticas = {
        "radio_obu": radio_obu,
        "total_tuplas": len(tuplas),
        "total_timesteps": len(timesteps_ordenados),
        "resumen_por_rsu": {}
    }

    for rsu_id, stats in stats_rsu.items():
        estadisticas["resumen_por_rsu"][rsu_id] = {
            "total_contactos": stats["contactos"],
            "vehiculos_unicos": len(stats["vehiculos"])
        }

    return tuplas, estadisticas


def guardar_tuplas_json(tuplas: list, estadisticas: dict, rsus: dict,
                         output_dir: str) -> str:
    """
    Guarda la matriz de tuplas y estadísticas en un archivo JSON.

    Estructura del archivo de salida (tuplas_visibilidad.json):
    {
        "parametros": {
            "radio_obu": 300,
            "total_tuplas": 1847,
            "total_timesteps": 100,
            "resumen_por_rsu": { ... }
        },
        "rsus": {
            "RSU_ID": {"x": 128.6, "y": 206.25, "grado": 6},
            ...
        },
        "tuplas": [
            {"t": 0.0, "vehiculo": "V0", "rsu": "RSU_ID", "distancia": 45.3},
            ...
        ]
    }

    Parámetros:
        tuplas: Lista de diccionarios de tuplas.
        estadisticas: Diccionario con resumen estadístico.
        rsus: Diccionario de los RSU utilizados.
        output_dir: Directorio de salida.

    Retorna:
        Ruta al archivo JSON generado.
    """
    datos = {
        "parametros": estadisticas,
        "rsus": rsus,
        "tuplas": tuplas
    }

    json_path = os.path.join(output_dir, "tuplas_visibilidad.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)

    return json_path


# ============================================================
# CONECTIVIDAD VEHÍCULO-VEHÍCULO (V2V) — Matriz A
# ============================================================

def _precalcular_edificios_por_zona(edificios: dict, bbox: tuple,
                                     margen: float = 50.0) -> list:
    """
    Filtra los edificios que están dentro de una zona rectangular
    definida por un bounding box con margen.

    Se usa para pre-filtrar edificios relevantes en la evaluación
    de LoS entre vehículos (V2V), donde las posiciones cambian
    en cada timestep y no se puede pre-calcular por RSU fijo.

    Parámetros:
        edificios: Dict {id: [[x, y], ...]}.
        bbox: Tupla (x_min, y_min, x_max, y_max) de la zona activa.
        margen: Metros adicionales alrededor del bbox.

    Retorna:
        Lista de polígonos (listas de vértices) dentro de la zona.
    """
    bx_min = bbox[0] - margen
    by_min = bbox[1] - margen
    bx_max = bbox[2] + margen
    by_max = bbox[3] + margen

    cercanos = []
    for e_id, vertices in edificios.items():
        e_bbox = _calcular_bbox_edificio(vertices)
        if _bboxes_se_solapan(bx_min, by_min, bx_max, by_max,
                               e_bbox[0], e_bbox[1], e_bbox[2], e_bbox[3]):
            cercanos.append(vertices)

    return cercanos


def generar_tuplas_v2v(datos_fcd: dict, edificios: dict,
                        radio_obu: float = 300.0,
                        bidireccional: bool = True) -> tuple[list, dict, dict]:
    """
    Genera la matriz de tuplas <t, vi, vj> que representan los momentos
    en que dos vehículos tienen conectividad directa (LoS) entre sí.

    Construye la Matriz A (vehículo-vehículo) para cada timestep:
        A ∈ {0, 1}^{n×n}
        A_ij = 1 si el vehículo v_i ve directamente al vehículo v_j

    Si la conectividad se modela como bidireccional (por defecto), la
    existencia de la tupla (t, vi, vj) implica también (t, vj, vi),
    y la Matriz A es simétrica.

    Algoritmo:
      Para cada timestep t en FCD:
        Para cada par de vehículos (vi, vj) con i < j:
          1. Calcular distancia euclidiana vi↔vj
          2. Si distancia > radio_obu → no hay contacto
          3. Si distancia ≤ radio_obu:
             a. Verificar LoS (sin edificios bloqueando)
             b. Si LoS → añadir tupla <t, vi, vj>
             c. Si bidireccional → añadir también <t, vj, vi>

    Parámetros:
        datos_fcd: Diccionario {timestep: [{id, x, y, speed, angle}, ...]}
                  obtenido de parsear_fcd().
        edificios: Diccionario de edificios {id: [[x, y], ...]}.
        radio_obu: Radio de cobertura del OBU del vehículo en metros.
        bidireccional: Si True, la Matriz A es simétrica (default True).

    Retorna:
        Tupla (lista_tuplas_v2v, matrices_por_timestep, estadisticas):
        - lista_tuplas_v2v: Lista de dicts {t, vehiculo_i, vehiculo_j, distancia}
        - matrices_por_timestep: Dict {t: {"vehiculos": [...], "A": [[...]]}}
        - estadisticas: Diccionario con resumen general.
    """
    tuplas_v2v = []
    matrices = {}

    # Estadísticas globales
    total_pares_evaluados = 0
    total_pares_en_rango = 0
    stats_vehiculo = {}  # {v_id: {"conexiones": int, "vecinos": set}}

    timesteps_ordenados = sorted(datos_fcd.keys())

    for t in timesteps_ordenados:
        vehiculos = datos_fcd[t]
        n = len(vehiculos)

        if n < 2:
            # Con menos de 2 vehículos no hay pares posibles
            # Aún así registrar la matriz (vacía o 1x1 con diagonal 0)
            ids_t = [f"V{v['id']}" for v in vehiculos]
            matrices[t] = {
                "vehiculos": ids_t,
                "A": [[0] * n for _ in range(n)]
            }
            continue

        # IDs de vehículos en este timestep
        ids_t = [f"V{v['id']}" for v in vehiculos]
        id_to_idx = {v["id"]: i for i, v in enumerate(vehiculos)}

        # Inicializar Matriz A como n×n de ceros
        A = [[0] * n for _ in range(n)]

        # Calcular bbox de todos los vehículos para pre-filtrar edificios
        xs = [v["x"] for v in vehiculos]
        ys = [v["y"] for v in vehiculos]
        bbox_vehiculos = (min(xs), min(ys), max(xs), max(ys))

        # Pre-filtrar edificios en la zona activa
        edificios_zona = _precalcular_edificios_por_zona(
            edificios, bbox_vehiculos, margen=radio_obu
        )

        # Evaluar todos los pares (i < j) para evitar duplicados
        for i in range(n):
            for j in range(i + 1, n):
                total_pares_evaluados += 1

                vi = vehiculos[i]
                vj = vehiculos[j]
                vix, viy = vi["x"], vi["y"]
                vjx, vjy = vj["x"], vj["y"]

                # Test rápido de distancia
                distancia = math.sqrt((vix - vjx) ** 2 + (viy - vjy) ** 2)

                if distancia > radio_obu:
                    continue

                total_pares_en_rango += 1

                # Test de LoS
                if tiene_linea_de_vista(vix, viy, vjx, vjy, edificios_zona):
                    dist_redondeada = round(distancia, 2)

                    # Registrar tupla vi → vj
                    tuplas_v2v.append({
                        "t": t,
                        "vehiculo_i": f"V{vi['id']}",
                        "vehiculo_j": f"V{vj['id']}",
                        "distancia": dist_redondeada
                    })

                    # Marcar en la Matriz A
                    A[i][j] = 1

                    if bidireccional:
                        # Simetría: A_ji = A_ij
                        A[j][i] = 1

                        # Registrar tupla inversa vj → vi
                        tuplas_v2v.append({
                            "t": t,
                            "vehiculo_i": f"V{vj['id']}",
                            "vehiculo_j": f"V{vi['id']}",
                            "distancia": dist_redondeada
                        })

                    # Estadísticas por vehículo
                    for v_id in [vi["id"], vj["id"]]:
                        if v_id not in stats_vehiculo:
                            stats_vehiculo[v_id] = {"conexiones": 0, "vecinos": set()}
                    stats_vehiculo[vi["id"]]["conexiones"] += 1
                    stats_vehiculo[vi["id"]]["vecinos"].add(vj["id"])
                    stats_vehiculo[vj["id"]]["conexiones"] += 1
                    stats_vehiculo[vj["id"]]["vecinos"].add(vi["id"])

        matrices[t] = {
            "vehiculos": ids_t,
            "A": A
        }

    # Compilar estadísticas
    estadisticas = {
        "radio_obu": radio_obu,
        "bidireccional": bidireccional,
        "total_tuplas_v2v": len(tuplas_v2v),
        "total_timesteps": len(timesteps_ordenados),
        "total_pares_evaluados": total_pares_evaluados,
        "total_pares_en_rango": total_pares_en_rango,
        "resumen_por_vehiculo": {}
    }

    for v_id, stats in stats_vehiculo.items():
        estadisticas["resumen_por_vehiculo"][f"V{v_id}"] = {
            "total_conexiones": stats["conexiones"],
            "vecinos_unicos": len(stats["vecinos"])
        }

    return tuplas_v2v, matrices, estadisticas


def guardar_tuplas_v2v_json(tuplas_v2v: list, matrices: dict,
                              estadisticas: dict,
                              output_dir: str) -> str:
    """
    Guarda las tuplas V2V, matrices A y estadísticas en un archivo JSON.

    Estructura del archivo de salida (tuplas_v2v.json):
    {
        "parametros": {
            "radio_obu": 300,
            "bidireccional": true,
            "total_tuplas_v2v": 523,
            ...
        },
        "tuplas_v2v": [
            {"t": 0.0, "vehiculo_i": "V0", "vehiculo_j": "V1", "distancia": 45.3},
            ...
        ],
        "matrices": {
            "0.0": {
                "vehiculos": ["V0", "V1", "V2"],
                "A": [[0,1,0],[1,0,1],[0,1,0]]
            },
            ...
        }
    }

    Parámetros:
        tuplas_v2v: Lista de diccionarios de tuplas V2V.
        matrices: Dict {timestep: {"vehiculos": [...], "A": [[...]]}}.
        estadisticas: Diccionario con resumen estadístico.
        output_dir: Directorio de salida.

    Retorna:
        Ruta al archivo JSON generado.
    """
    # Convertir claves de timestep (float) a string para JSON
    matrices_str = {}
    for t, datos in matrices.items():
        matrices_str[str(t)] = datos

    datos = {
        "parametros": estadisticas,
        "tuplas_v2v": tuplas_v2v,
        "matrices": matrices_str
    }

    json_path = os.path.join(output_dir, "tuplas_v2v.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)

    return json_path
