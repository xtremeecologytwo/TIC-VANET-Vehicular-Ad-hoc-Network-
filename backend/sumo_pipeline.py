"""
Módulo de Automatización de SUMO
================================
Ejecuta secuencialmente las herramientas CLI de SUMO:
  1. netconvert  → genera la red vial (.net.xml)
  2. polyconvert → genera los polígonos (.poly.xml)
  3. randomTrips  → genera las rutas aleatorias (.rou.xml)
"""

import os
import sys
import subprocess


def _buscar_random_trips() -> str:
    """
    Busca la ruta del script randomTrips.py.
    Primero intenta con SUMO_HOME, luego asume que está en el PATH.
    """
    sumo_home = os.environ.get("SUMO_HOME", "")
    if sumo_home:
        ruta = os.path.join(sumo_home, "tools", "randomTrips.py")
        if os.path.isfile(ruta):
            return ruta
    # Fallback: asumir que está accesible directamente
    return "randomTrips.py"


def ejecutar_pipeline_sumo(osm_path: str, output_dir: str = "output") -> list[dict]:
    """
    Ejecuta el pipeline completo de SUMO de forma secuencial.
    
    Parámetros:
        osm_path: Ruta al archivo .osm descargado.
        output_dir: Directorio donde se generarán los archivos de salida.
    
    Retorna:
        Lista de diccionarios con el resultado de cada paso:
        [{"paso": str, "exito": bool, "mensaje": str}, ...]
    """
    resultados = []
    
    net_path = os.path.join(output_dir, "mapa.net.xml")
    poly_path = os.path.join(output_dir, "mapa.poly.xml")
    rou_path = os.path.join(output_dir, "mapa.rou.xml")
    
    # ---- Paso 1: NETCONVERT ----
    cmd_netconvert = [
        "netconvert",
        "--ramps.guess",
        "--remove-edges.isolated",
        "--edges.join",
        "--geometry.remove",
        "--osm-files", osm_path,
        "-o", net_path
    ]
    
    try:
        resultado = subprocess.run(
            cmd_netconvert, check=True,
            capture_output=True, text=True, timeout=120
        )
        resultados.append({
            "paso": "netconvert",
            "exito": True,
            "mensaje": f"Red vial generada: {net_path}",
            "archivo": net_path
        })
    except FileNotFoundError:
        resultados.append({
            "paso": "netconvert",
            "exito": False,
            "mensaje": "No se encontró 'netconvert'. ¿Está SUMO instalado y en el PATH del sistema?"
        })
        return resultados  # No tiene sentido continuar
    except subprocess.CalledProcessError as e:
        resultados.append({
            "paso": "netconvert",
            "exito": False,
            "mensaje": f"Error en netconvert:\n{e.stderr[:500]}"
        })
        return resultados
    except subprocess.TimeoutExpired:
        resultados.append({
            "paso": "netconvert",
            "exito": False,
            "mensaje": "netconvert excedió el tiempo de espera (120s)."
        })
        return resultados

    # ---- Paso 2: POLYCONVERT ----
    cmd_polyconvert = [
        "polyconvert",
        "--net-file", net_path,
        "--osm-files", osm_path,
        "-o", poly_path
    ]
    
    try:
        subprocess.run(
            cmd_polyconvert, check=True,
            capture_output=True, text=True, timeout=120
        )
        resultados.append({
            "paso": "polyconvert",
            "exito": True,
            "mensaje": f"Polígonos generados: {poly_path}",
            "archivo": poly_path
        })
    except FileNotFoundError:
        resultados.append({
            "paso": "polyconvert",
            "exito": False,
            "mensaje": "No se encontró 'polyconvert'. ¿Está SUMO instalado y en el PATH del sistema?"
        })
        return resultados
    except subprocess.CalledProcessError as e:
        resultados.append({
            "paso": "polyconvert",
            "exito": False,
            "mensaje": f"Error en polyconvert:\n{e.stderr[:500]}"
        })
        return resultados
    except subprocess.TimeoutExpired:
        resultados.append({
            "paso": "polyconvert",
            "exito": False,
            "mensaje": "polyconvert excedió el tiempo de espera (120s)."
        })
        return resultados

    # ---- Paso 3: RANDOM TRIPS ----
    random_trips_path = _buscar_random_trips()
    
    cmd_random_trips = [
        sys.executable, random_trips_path,
        "-n", net_path,
        "-r", rou_path,
        "-e", "100"
    ]
    
    try:
        subprocess.run(
            cmd_random_trips, check=True,
            capture_output=True, text=True, timeout=120
        )
        resultados.append({
            "paso": "randomTrips",
            "exito": True,
            "mensaje": f"Rutas aleatorias generadas: {rou_path}",
            "archivo": rou_path
        })
    except FileNotFoundError:
        resultados.append({
            "paso": "randomTrips",
            "exito": False,
            "mensaje": f"No se encontró randomTrips.py en: {random_trips_path}. Configura la variable SUMO_HOME."
        })
    except subprocess.CalledProcessError as e:
        resultados.append({
            "paso": "randomTrips",
            "exito": False,
            "mensaje": f"Error en randomTrips:\n{e.stderr[:500]}"
        })
    except subprocess.TimeoutExpired:
        resultados.append({
            "paso": "randomTrips",
            "exito": False,
            "mensaje": "randomTrips excedió el tiempo de espera (120s)."
        })
    
    return resultados
