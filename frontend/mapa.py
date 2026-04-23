"""
Módulo del Mapa Interactivo
===========================
Crea y configura el mapa de Folium con la herramienta de dibujo
y extrae las coordenadas del Bounding Box dibujado por el usuario.
"""

import folium
from folium.plugins import Draw, MiniMap


def crear_mapa(centro_lat: float = -0.2186, centro_lon: float = -78.5097, zoom: int = 14) -> folium.Map:
    """
    Crea un mapa de Folium con la herramienta de dibujo restringida a rectángulos.
    Usa OpenStreetMap como capa base visible con opciones alternativas.
    
    Parámetros:
        centro_lat: Latitud del centro inicial del mapa (Quito por defecto).
        centro_lon: Longitud del centro inicial del mapa (Quito por defecto).
        zoom: Nivel de zoom inicial.
    
    Retorna:
        Objeto folium.Map configurado y listo para renderizar.
    """
    # Crear mapa base con OpenStreetMap (SIEMPRE visible, máxima compatibilidad)
    m = folium.Map(
        location=[centro_lat, centro_lon],
        zoom_start=zoom,
        tiles="OpenStreetMap",
        control_scale=True
    )
    
    # Capas alternativas (el usuario puede cambiar con el control de capas)
    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        attr="CARTO",
        name="Claro (CARTO)"
    ).add_to(m)
    
    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
        attr="CARTO",
        name="Detallado (Voyager)"
    ).add_to(m)
    
    # Control de capas
    folium.LayerControl(position="topright", collapsed=True).add_to(m)
    
    # Minimapa
    m.add_child(MiniMap(toggle_display=True, position="bottomright", width=120, height=100))
    
    # Herramienta de dibujo: solo rectángulos
    draw = Draw(
        draw_options={
            'polyline': False,
            'polygon': False,
            'circle': False,
            'marker': False,
            'circlemarker': False,
            'rectangle': {
                'shapeOptions': {
                    'color': '#3b82f6',
                    'weight': 3,
                    'fillColor': '#8b5cf6',
                    'fillOpacity': 0.2,
                    'dashArray': '5, 5'
                }
            }
        },
        edit_options={'edit': False}
    )
    draw.add_to(m)
    
    return m


def extraer_coordenadas_bbox(st_data: dict) -> tuple[float, float, float, float] | None:
    """
    Extrae las coordenadas del Bounding Box desde los datos retornados por st_folium.
    
    Retorna:
        Tupla (min_lon, min_lat, max_lon, max_lat) o None si no hay dibujo válido.
    """
    if not st_data:
        return None
    
    # Intentar primero con last_active_drawing (el más reciente)
    dibujo = None
    if st_data.get("last_active_drawing"):
        dibujo = st_data["last_active_drawing"]
    elif st_data.get("all_drawings"):
        dibujo = st_data["all_drawings"][-1]
    
    if not dibujo:
        return None
    
    try:
        # GeoJSON: coordinates[0] es el anillo exterior, cada punto es [lon, lat]
        coordenadas = dibujo["geometry"]["coordinates"][0]
        
        lons = [coord[0] for coord in coordenadas]
        lats = [coord[1] for coord in coordenadas]
        
        min_lon = min(lons)
        max_lon = max(lons)
        min_lat = min(lats)
        max_lat = max(lats)
        
        # Validación: rangos geográficos válidos
        if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
            return None
        if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
            return None
        if min_lon >= max_lon or min_lat >= max_lat:
            return None
        
        return (min_lon, min_lat, max_lon, max_lat)
        
    except (KeyError, IndexError, TypeError):
        return None


