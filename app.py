"""
==================================================================
VANET Scenario Generator — Módulo 1
==================================================================
Aplicación principal de Streamlit que orquesta:
  - Frontend: Mapa interactivo con selección de Bounding Box
  - Backend:  Descarga OSM + Pipeline SUMO + Parseo XML → JSON

NOTA: El componente st_folium causa un doble re-render en Streamlit
que invalida el estado del botón. Se usa session_state con un flag
"ejecutar_pipeline" para persistir la acción del clic.
==================================================================
"""

import os
import streamlit as st
from streamlit_folium import st_folium

# ---- Importaciones del proyecto ----
from frontend.estilos import (
    inyectar_css, renderizar_header, renderizar_instrucciones,
    renderizar_coordenadas, renderizar_estado_vacio,
    renderizar_paso_pipeline, renderizar_divider, renderizar_resumen,
    renderizar_map_label
)
from frontend.mapa import crear_mapa, extraer_coordenadas_bbox, crear_mapa_resultados
from backend.descargar_osm import descargar_mapa_osm
from backend.sumo_pipeline import ejecutar_pipeline_sumo
from backend.parsear_xml import (
    parsear_junctions, parsear_edificios, obtener_proyeccion, filtrar_junctions_rsu
)


# ==========================================
# Configuración de la Página
# ==========================================
st.set_page_config(
    page_title="VANET Scenario Generator",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Inyectar CSS personalizado
inyectar_css()

# Directorio de salida para todos los archivos generados
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# ==========================================
# Estado de Sesión
# ==========================================
if "bbox" not in st.session_state:
    st.session_state.bbox = None
if "ejecutar_pipeline" not in st.session_state:
    st.session_state.ejecutar_pipeline = False
if "pipeline_resultados" not in st.session_state:
    st.session_state.pipeline_resultados = None


# ==========================================
# HEADER
# ==========================================
renderizar_header()


# ==========================================
# LAYOUT PRINCIPAL: Mapa + Panel de Control
# ==========================================
col_mapa, col_panel = st.columns([5, 2], gap="large")

# ---- Columna Izquierda: Mapa Interactivo ----
with col_mapa:
    # Label del mapa con indicador de estado
    renderizar_map_label()
    # Crear y renderizar el mapa (centrado en Quito)
    mapa = crear_mapa(centro_lat=-0.2186, centro_lon=-78.5097, zoom=14)
    datos_mapa = st_folium(mapa, width=None, height=520, key="mapa_principal")

    # Extraer coordenadas del Bounding Box dibujado
    bbox = extraer_coordenadas_bbox(datos_mapa)
    if bbox:
        st.session_state.bbox = bbox

# ---- Columna Derecha: Panel de Control ----
with col_panel:
    # Instrucciones
    renderizar_instrucciones()

    # Mostrar coordenadas o estado vacío
    if st.session_state.bbox:
        min_lon, min_lat, max_lon, max_lat = st.session_state.bbox
        renderizar_coordenadas(min_lat, min_lon, max_lat, max_lon)
    else:
        renderizar_estado_vacio()

    # Botón principal — usa callback para guardar el flag ANTES del re-render
    st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)

    def _on_click_generar():
        """Callback que se ejecuta al presionar el botón, antes del re-render."""
        st.session_state.ejecutar_pipeline = True
        st.session_state.pipeline_resultados = None

    st.button(
        "⚡ Generar Escenario",
        type="primary",
        use_container_width=True,
        key="btn_generar",
        on_click=_on_click_generar
    )


