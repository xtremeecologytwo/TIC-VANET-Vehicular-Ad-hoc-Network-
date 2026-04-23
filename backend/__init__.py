# ==========================================
# Paquete Backend - VANET Scenario Generator
# Contiene la lógica de descarga, SUMO y parseo XML
# ==========================================
from backend.descargar_osm import descargar_mapa_osm
from backend.sumo_pipeline import ejecutar_pipeline_sumo
from backend.parsear_xml import (
    parsear_junctions, parsear_edificios,
    obtener_proyeccion, convertir_xy_a_lonlat,
    calcular_grado_junctions, filtrar_junctions_rsu
)

