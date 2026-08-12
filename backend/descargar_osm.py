"""
Módulo de Descarga de Datos OSM
===============================
Descarga el archivo .osm de un Bounding Box usando la **Overpass API**.

Antes se usaba la API principal de OpenStreetMap (`/api/0.6/map`), pero esa
rechaza con HTTP 400 cualquier área con más de ~50 000 nodos (el centro de una
ciudad los supera enseguida). Overpass permite áreas mucho más grandes; sus
límites son de tiempo/memoria del servidor, no un tope duro de nodos.
"""

import os
import requests

# Endpoint público de Overpass (bbox en orden S,W,N,E).
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Overpass (su CDN) rechaza con 406 el User-Agent por defecto de requests; hay que
# enviar uno propio identificando la app.
HEADERS = {"User-Agent": "SmartCityNet-VANET/1.0 (TIC EPN; academic use)"}
# Tope de seguridad del área (grados²). Overpass aguanta bastante, pero áreas
# enormes hacen que SUMO (netconvert) tarde muchísimo; este límite evita abusos.
MAX_AREA_DEG2 = 1.5


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
    # Tope de seguridad (Overpass aguanta grande, pero SUMO tarda mucho en áreas enormes)
    area = (max_lon - min_lon) * (max_lat - min_lat)
    if area > MAX_AREA_DEG2:
        return False, (f"El área seleccionada es muy grande ({area:.3f}°²). "
                       f"Selecciona un área más pequeña (máx ~{MAX_AREA_DEG2}°²).")

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

    # Consulta Overpass: nodos + vías + relaciones del bbox (S,W,N,E). El `>;`
    # recupera los nodos que definen la geometría de las vías, de modo que el
    # .osm resultante es completo y lo consumen netconvert/polyconvert.
    query = (
        "[out:xml][timeout:180];"
        f"(node({min_lat},{min_lon},{max_lat},{max_lon});"
        f"way({min_lat},{min_lon},{max_lat},{max_lon});"
        f"relation({min_lat},{min_lon},{max_lat},{max_lon}););"
        "out body;>;out skel qt;"
    )

    try:
        respuesta = requests.post(OVERPASS_URL, data={"data": query}, headers=HEADERS, timeout=300)

        if respuesta.status_code == 200:
            contenido = respuesta.content
            # Overpass a veces responde 200 con un <remark> de error (timeout/exceso).
            if b"<remark>" in contenido and (b"runtime error" in contenido or b"timed out" in contenido.lower()):
                return None, ("Overpass no pudo procesar el área (demasiado grande o servidor "
                              "ocupado). Prueba un área menor o reintenta en unos segundos.")
            with open(filepath, "wb") as f:
                f.write(contenido)
            if os.path.getsize(filepath) < 200:
                return None, "El área descargada está casi vacía (puede no contener calles)."
            return filepath, None
        elif respuesta.status_code == 429:
            return None, "Overpass: demasiadas solicitudes (429). Espera unos segundos e intenta de nuevo."
        elif respuesta.status_code in (504, 508):
            return None, "Overpass: tiempo/recursos agotados. El área es muy grande; redúcela e intenta de nuevo."
        else:
            return None, f"Error HTTP {respuesta.status_code} de Overpass: {respuesta.text[:200]}"

    except requests.exceptions.Timeout:
        return None, "La descarga excedió el tiempo de espera (300s). Reduce el tamaño del área."
    except requests.exceptions.ConnectionError:
        return None, "Error de conexión. Verifica tu acceso a internet."
    except requests.exceptions.RequestException as e:
        return None, f"Error de red inesperado: {str(e)}"