# ==========================================
# PIPELINE DE EJECUCIÓN
# ==========================================
if st.session_state.ejecutar_pipeline:
    # Resetear el flag inmediatamente para que no se re-ejecute en reruns posteriores
    st.session_state.ejecutar_pipeline = False

    if not st.session_state.bbox:
        st.warning("⚠️ Primero debes dibujar un rectángulo en el mapa para definir el área.")
    else:
        min_lon, min_lat, max_lon, max_lat = st.session_state.bbox

        renderizar_divider("🔧 Ejecución del Pipeline")

        # Contenedor para los pasos del pipeline
        pipeline_container = st.container()
        resultados_guardados = {"pasos": [], "junctions": None, "edificios": None}

        with pipeline_container:
            # ========================================
            # PASO 1: Descargar mapa de OSM
            # ========================================
            with st.spinner("📡 Descargando mapa de OpenStreetMap..."):
                osm_path, error = descargar_mapa_osm(min_lon, min_lat, max_lon, max_lat, OUTPUT_DIR)

            if error:
                renderizar_paso_pipeline("Descarga OSM", False, error)
                resultados_guardados["pasos"].append(("Descarga OSM", False, error))
                st.session_state.pipeline_resultados = resultados_guardados
                st.stop()
            else:
                tamaño = os.path.getsize(osm_path) // 1024
                msg = f"map.osm ({tamaño} KB)"
                renderizar_paso_pipeline("Descarga OSM", True, msg)
                resultados_guardados["pasos"].append(("Descarga OSM", True, msg))

            # ========================================
            # PASO 2: Pipeline SUMO
            # ========================================
            with st.spinner("🔄 Ejecutando herramientas SUMO (netconvert → polyconvert → randomTrips)..."):
                resultados_sumo = ejecutar_pipeline_sumo(osm_path, OUTPUT_DIR)

            pipeline_ok = True
            for resultado in resultados_sumo:
                renderizar_paso_pipeline(
                    resultado["paso"],
                    resultado["exito"],
                    resultado["mensaje"]
                )
                resultados_guardados["pasos"].append(
                    (resultado["paso"], resultado["exito"], resultado["mensaje"])
                )
                if not resultado["exito"]:
                    pipeline_ok = False

            if not pipeline_ok:
                st.error("❌ El pipeline de SUMO se detuvo por un error. Revisa los detalles arriba.")
                st.session_state.pipeline_resultados = resultados_guardados
                st.stop()

            # ========================================
            # PASO 3: Parseo XML → JSON
            # ========================================
            renderizar_divider("📊 Extracción de Datos")

            net_xml = os.path.join(OUTPUT_DIR, "mapa.net.xml")
            poly_xml = os.path.join(OUTPUT_DIR, "mapa.poly.xml")

            with st.spinner("🧮 Parseando junctions y edificios..."):
                junctions, err_j = parsear_junctions(net_xml, OUTPUT_DIR)
                edificios, err_e = parsear_edificios(poly_xml, OUTPUT_DIR)

            # Resultados de junctions
            if err_j:
                renderizar_paso_pipeline("Parseo Junctions", False, err_j)
                resultados_guardados["pasos"].append(("Parseo Junctions", False, err_j))
            else:
                msg_j = f"junctions_limpias.json — {len(junctions)} intersecciones útiles"
                renderizar_paso_pipeline("Parseo Junctions", True, msg_j)
                resultados_guardados["pasos"].append(("Parseo Junctions", True, msg_j))
                resultados_guardados["junctions"] = len(junctions)

            # Resultados de edificios
            if err_e:
                renderizar_paso_pipeline("Parseo Edificios", False, err_e)
                resultados_guardados["pasos"].append(("Parseo Edificios", False, err_e))
            else:
                msg_e = f"edificios_limpios.json — {len(edificios)} polígonos de edificios"
                renderizar_paso_pipeline("Parseo Edificios", True, msg_e)
                resultados_guardados["pasos"].append(("Parseo Edificios", True, msg_e))
                resultados_guardados["edificios"] = len(edificios)

            # ========================================
            # RESUMEN FINAL
            # ========================================
            if resultados_guardados["junctions"] and resultados_guardados["edificios"]:
                renderizar_resumen(resultados_guardados["junctions"], resultados_guardados["edificios"])
                st.balloons()

            # ========================================
            # MAPA DE RESULTADOS: Visualización
            # ========================================
            if junctions and edificios:
                proy = obtener_proyeccion(net_xml)
                if proy:
                    # Guardar datos para persistencia
                    resultados_guardados["junctions_data"] = junctions
                    resultados_guardados["edificios_data"] = edificios
                    resultados_guardados["proyeccion"] = proy
                    resultados_guardados["net_xml"] = net_xml

            st.session_state.pipeline_resultados = resultados_guardados


