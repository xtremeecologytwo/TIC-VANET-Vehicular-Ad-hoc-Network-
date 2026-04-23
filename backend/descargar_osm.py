"""
Módulo de Descarga de Datos OSM
===============================
Descarga el archivo .osm desde la API de OpenStreetMap
usando las coordenadas del Bounding Box seleccionado por el usuario.
"""

import os
import requests


def validar_coordenadas(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> tuple[bool, str]:
    """
    Valida que las coordenadas geográficas estén dentro de rangos válidos.
    
    Retorna:
        (True, "") si son válidas,
        (False, "mensaje de error") si no lo son.
    """
    # Validar rangos geográficos reales
    if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
        return False, f"Longitud fuera de rango [-180, 180]: min={min_lon}, max={max_lon}"
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        return False, f"Latitud fuera de rango [-90, 90]: min={min_lat}, max={max_lat}"
    # Validar que min < max
    if min_lon >= max_lon:
        return False, f"min_lon ({min_lon}) debe ser menor que max_lon ({max_lon})"
    if min_lat >= max_lat:
        return False, f"min_lat ({min_lat}) debe ser menor que max_lat ({max_lat})"
    # Validar que el área no sea demasiado grande (OSM API limita a ~50,000 nodos)
    area = (max_lon - min_lon) * (max_lat - min_lat)
    if area > 0.25:
        return False, f"El área seleccionada es muy grande ({area:.4f}°²). Selecciona un área más pequeña (máx ~0.25°²)."
    
    return True, ""


def descargar_mapa_osm(min_lon: float, min_lat: float, max_lon: float, max_lat: float, 
                        output_dir: str = "output") -> tuple[str | None, str | None]:
    """
    Descarga el mapa de OpenStreetMap correspondiente al Bounding Box dado.
    
    Parámetros:
        min_lon, min_lat, max_lon, max_lat: Coordenadas del Bounding Box.
        output_dir: Directorio donde se guardará el archivo descargado.
    
    Retorna:
        (ruta_archivo, None) si la descarga fue exitosa,
        (None, mensaje_error) si hubo un error.
    """
    # Validar coordenadas antes de descargar
    valido, msg_error = validar_coordenadas(min_lon, min_lat, max_lon, max_lat)
    if not valido:
        return None, f"Coordenadas inválidas: {msg_error}"
    
    # Crear directorio de salida si no existe
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "map.osm")
    
    # URL de la API de OpenStreetMap (formato bbox=left,bottom,right,top)
    url = f"https://api.openstreetmap.org/api/0.6/map?bbox={min_lon},{min_lat},{max_lon},{max_lat}"
    
    try:
        respuesta = requests.get(url, timeout=120)
        
        if respuesta.status_code == 200:
            with open(filepath, "wb") as f:
                f.write(respuesta.content)
            # Verificar que el archivo no esté vacío
            if os.path.getsize(filepath) < 100:
                return None, "El archivo descargado está vacío. El área puede no contener datos."
            return filepath, None
        elif respuesta.status_code == 400:
            return None, "Solicitud inválida (400). Verifica que las coordenadas sean correctas y el área no sea demasiado extensa."
        elif respuesta.status_code == 509:
            return None, "Demasiadas solicitudes (509). Espera unos segundos e intenta de nuevo."
        else:
            return None, f"Error HTTP {respuesta.status_code}: {respuesta.text[:200]}"
            
    except requests.exceptions.Timeout:
        return None, "La solicitud excedió el tiempo de espera (120s). Intenta con un área más pequeña."
    except requests.exceptions.ConnectionError:
        return None, "Error de conexión. Verifica tu acceso a internet."
    except requests.exceptions.RequestException as e:
        return None, f"Error de red inesperado: {str(e)}"