def crear_mapa_resultados(junctions: dict, edificios: dict, proy: dict,
                          radio_cobertura_m: float = 0) -> folium.Map:
    """
    Crea un mapa de Folium con las junctions (como marcadores circulares)
    y los edificios (como polígonos) extraídos del pipeline SUMO.
    
    Las coordenadas SUMO (x, y en metros) se convierten a lat/lon
    usando los parámetros de proyección del archivo .net.xml.
    
    Parámetros:
        junctions: Diccionario {id: {"x": float, "y": float}}
        edificios: Diccionario {id: [[x, y], [x, y], ...]}
        proy: Diccionario de proyección con "orig" y "conv"
        radio_cobertura_m: Radio de cobertura RSU en metros (0 = no mostrar)
    
    Retorna:
        Objeto folium.Map con los datos visualizados.
    """
    from backend.parsear_xml import convertir_xy_a_lonlat
    
    # Calcular el centro del mapa a partir del boundary original
    orig = proy["orig"]  # [lon_min, lat_min, lon_max, lat_max]
    centro_lat = (orig[1] + orig[3]) / 2
    centro_lon = (orig[0] + orig[2]) / 2
    
    # Crear mapa base
    m = folium.Map(
        location=[centro_lat, centro_lon],
        zoom_start=17,
        tiles="OpenStreetMap",
        control_scale=True
    )
    
    # Capa alternativa
    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        attr="CARTO",
        name="Claro"
    ).add_to(m)
    
    # ---- GRUPO: Cobertura RSU (círculos verdes) ----
    # Se agrega ANTES de los markers para que queden detrás
    es_rsu = any("grado" in coords for coords in junctions.values())
    
    if es_rsu and radio_cobertura_m > 0:
        grupo_cobertura = folium.FeatureGroup(name="📶 Radio de Cobertura RSU")
        
        for j_id, coords in junctions.items():
            lat, lon = convertir_xy_a_lonlat(coords["x"], coords["y"], proy)
            
            # Círculo geográfico verde (en metros reales)
            folium.Circle(
                location=[lat, lon],
                radius=radio_cobertura_m,
                color="#22c55e",
                fill=True,
                fill_color="#4ade80",
                fill_opacity=0.10,
                weight=1.5,
                dash_array="6, 4",
                tooltip=(
                    f"<b>📶 Cobertura RSU</b><br>"
                    f"<b>ID:</b> {j_id}<br>"
                    f"<b>Radio:</b> {radio_cobertura_m} m"
                )
            ).add_to(grupo_cobertura)
        
        grupo_cobertura.add_to(m)
    
    # ---- GRUPO: Junctions / RSU candidatos ----
    nombre_grupo = "📡 RSU Candidatos" if es_rsu else "⭐ Intersecciones"
    grupo_junctions = folium.FeatureGroup(name=nombre_grupo)
    
    for j_id, coords in junctions.items():
        lat, lon = convertir_xy_a_lonlat(coords["x"], coords["y"], proy)
        grado = coords.get("grado")
        
        if es_rsu and grado:
            # Marcador RSU: rojo, más grande, con grado
            folium.CircleMarker(
                location=[lat, lon],
                radius=9,
                color="#ef4444",
                fill=True,
                fill_color="#f87171",
                fill_opacity=0.85,
                weight=3,
                tooltip=(
                    f"<b>📡 RSU Candidato</b><br>"
                    f"<b>ID:</b> {j_id}<br>"
                    f"<b>Grado:</b> {grado} calles conectadas<br>"
                    f"<b>Lat:</b> {lat:.6f}°<br>"
                    f"<b>Lon:</b> {lon:.6f}°"
                ),
                popup=(
                    f"<b>RSU — {j_id}</b><br>"
                    f"<b>Grado:</b> {grado}<br>"
                    f"<b>SUMO:</b> ({coords['x']}, {coords['y']})<br>"
                    f"<b>Geo:</b> ({lat:.6f}, {lon:.6f})"
                )
            ).add_to(grupo_junctions)
        else:
            # Marcador estándar: azul, más pequeño
            folium.CircleMarker(
                location=[lat, lon],
                radius=6,
                color="#3b82f6",
                fill=True,
                fill_color="#60a5fa",
                fill_opacity=0.8,
                weight=2,
                tooltip=f"<b>Junction:</b> {j_id}<br><b>x:</b> {coords['x']}<br><b>y:</b> {coords['y']}",
                popup=f"<b>ID:</b> {j_id}<br><b>SUMO:</b> ({coords['x']}, {coords['y']})<br><b>Geo:</b> ({lat:.6f}, {lon:.6f})"
            ).add_to(grupo_junctions)
    
    grupo_junctions.add_to(m)
    
    # ---- GRUPO: Edificios (polígonos) ----
    grupo_edificios = folium.FeatureGroup(name="🏢 Edificios (buildings)")
    
    for e_id, coords_sumo in edificios.items():
        # Convertir cada vértice del polígono
        vertices_latlon = []
        for punto in coords_sumo:
            lat, lon = convertir_xy_a_lonlat(punto[0], punto[1], proy)
            vertices_latlon.append([lat, lon])
        
        # Polígono naranja/rojo con tooltip
        folium.Polygon(
            locations=vertices_latlon,
            color="#f97316",
            fill=True,
            fill_color="#fb923c",
            fill_opacity=0.35,
            weight=2,
            tooltip=f"<b>Edificio:</b> {e_id}",
            popup=f"<b>ID:</b> {e_id}<br><b>Vértices:</b> {len(coords_sumo)}"
        ).add_to(grupo_edificios)
    
    grupo_edificios.add_to(m)
    
    # Control de capas para poder togglear intersecciones, edificios y cobertura
    folium.LayerControl(position="topright", collapsed=False).add_to(m)
    
    return m