# ==========================================
# VISUALIZACIÓN DE RESULTADOS (filtrado RSU)
# ==========================================
if st.session_state.pipeline_resultados:
    resultados = st.session_state.pipeline_resultados

    # Mostrar pasos si no fue este ciclo del pipeline
    if not st.session_state.get("_pipeline_just_ran"):
        renderizar_divider("📋 Último Resultado del Pipeline")
        for nombre, exito, detalle in resultados["pasos"]:
            renderizar_paso_pipeline(nombre, exito, detalle)
        if resultados.get("junctions") and resultados.get("edificios"):
            renderizar_resumen(resultados["junctions"], resultados["edificios"])

    # Mapa con controles de filtrado RSU
    if (
        resultados.get("junctions_data")
        and resultados.get("edificios_data")
        and resultados.get("proyeccion")
    ):
        renderizar_divider("🗺️ Visualización de Resultados — RSU Placement")

        # ---- Controles de filtrado ----
        with st.expander("⚙️ Configuración de filtrado RSU", expanded=True):
            st.markdown("""
            <div style="font-size: 0.8rem; color: #94a3b8; margin-bottom: 0.6rem;">
                Ajusta los parámetros para determinar dónde colocar los <strong style="color: #06b6d4;">RSU (Road Side Units)</strong>.
                Solo se mostrarán las intersecciones que cumplan ambos criterios.
            </div>
            """, unsafe_allow_html=True)

            col_f1, col_f2 = st.columns(2)
            with col_f1:
                min_grado = st.slider(
                    "🔗 Grado mínimo de conectividad",
                    min_value=2, max_value=8, value=4, step=1,
                    help="Cuántas calles deben cruzar en la intersección. "
                         "4 = cruce de 2 calles, 6 = cruce de 3 calles."
                )
            with col_f2:
                radio_cluster = st.slider(
                    "📏 Radio de agrupación (metros)",
                    min_value=0, max_value=100, value=20, step=5,
                    help="Si dos intersecciones están a menos de esta distancia, "
                         "solo se conserva la de mayor grado."
                )

            # ---- Cobertura RSU ----
            st.markdown("---")
            mostrar_cobertura = st.checkbox(
                "📶 Mostrar radio de cobertura RSU",
                value=False,
                help="Dibuja un círculo verde alrededor de cada RSU candidato "
                     "representando su área de cobertura de comunicación."
            )

            radio_cobertura = 0
            if mostrar_cobertura:
                radio_cobertura = st.slider(
                    "📡 Radio de cobertura (metros)",
                    min_value=50, max_value=500, value=200, step=25,
                    help="Radio típico de comunicación de un RSU con tecnología DSRC/802.11p: "
                         "~300m en condiciones ideales, ~150m en entornos urbanos densos."
                )

        # ---- Aplicar filtrado ----
        junctions_originales = resultados["junctions_data"]
        edificios = resultados["edificios_data"]
        proy = resultados["proyeccion"]
        net_xml = resultados.get("net_xml", os.path.join(OUTPUT_DIR, "mapa.net.xml"))

        junctions_rsu = filtrar_junctions_rsu(
            junctions_originales, net_xml,
            min_grado=min_grado, radio_cluster=radio_cluster
        )

        # ---- Leyenda y estadísticas ----
        leyenda_cobertura = ""
        if mostrar_cobertura and radio_cobertura > 0:
            leyenda_cobertura = (
                '<span style="color: #4ade80;">◯ Verde</span> = '
                f'Cobertura ({radio_cobertura}m) &nbsp;&nbsp;'
            )

        st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 20px; margin-bottom: 0.8rem; flex-wrap: wrap;">
            <div style="font-size: 0.82rem; color: #94a3b8;">
                <span style="color: #ef4444;">★ Rojo</span> = RSU candidatos &nbsp;&nbsp;
                <span style="color: #fb923c;">■ Naranja</span> = Edificios &nbsp;&nbsp;{leyenda_cobertura}
            </div>
            <div style="background: rgba(6, 182, 212, 0.08); border: 1px solid rgba(6, 182, 212, 0.2); border-radius: 8px; padding: 4px 12px; font-size: 0.78rem;">
                <span style="color: #94a3b8;">Originales:</span> <span style="color: #06b6d4; font-weight: 700;">{len(junctions_originales)}</span>
                <span style="color: #94a3b8;"> → RSU:</span> <span style="color: #ef4444; font-weight: 700;">{len(junctions_rsu)}</span>
                <span style="color: #94a3b8;"> (reducción {100 - (len(junctions_rsu) / max(len(junctions_originales), 1) * 100):.0f}%)</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ---- Renderizar mapa ----
        mapa_res = crear_mapa_resultados(
            junctions_rsu, edificios, proy,
            radio_cobertura_m=radio_cobertura
        )
        st_folium(mapa_res, width=None, height=550, key="mapa_resultados_rsu", returned_objects=[])

