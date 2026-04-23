"""
Módulo de Parseo XML y Extracción de Datos
==========================================
Lee los archivos XML generados por SUMO y extrae:
  - Junctions útiles (excluyendo 'internal' y 'dead_end')
  - Polígonos de edificios (tipo 'building')
Guarda los datos limpios en formato JSON.
"""

import os
import json
import xml.etree.ElementTree as ET


def parsear_junctions(net_xml_path: str, output_dir: str = "output") -> tuple[dict | None, str | None]:
    """
    Parsea el archivo .net.xml y extrae las junctions útiles.
    
    Filtra y excluye junctions con type == "internal" o "dead_end".
    Guarda el resultado como junctions_limpias.json.
    
    Parámetros:
        net_xml_path: Ruta al archivo mapa.net.xml
        output_dir: Directorio de salida para el JSON
    
    Retorna:
        (diccionario_junctions, None) si fue exitoso,
        (None, mensaje_error) si hubo error.
    """
    try:
        tree = ET.parse(net_xml_path)
        root = tree.getroot()
    except ET.ParseError as e:
        return None, f"Error parseando XML de red: {e}"
    except FileNotFoundError:
        return None, f"Archivo no encontrado: {net_xml_path}"
    
    junctions = {}
    tipos_excluidos = {"internal", "dead_end"}
    
    for junction in root.findall("junction"):
        j_type = junction.get("type", "")
        j_id = junction.get("id")
        
        # Filtrar los tipos no deseados
        if j_type in tipos_excluidos:
            continue
        
        try:
            x = float(junction.get("x", "0"))
            y = float(junction.get("y", "0"))
            junctions[j_id] = {"x": x, "y": y}
        except (ValueError, TypeError):
            # Si no se puede convertir a float, saltamos esa junction
            continue
    
    # Guardar el JSON resultante
    json_path = os.path.join(output_dir, "junctions_limpias.json")
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(junctions, f, indent=4, ensure_ascii=False)
    except IOError as e:
        return None, f"Error guardando archivo JSON: {e}"
    
    return junctions, None


def parsear_edificios(poly_xml_path: str, output_dir: str = "output") -> tuple[dict | None, str | None]:
    """
    Parsea el archivo .poly.xml y extrae los polígonos de tipo 'building'.
    
    El atributo 'shape' tiene formato "x1,y1 x2,y2 x3,y3 ..."
    Se convierte a una lista de tuplas [(x1, y1), (x2, y2), ...].
    Guarda el resultado como edificios_limpios.json.
    
    Parámetros:
        poly_xml_path: Ruta al archivo mapa.poly.xml
        output_dir: Directorio de salida para el JSON
    
    Retorna:
        (diccionario_edificios, None) si fue exitoso,
        (None, mensaje_error) si hubo error.
    """
    try:
        tree = ET.parse(poly_xml_path)
        root = tree.getroot()
    except ET.ParseError as e:
        return None, f"Error parseando XML de polígonos: {e}"
    except FileNotFoundError:
        return None, f"Archivo no encontrado: {poly_xml_path}"
    
    edificios = {}
    
    for poly in root.findall("poly"):
        p_type = poly.get("type", "")
        
        # Solo nos interesan los polígonos de tipo building
        if "building" not in p_type.lower():
            continue
        
        p_id = poly.get("id")
        shape_str = poly.get("shape", "")
        
        # Convertir "x1,y1 x2,y2 ..." en lista de tuplas
        lista_coords = []
        for par in shape_str.strip().split():
            partes = par.split(",")
            if len(partes) == 2:
                try:
                    lista_coords.append([float(partes[0]), float(partes[1])])
                except ValueError:
                    pass
        
        # Solo agregar si tiene geometría válida (al menos 3 puntos para un polígono)
        if len(lista_coords) >= 3:
            edificios[p_id] = lista_coords
    
    # Guardar el JSON resultante
    json_path = os.path.join(output_dir, "edificios_limpios.json")
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(edificios, f, indent=4, ensure_ascii=False)
    except IOError as e:
        return None, f"Error guardando archivo JSON: {e}"
    
    return edificios, None


def obtener_proyeccion(net_xml_path: str) -> dict | None:
    """
    Lee el elemento <location> del archivo .net.xml para obtener
    los parámetros de proyección necesarios para convertir coordenadas
    SUMO (x, y en metros) de vuelta a coordenadas geográficas (lon, lat).
    
    Retorna un diccionario con:
        - orig: [lon_min, lat_min, lon_max, lat_max] (boundary original)
        - conv: [x_min, y_min, x_max, y_max] (boundary convertido)
    O None si no se pudo leer.
    """
    try:
        tree = ET.parse(net_xml_path)
        root = tree.getroot()
    except (ET.ParseError, FileNotFoundError):
        return None
    
    location = root.find("location")
    if location is None:
        return None
    
    try:
        orig = [float(v) for v in location.get("origBoundary", "").split(",")]
        conv = [float(v) for v in location.get("convBoundary", "").split(",")]
        
        if len(orig) != 4 or len(conv) != 4:
            return None
        
        return {"orig": orig, "conv": conv}
    except (ValueError, AttributeError):
        return None


def convertir_xy_a_lonlat(x: float, y: float, proy: dict) -> tuple[float, float]:
    """
    Convierte coordenadas SUMO (x, y en metros) a coordenadas geográficas (lat, lon)
    usando interpolación lineal entre los boundaries original y convertido.
    
    Parámetros:
        x, y: Coordenadas en el sistema SUMO (metros).
        proy: Diccionario de proyección obtenido de obtener_proyeccion().
    
    Retorna:
        Tupla (lat, lon) en grados decimales.
    """
    orig = proy["orig"]  # [lon_min, lat_min, lon_max, lat_max]
    conv = proy["conv"]  # [x_min, y_min, x_max, y_max]
    
    # Evitar división por cero
    dx = conv[2] - conv[0]
    dy = conv[3] - conv[1]
    
    if dx == 0 or dy == 0:
        return 0.0, 0.0
    
    # Interpolación lineal: mapear de [conv_min, conv_max] a [orig_min, orig_max]
    lon = orig[0] + (x - conv[0]) / dx * (orig[2] - orig[0])
    lat = orig[1] + (y - conv[1]) / dy * (orig[3] - orig[1])
    
    return lat, lon


def calcular_grado_junctions(net_xml_path: str) -> dict[str, int]:
    """
    Calcula el grado de conectividad de cada junction, es decir,
    cuántas aristas (calles) no-internas están conectadas a ella.
    
    En SUMO, una calle bidireccional cuenta como 2 aristas (ida y vuelta).
    Entonces:
      - grado 2 = una sola calle pasa por ahí (nodo intermedio)
      - grado 4 = cruce de 2 calles bidireccionales (intersección en cruz)
      - grado 6 = cruce de 3 calles bidireccionales (intersección en Y/T triple)
    
    Parámetros:
        net_xml_path: Ruta al archivo mapa.net.xml
    
    Retorna:
        Diccionario {junction_id: grado}
    """
    try:
        tree = ET.parse(net_xml_path)
        root = tree.getroot()
    except (ET.ParseError, FileNotFoundError):
        return {}
    
    grados = {}
    
    for edge in root.findall("edge"):
        # Ignorar aristas internas (las de dentro de las junction)
        if edge.get("function") == "internal":
            continue
        
        from_id = edge.get("from")
        to_id = edge.get("to")
        
        if from_id:
            grados[from_id] = grados.get(from_id, 0) + 1
        if to_id:
            grados[to_id] = grados.get(to_id, 0) + 1
    
    return grados


def filtrar_junctions_rsu(junctions: dict, net_xml_path: str,
                           min_grado: int = 4, radio_cluster: float = 20.0) -> dict:
    """
    Filtra las junctions para obtener puntos óptimos de colocación de RSU
    (Road Side Units) en redes vehiculares.
    
    Aplica dos filtros secuenciales:
    
    1. FILTRO POR GRADO: Solo conserva junctions con >= min_grado aristas
       conectadas. Esto elimina nodos intermedios y conserva solo las
       intersecciones reales donde cruzan múltiples calles.
       
    2. CLUSTERING ESPACIAL: Agrupa junctions que están a menos de
       radio_cluster metros entre sí y conserva solo la de mayor grado
       (o la primera si tienen igual grado). Esto evita que una misma
       intersección física tenga múltiples puntos RSU.
    
    Parámetros:
        junctions: Diccionario {id: {"x": float, "y": float}} con las junctions.
        net_xml_path: Ruta al archivo .net.xml para calcular grados.
        min_grado: Grado mínimo de conectividad (default 4 = cruce de 2 calles).
        radio_cluster: Radio en metros para agrupar junctions cercanas (default 20m).
    
    Retorna:
        Diccionario {id: {"x": float, "y": float, "grado": int}} con las
        junctions filtradas y optimizadas para RSU.
    """
    import math
    
    # Paso 1: Calcular grado de cada junction
    grados = calcular_grado_junctions(net_xml_path)
    
    # Paso 2: Filtrar por grado mínimo
    candidatos = {}
    for j_id, coords in junctions.items():
        grado = grados.get(j_id, 0)
        if grado >= min_grado:
            candidatos[j_id] = {"x": coords["x"], "y": coords["y"], "grado": grado}
    
    # Si no hay clustering o no quedan candidatos, retornar así
    if radio_cluster <= 0 or not candidatos:
        return candidatos
    
    # Paso 3: Clustering espacial greedy (prioriza mayor grado)
    # Ordenar por grado descendente para que los nodos más conectados
    # sean los "centros" del cluster
    ordenados = sorted(candidatos.items(), key=lambda x: x[1]["grado"], reverse=True)
    
    centros = {}  # Resultado final: junctions representativas
    
    for j_id, datos in ordenados:
        x, y = datos["x"], datos["y"]
        
        # Verificar si ya hay un centro de cluster dentro del radio
        demasiado_cerca = False
        for c_id, c_datos in centros.items():
            dist = math.sqrt((x - c_datos["x"]) ** 2 + (y - c_datos["y"]) ** 2)
            if dist <= radio_cluster:
                demasiado_cerca = True
                break
        
        # Si no hay ningún centro cerca, este nodo se convierte en centro
        if not demasiado_cerca:
            centros[j_id] = datos
    
    return centros


