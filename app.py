"""
==================================================================
VANET Scenario Generator — Módulo 1 & 2
==================================================================
Aplicación principal de Streamlit que orquesta:
  - Módulo 1: Mapa interactivo + Descarga OSM + Pipeline SUMO + RSU Placement
  - Módulo 2: Simulación SUMO + Detección LoS + Tuplas V2I + Tuplas V2V
              + Matrices de Conectividad (A: vehículo-vehículo, B: vehículo-RSU)

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
    renderizar_map_label, renderizar_simulacion_stats, renderizar_v2v_stats
)
from frontend.mapa import (
    crear_mapa, extraer_coordenadas_bbox,
    crear_mapa_resultados, crear_mapa_conectividad
)
from backend.descargar_osm import descargar_mapa_osm
from backend.sumo_pipeline import ejecutar_pipeline_sumo
from backend.parsear_xml import (
    parsear_junctions, parsear_edificios, obtener_proyeccion, filtrar_junctions_rsu
)
from backend.simulacion_sumo import ejecutar_simulacion_sumo, parsear_fcd
from backend.visibilidad import (
    generar_tuplas_visibilidad, guardar_tuplas_json,
    generar_tuplas_v2v, guardar_tuplas_v2v_json
)
from backend.multisalto import analizar_timestep


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
if "ejecutar_simulacion" not in st.session_state:
    st.session_state.ejecutar_simulacion = False
if "simulacion_resultados" not in st.session_state:
    st.session_state.simulacion_resultados = None


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

    # ---- Controles de generación de escenario ----
    with st.expander("⚙️ Parámetros de simulación", expanded=False):
        st.markdown("""
        <div style="font-size: 0.8rem; color: #94a3b8; margin-bottom: 0.6rem;">
            Configura cuántos vehículos generar y con qué separación temporal.
        </div>
        """, unsafe_allow_html=True)

        num_vehiculos = st.slider(
            "🚗 Número de vehículos",
            min_value=5, max_value=200, value=100, step=5,
            help="Cantidad total de vehículos con rutas aleatorias a generar "
                 "durante toda la simulación."
        )
        tiempo_simulacion_min = st.slider(
            "🕐 Duración de simulación (minutos)",
            min_value=1, max_value=180, value=120, step=1,
            help="Tiempo total de la simulación SUMO. Soporta hasta 3 horas (180 min). "
                 "Ej.: 120 min = 2 horas de tráfico."
        )

        # Duración en segundos para el backend de SUMO
        tiempo_simulacion = tiempo_simulacion_min * 60

        # Salida AUTOMÁTICA de vehículos: se reparten los N autos a lo largo de
        # toda la duración (período = duración / Nº autos). Así se garantiza que
        # TODOS salgan dentro de la simulación y el tráfico sea continuo, en vez
        # de tener un intervalo fijo que dejaría autos sin aparecer.
        periodo_salida = tiempo_simulacion / num_vehiculos  # segundos entre autos

        st.markdown(f"""
        <div style="background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.2);
                    border-radius: 8px; padding: 8px 12px; font-size: 0.78rem; margin-top: 0.4rem;">
            🚦 <strong style="color:#10b981;">Salida automática:</strong>
            1 vehículo cada <strong>{periodo_salida:.1f} s</strong>
            → {num_vehiculos} autos repartidos en {tiempo_simulacion_min} min.
        </div>
        """, unsafe_allow_html=True)

    # Botón principal — usa callback para guardar el flag ANTES del re-render
    st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)

    def _on_click_generar():
        """Callback que se ejecuta al presionar el botón, antes del re-render."""
        st.session_state.ejecutar_pipeline = True
        st.session_state.pipeline_resultados = None
        st.session_state.simulacion_resultados = None

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
                resultados_sumo = ejecutar_pipeline_sumo(
                    osm_path, OUTPUT_DIR,
                    num_vehiculos=num_vehiculos,
                    periodo_salida=periodo_salida
                )

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
                    resultados_guardados["num_vehiculos"] = num_vehiculos
                    resultados_guardados["periodo_salida"] = periodo_salida
                    resultados_guardados["tiempo_simulacion"] = tiempo_simulacion

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
                    "📡 Radio de cobertura RSU (metros)",
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

        # ==========================================
        # MÓDULO 2: SIMULACIÓN V2I + V2V
        # ==========================================
        renderizar_divider("📡 Módulo 2 — Simulación de Conectividad V2I + V2V")

        st.markdown("""
        <div style="font-size: 0.85rem; color: #94a3b8; margin-bottom: 1rem; line-height: 1.6;">
            Ejecuta la simulación de tráfico en SUMO para obtener la posición de cada vehículo
            en cada instante de tiempo, y genera:<br>
            • <strong style="color: #06b6d4;">Tuplas &lt;t, V, RSU&gt;</strong> — Conectividad V2I (Matriz B: vehículo–RSU)<br>
            • <strong style="color: #eab308;">Tuplas &lt;t, Vi, Vj&gt;</strong> — Conectividad V2V (Matriz A: vehículo–vehículo)
        </div>
        """, unsafe_allow_html=True)

        # ---- Controles de simulación V2I + V2V ----
        with st.expander("⚙️ Parámetros de visibilidad V2I + V2V", expanded=True):
            radio_obu_sim = st.slider(
                "📱 Radio de cobertura OBU (metros)",
                min_value=50, max_value=500, value=300, step=25,
                key="radio_obu_sim",
                help="Radio de comunicación del OBU (On Board Unit) del vehículo. "
                     "Se usa tanto para conexiones V2I como V2V."
            )

            step_intervalo_min = st.slider(
                "⏱️ Intervalo de muestreo (minutos)",
                min_value=1, max_value=30, value=2, step=1,
                key="step_intervalo_min",
                help="Cada cuántos MINUTOS se toma una 'foto' del tráfico para "
                     "construir las matrices A y B (y el multisalto). "
                     "Ej.: 2 = cada 2 min, 15 = cada 15 min. El análisis se hace "
                     "sobre estas muestras discretas, no segundo a segundo."
            )
            # A segundos para el backend (parsear_fcd y el período de FCD de SUMO)
            step_intervalo = step_intervalo_min * 60.0

            st.markdown("---")

            v2v_bidireccional = st.checkbox(
                "🔄 Conectividad V2V bidireccional (Matriz A simétrica)",
                value=True,
                key="v2v_bidireccional",
                help="Si está activado, la existencia de la tupla (t, vi, vj) "
                     "implica también (t, vj, vi), y la Matriz A es simétrica. "
                     "Esto es lo esperado para comunicación inalámbrica."
            )

            st.markdown(f"""
            <div style="background: rgba(6, 182, 212, 0.06); border: 1px solid rgba(6, 182, 212, 0.15);
                        border-radius: 8px; padding: 8px 14px; font-size: 0.78rem; margin-top: 0.5rem;">
                <strong style="color: #06b6d4;">Radio OBU:</strong>
                <span style="color: #f1f5f9;"><strong>{radio_obu_sim}m</strong></span>
                <span style="color: #94a3b8;"> — Aplica a V2I y V2V. </span>
                <strong style="color: #eab308;">V2V:</strong>
                <span style="color: #f1f5f9;"><strong>{"Bidireccional" if v2v_bidireccional else "Dirigida"}</strong></span>
            </div>
            """, unsafe_allow_html=True)

        # ---- Botón de simulación ----
        def _on_click_simular():
            st.session_state.ejecutar_simulacion = True
            st.session_state.simulacion_resultados = None

        st.button(
            "🚀 Ejecutar Simulación V2I + V2V",
            type="primary",
            use_container_width=True,
            key="btn_simular",
            on_click=_on_click_simular,
            help="Ejecuta SUMO para simular el tráfico y genera las tuplas de visibilidad V2I y V2V."
        )

        # ==========================================
        # EJECUCIÓN DE LA SIMULACIÓN
        # ==========================================
        if st.session_state.ejecutar_simulacion:
            st.session_state.ejecutar_simulacion = False

            tiempo_sim = resultados.get("tiempo_simulacion", 150)

            renderizar_divider("🔄 Simulación SUMO en progreso")

            # Paso 1: Ejecutar simulación SUMO
            with st.spinner("🚗 Ejecutando simulación de tráfico SUMO..."):
                # SUMO solo escribe la posición cada 'step_intervalo' segundos
                # (mismo valor del muestreo), para no generar un FCD gigante.
                fcd_path, err_sim = ejecutar_simulacion_sumo(
                    OUTPUT_DIR, tiempo_sim, periodo_fcd=step_intervalo
                )

            if err_sim:
                renderizar_paso_pipeline("Simulación SUMO", False, err_sim)
            else:
                fcd_size = os.path.getsize(fcd_path) // 1024
                renderizar_paso_pipeline(
                    "Simulación SUMO", True,
                    f"fcd.xml generado ({fcd_size} KB)"
                )

                # Paso 2: Parsear FCD
                with st.spinner("📊 Parseando datos FCD (posiciones vehiculares)..."):
                    datos_fcd, err_fcd = parsear_fcd(fcd_path, step_intervalo)

                if err_fcd:
                    renderizar_paso_pipeline("Parseo FCD", False, err_fcd)
                else:
                    total_registros = sum(len(v) for v in datos_fcd.values())
                    renderizar_paso_pipeline(
                        "Parseo FCD", True,
                        f"{len(datos_fcd)} timesteps, {total_registros} registros de vehículos"
                    )

                    # Paso 3: Generar tuplas de visibilidad V2I (Matriz B)
                    with st.spinner("📡 Generando tuplas V2I — Matriz B (vehículo–RSU)..."):
                        tuplas, estadisticas = generar_tuplas_visibilidad(
                            datos_fcd, junctions_rsu, edificios,
                            radio_obu=radio_obu_sim
                        )

                    renderizar_paso_pipeline(
                        "Matriz B — Tuplas V2I (LoS)", True,
                        f"{len(tuplas)} tuplas <t, V, RSU> con LoS confirmado"
                    )

                    # Paso 4: Guardar JSON V2I
                    json_path = guardar_tuplas_json(
                        tuplas, estadisticas, junctions_rsu, OUTPUT_DIR
                    )
                    renderizar_paso_pipeline(
                        "Exportación V2I JSON", True,
                        f"tuplas_visibilidad.json ({os.path.getsize(json_path) // 1024} KB)"
                    )

                    # Paso 5: Generar tuplas V2V (Matriz A)
                    with st.spinner("🚗 Generando tuplas V2V — Matriz A (vehículo–vehículo)..."):
                        tuplas_v2v, matrices_v2v, estadisticas_v2v = generar_tuplas_v2v(
                            datos_fcd, edificios,
                            radio_obu=radio_obu_sim,
                            bidireccional=v2v_bidireccional
                        )

                    renderizar_paso_pipeline(
                        "Matriz A — Tuplas V2V (LoS)", True,
                        f"{len(tuplas_v2v)} tuplas <t, Vi, Vj> con LoS confirmado"
                    )

                    # Paso 6: Guardar JSON V2V
                    json_v2v_path = guardar_tuplas_v2v_json(
                        tuplas_v2v, matrices_v2v, estadisticas_v2v, OUTPUT_DIR
                    )
                    renderizar_paso_pipeline(
                        "Exportación V2V JSON", True,
                        f"tuplas_v2v.json ({os.path.getsize(json_v2v_path) // 1024} KB)"
                    )

                    # Guardar en sesión para persistencia
                    st.session_state.simulacion_resultados = {
                        "tuplas": tuplas,
                        "estadisticas": estadisticas,
                        "datos_fcd": datos_fcd,
                        "rsus": junctions_rsu,
                        "edificios": edificios,
                        "proyeccion": proy,
                        "radio_obu": radio_obu_sim,
                        "tuplas_v2v": tuplas_v2v,
                        "matrices_v2v": matrices_v2v,
                        "estadisticas_v2v": estadisticas_v2v,
                    }

        # ==========================================
        # RESULTADOS DE LA SIMULACIÓN V2I + V2V
        # ==========================================
        if st.session_state.simulacion_resultados:
            sim = st.session_state.simulacion_resultados
            tuplas = sim["tuplas"]
            estadisticas = sim["estadisticas"]
            datos_fcd = sim["datos_fcd"]
            rsus_sim = sim["rsus"]
            edificios_sim = sim["edificios"]
            proy_sim = sim["proyeccion"]
            tuplas_v2v = sim.get("tuplas_v2v", [])
            matrices_v2v = sim.get("matrices_v2v", {})
            estadisticas_v2v = sim.get("estadisticas_v2v", {})

            renderizar_divider("📊 Resultados de Conectividad V2I + V2V")

            # ---- Estadísticas V2I ----
            st.markdown("##### 📡 Estadísticas V2I (Matriz B — Vehículo–RSU)")
            renderizar_simulacion_stats(estadisticas)

            # ---- Estadísticas V2V ----
            st.markdown("##### 🚗 Estadísticas V2V (Matriz A — Vehículo–Vehículo)")
            renderizar_v2v_stats(estadisticas_v2v)

            if tuplas or tuplas_v2v:
                # ---- Tabs de visualización ----
                tab_tabla_v2i, tab_tabla_v2v, tab_matrices, tab_multisalto, tab_mapa = st.tabs([
                    "📋 Tuplas V2I",
                    "🚗 Tuplas V2V",
                    "🔢 Matrices A y B",
                    "🔗 Multisalto",
                    "🗺️ Mapas de Conectividad"
                ])

                # ============ TAB 1: TABLA DE TUPLAS V2I ============
                with tab_tabla_v2i:
                    if tuplas:
                        st.markdown(f"""
                        <div class="tupla-tabla-header">
                            <span class="titulo">📋 Matriz B — Tuplas &lt;t, V, RSU&gt;</span>
                            <span class="badge">{len(tuplas)} tuplas V2I</span>
                        </div>
                        """, unsafe_allow_html=True)

                        # Filtros
                        col_ft1, col_ft2, col_ft3 = st.columns(3)
                        with col_ft1:
                            rsus_disponibles = sorted(set(t["rsu"] for t in tuplas))
                            filtro_rsu = st.multiselect(
                                "Filtrar por RSU",
                                rsus_disponibles,
                                default=rsus_disponibles[:5] if len(rsus_disponibles) > 5 else rsus_disponibles,
                                key="filtro_rsu_tabla"
                            )
                        with col_ft2:
                            vehiculos_disponibles = sorted(set(t["vehiculo"] for t in tuplas))
                            filtro_vehiculo = st.multiselect(
                                "Filtrar por Vehículo",
                                vehiculos_disponibles,
                                default=[],
                                key="filtro_vehiculo_tabla"
                            )
                        with col_ft3:
                            timesteps_disponibles = sorted(set(t["t"] for t in tuplas))
                            rango_t = st.slider(
                                "Rango de tiempo (s)",
                                min_value=float(min(timesteps_disponibles)),
                                max_value=float(max(timesteps_disponibles)),
                                value=(float(min(timesteps_disponibles)),
                                       float(max(timesteps_disponibles))),
                                key="rango_t_tabla"
                            )

                        # Aplicar filtros
                        tuplas_filtradas = tuplas
                        if filtro_rsu:
                            tuplas_filtradas = [t for t in tuplas_filtradas if t["rsu"] in filtro_rsu]
                        if filtro_vehiculo:
                            tuplas_filtradas = [t for t in tuplas_filtradas if t["vehiculo"] in filtro_vehiculo]
                        tuplas_filtradas = [t for t in tuplas_filtradas
                                           if rango_t[0] <= t["t"] <= rango_t[1]]

                        # Mostrar tabla
                        st.dataframe(
                            tuplas_filtradas,
                            use_container_width=True,
                            height=400,
                            column_config={
                                "t": st.column_config.NumberColumn("⏱️ Tiempo (s)", format="%.1f"),
                                "vehiculo": st.column_config.TextColumn("🚗 Vehículo"),
                                "rsu": st.column_config.TextColumn("📡 RSU"),
                                "distancia": st.column_config.NumberColumn("📏 Distancia (m)", format="%.2f"),
                            }
                        )

                        st.markdown(f"""
                        <div style="font-size: 0.75rem; color: #94a3b8; margin-top: 0.5rem;">
                            Mostrando <strong style="color: #06b6d4;">{len(tuplas_filtradas)}</strong> de
                            <strong>{len(tuplas)}</strong> tuplas totales.
                            Cada tupla representa un momento donde un vehículo tiene LoS con un RSU.
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.info("📭 No se generaron tuplas V2I.")

                # ============ TAB 2: TABLA DE TUPLAS V2V ============
                with tab_tabla_v2v:
                    if tuplas_v2v:
                        st.markdown(f"""
                        <div class="tupla-tabla-header">
                            <span class="titulo">🚗 Matriz A — Tuplas &lt;t, Vi, Vj&gt;</span>
                            <span class="badge">{len(tuplas_v2v)} tuplas V2V</span>
                        </div>
                        """, unsafe_allow_html=True)

                        # Filtros V2V
                        col_vt1, col_vt2, col_vt3 = st.columns(3)
                        with col_vt1:
                            v2v_vehiculos_i = sorted(set(t["vehiculo_i"] for t in tuplas_v2v))
                            filtro_vi = st.multiselect(
                                "Filtrar por Vehículo i",
                                v2v_vehiculos_i,
                                default=[],
                                key="filtro_vi_tabla"
                            )
                        with col_vt2:
                            v2v_vehiculos_j = sorted(set(t["vehiculo_j"] for t in tuplas_v2v))
                            filtro_vj = st.multiselect(
                                "Filtrar por Vehículo j",
                                v2v_vehiculos_j,
                                default=[],
                                key="filtro_vj_tabla"
                            )
                        with col_vt3:
                            ts_v2v_disponibles = sorted(set(t["t"] for t in tuplas_v2v))
                            rango_t_v2v = st.slider(
                                "Rango de tiempo (s)",
                                min_value=float(min(ts_v2v_disponibles)),
                                max_value=float(max(ts_v2v_disponibles)),
                                value=(float(min(ts_v2v_disponibles)),
                                       float(max(ts_v2v_disponibles))),
                                key="rango_t_v2v_tabla"
                            )

                        # Aplicar filtros
                        v2v_filtradas = tuplas_v2v
                        if filtro_vi:
                            v2v_filtradas = [t for t in v2v_filtradas if t["vehiculo_i"] in filtro_vi]
                        if filtro_vj:
                            v2v_filtradas = [t for t in v2v_filtradas if t["vehiculo_j"] in filtro_vj]
                        v2v_filtradas = [t for t in v2v_filtradas
                                        if rango_t_v2v[0] <= t["t"] <= rango_t_v2v[1]]

                        # Mostrar tabla
                        st.dataframe(
                            v2v_filtradas,
                            use_container_width=True,
                            height=400,
                            column_config={
                                "t": st.column_config.NumberColumn("⏱️ Tiempo (s)", format="%.1f"),
                                "vehiculo_i": st.column_config.TextColumn("🚗 Vehículo i"),
                                "vehiculo_j": st.column_config.TextColumn("🚗 Vehículo j"),
                                "distancia": st.column_config.NumberColumn("📏 Distancia (m)", format="%.2f"),
                            }
                        )

                        st.markdown(f"""
                        <div style="font-size: 0.75rem; color: #94a3b8; margin-top: 0.5rem;">
                            Mostrando <strong style="color: #eab308;">{len(v2v_filtradas)}</strong> de
                            <strong>{len(tuplas_v2v)}</strong> tuplas V2V totales.
                            Cada tupla representa un momento donde dos vehículos tienen LoS directo.
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.info("📭 No se generaron tuplas V2V. Posibles causas:\n"
                                "- Pocos vehículos activos simultáneamente\n"
                                "- Radio OBU demasiado pequeño\n"
                                "- Los vehículos no se cruzan")

                # ============ TAB 3: MATRICES A y B ============
                with tab_matrices:
                    st.markdown("#### 🔢 Visualización de Matrices de Conectividad")
                    st.markdown("""
                    <div style="font-size: 0.82rem; color: #94a3b8; margin-bottom: 1rem; line-height: 1.6;">
                        Selecciona un instante de tiempo para visualizar las matrices binarias:<br>
                        • <strong style="color: #eab308;">Matriz A</strong> (n×n) — Conectividad vehículo–vehículo<br>
                        • <strong style="color: #06b6d4;">Matriz B</strong> (n×m) — Conectividad vehículo–RSU
                    </div>
                    """, unsafe_allow_html=True)

                    # Selector de timestep
                    timesteps_disponibles_mat = sorted(matrices_v2v.keys()) if matrices_v2v else sorted(datos_fcd.keys())
                    if timesteps_disponibles_mat:
                        ts_seleccionado = st.select_slider(
                            "⏱️ Seleccionar instante de tiempo (s)",
                            options=timesteps_disponibles_mat,
                            value=timesteps_disponibles_mat[len(timesteps_disponibles_mat) // 4],
                            key="ts_matriz"
                        )

                        col_mat_a, col_mat_b = st.columns(2)

                        # ---- MATRIZ A (V2V) ----
                        with col_mat_a:
                            st.markdown("##### 🚗 Matriz A — Vehículo×Vehículo")
                            if ts_seleccionado in matrices_v2v:
                                mat_data = matrices_v2v[ts_seleccionado]
                                vehiculos_mat = mat_data["vehiculos"]
                                A = mat_data["A"]
                                n_v = len(vehiculos_mat)

                                if n_v > 0:
                                    import pandas as pd
                                    df_A = pd.DataFrame(
                                        A,
                                        index=vehiculos_mat,
                                        columns=vehiculos_mat
                                    )
                                    st.dataframe(
                                        df_A,
                                        use_container_width=True,
                                        height=min(400, 40 + n_v * 35)
                                    )
                                    # Contar conexiones
                                    total_unos = sum(sum(fila) for fila in A)
                                    st.markdown(f"""
                                    <div style="font-size: 0.75rem; color: #94a3b8;">
                                        <strong style="color: #eab308;">A ∈ {{0,1}}^{{{n_v}×{n_v}}}</strong> —
                                        {total_unos} conexiones activas en t={ts_seleccionado}s
                                    </div>
                                    """, unsafe_allow_html=True)
                                else:
                                    st.info("Sin vehículos activos en este instante.")
                            else:
                                st.info("Sin datos de Matriz A para este instante.")

                        # ---- MATRIZ B (V2I) ----
                        with col_mat_b:
                            st.markdown("##### 📡 Matriz B — Vehículo×RSU")
                            # Construir Matriz B para el timestep seleccionado
                            tuplas_en_ts = [t for t in tuplas if t["t"] == ts_seleccionado]
                            vehiculos_en_ts = []
                            if ts_seleccionado in datos_fcd:
                                vehiculos_en_ts = [f"V{v['id']}" for v in datos_fcd[ts_seleccionado]]

                            rsu_ids = sorted(rsus_sim.keys())

                            if vehiculos_en_ts and rsu_ids:
                                import pandas as pd
                                n_v_b = len(vehiculos_en_ts)
                                m_r = len(rsu_ids)

                                # Inicializar B como n×m de ceros
                                B = [[0] * m_r for _ in range(n_v_b)]
                                v_idx = {v: i for i, v in enumerate(vehiculos_en_ts)}
                                r_idx = {r: j for j, r in enumerate(rsu_ids)}

                                for tp in tuplas_en_ts:
                                    vi = v_idx.get(tp["vehiculo"])
                                    rj = r_idx.get(tp["rsu"])
                                    if vi is not None and rj is not None:
                                        B[vi][rj] = 1

                                df_B = pd.DataFrame(
                                    B,
                                    index=vehiculos_en_ts,
                                    columns=rsu_ids
                                )
                                st.dataframe(
                                    df_B,
                                    use_container_width=True,
                                    height=min(400, 40 + n_v_b * 35)
                                )
                                total_unos_b = sum(sum(fila) for fila in B)
                                st.markdown(f"""
                                <div style="font-size: 0.75rem; color: #94a3b8;">
                                    <strong style="color: #06b6d4;">B ∈ {{0,1}}^{{{n_v_b}×{m_r}}}</strong> —
                                    {total_unos_b} conexiones V2I activas en t={ts_seleccionado}s
                                </div>
                                """, unsafe_allow_html=True)
                            else:
                                st.info("Sin datos para construir Matriz B en este instante.")

                # ============ TAB 4: MULTISALTO ============
                with tab_multisalto:
                    st.markdown("#### 🔗 Conectividad Multisalto Vehículo → RSU")
                    st.markdown("""
                    <div style="font-size: 0.82rem; color: #94a3b8; margin-bottom: 1rem; line-height: 1.6;">
                        Combina la <strong style="color: #eab308;">Matriz A</strong> (V2V) y la
                        <strong style="color: #06b6d4;">Matriz B</strong> (V2I) para calcular si un vehículo
                        alcanza un RSU <strong>rebotando</strong> a través de otros vehículos (multisalto):<br>
                        • <strong>1 salto:</strong> V → RSU &nbsp;&nbsp;
                        • <strong>2 saltos:</strong> V → V → RSU &nbsp;&nbsp;
                        • <strong>3 saltos:</strong> V → V → V → RSU<br>
                        Fórmulas: Ã = A ∨ I, &nbsp; R₁ = B, &nbsp; Rₕ = β(Ã·Rₕ₋₁), &nbsp;
                        Sₕ = Rₕ − Rₕ₋₁, &nbsp; D_H = J − R_H.
                    </div>
                    """, unsafe_allow_html=True)

                    if not matrices_v2v:
                        st.info("Ejecuta primero la simulación V2V para tener la Matriz A por instante.")
                    else:
                        import pandas as pd

                        # ---- Controles ----
                        col_ms1, col_ms2, col_ms3 = st.columns([2, 2, 3])
                        with col_ms1:
                            H_saltos = st.slider(
                                "🔢 Máximo de saltos (H)",
                                min_value=1, max_value=6, value=3, step=1,
                                key="H_multisalto",
                                help="Número máximo de saltos permitidos para llegar a un RSU."
                            )
                        with col_ms2:
                            forzar_sim = st.checkbox(
                                "🔄 Forzar A simétrica",
                                value=True,
                                key="forzar_sim_multisalto",
                                help="Garantiza que si i ve a j, j ve a i (recomendado). "
                                     "Repara el caso en que la simulación se corrió como 'dirigida'."
                            )
                        with col_ms3:
                            ts_ms_opciones = sorted(matrices_v2v.keys())
                            ts_ms = st.select_slider(
                                "⏱️ Instante de tiempo (s)",
                                options=ts_ms_opciones,
                                value=ts_ms_opciones[len(ts_ms_opciones) // 4],
                                key="ts_multisalto"
                            )

                        rsu_ids_ms = sorted(rsus_sim.keys())

                        # ---- Calcular el análisis multisalto del instante ----
                        res_ms = analizar_timestep(
                            matrices_v2v[ts_ms], tuplas, ts_ms,
                            rsu_ids_ms, H=H_saltos, forzar_simetria=forzar_sim
                        )

                        if res_ms["resumen"]["n_vehiculos"] == 0:
                            st.info("No hay vehículos activos en este instante.")
                        else:
                            vehiculos_ms = res_ms["vehiculos"]
                            resumen_ms = res_ms["resumen"]

                            # ---- Resumen por salto ----
                            st.markdown("##### 📈 Resumen por número de saltos")
                            df_resumen = pd.DataFrame([
                                {
                                    "Saltos (h)": f"≤ {p['h']}",
                                    "Pares V→RSU alcanzables": p["pares_acumulados"],
                                    "Vehículos con ≥1 RSU": p["vehiculos_conectados"],
                                    "Pares nuevos (exact. h)": p["pares_nuevos"],
                                }
                                for p in resumen_ms["por_salto"]
                            ])
                            st.dataframe(df_resumen, use_container_width=True, hide_index=True)

                            n_desc = resumen_ms["vehiculos_desconectados"]
                            if n_desc > 0:
                                st.warning(
                                    f"🚫 {n_desc} vehículo(s) totalmente desconectado(s) "
                                    f"(no alcanzan ningún RSU ni con {H_saltos} saltos): "
                                    f"{', '.join(resumen_ms['ids_desconectados'])}"
                                )
                            else:
                                st.success(
                                    f"✅ Todos los vehículos alcanzan al menos un RSU usando hasta {H_saltos} saltos."
                                )

                            # ---- Selector de matriz a visualizar ----
                            st.markdown("##### 🔍 Matrices del instante")
                            opciones_matriz = (
                                [f"R{h} — Acumulada (≤{h} saltos)" for h in range(1, H_saltos + 1)] +
                                [f"S{h} — Primera aparición (exact. {h})" for h in range(1, H_saltos + 1)] +
                                [f"D{H_saltos} — Desconexión (1 = no conecta)"]
                            )
                            sel_matriz = st.selectbox(
                                "Matriz a mostrar",
                                opciones_matriz,
                                key="sel_matriz_multisalto"
                            )

                            # Resolver qué matriz mostrar
                            if sel_matriz.startswith("R"):
                                h = int(sel_matriz[1:].split(" ")[0])
                                M = res_ms["R"][h - 1]
                                color = "#06b6d4"
                            elif sel_matriz.startswith("S"):
                                h = int(sel_matriz[1:].split(" ")[0])
                                M = res_ms["S"][h - 1]
                                color = "#eab308"
                            else:
                                M = res_ms["D"]
                                color = "#ef4444"

                            df_M = pd.DataFrame(M, index=vehiculos_ms, columns=rsu_ids_ms)
                            st.dataframe(
                                df_M,
                                use_container_width=True,
                                height=min(420, 60 + len(vehiculos_ms) * 35)
                            )
                            st.markdown(f"""
                            <div style="font-size: 0.75rem; color: #94a3b8;">
                                <strong style="color: {color};">{sel_matriz}</strong> —
                                tamaño {M.shape[0]}×{M.shape[1]}, {int(M.sum())} unos,
                                en t={ts_ms}s (filas = vehículos, columnas = RSU).
                            </div>
                            """, unsafe_allow_html=True)

                            # ---- Vector d de desconectados ----
                            with st.expander("📉 Vector d — vehículos totalmente desconectados"):
                                df_d = pd.DataFrame(
                                    {"d (1=aislado)": res_ms["d"]},
                                    index=vehiculos_ms
                                )
                                st.dataframe(df_d, use_container_width=True,
                                             height=min(300, 60 + len(vehiculos_ms) * 35))

                # ============ TAB 5: 4 MAPAS DE CONECTIVIDAD ============
                with tab_mapa:
                    st.markdown("#### 🗺️ Mapas de Conectividad V2I + V2V — Instantes al 25%, 50%, 75% y 100%")

                    # Leyenda
                    st.markdown("""
                    <div class="v2i-legend">
                        <div class="v2i-legend-item">
                            <div class="legend-dot" style="background: #ef4444;"></div>
                            <span>RSU</span>
                        </div>
                        <div class="v2i-legend-item">
                            <div class="legend-dot" style="background: #fb923c;"></div>
                            <span>Edificios</span>
                        </div>
                        <div class="v2i-legend-item">
                            <div class="legend-dot" style="background: #3b82f6;"></div>
                            <span>Vehículos</span>
                        </div>
                        <div class="v2i-legend-item">
                            <div class="legend-line" style="background: #22c55e;"></div>
                            <span>V2I LoS</span>
                        </div>
                        <div class="v2i-legend-item">
                            <div class="legend-line" style="background: #eab308;"></div>
                            <span>V2V LoS</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # Calcular 4 instantes exactos al 25%, 50%, 75%, 100%
                    timesteps = sorted(datos_fcd.keys())
                    n = len(timesteps)
                    indices = [
                        max(0, n // 4 - 1),
                        max(0, n // 2 - 1),
                        max(0, 3 * n // 4 - 1),
                        n - 1,
                    ]
                    instantes = [timesteps[i] for i in indices]
                    etiquetas = ["25%", "50%", "75%", "100%"]

                    # Fila 1: mapas 25% y 50%
                    col_m1, col_m2 = st.columns(2)
                    with col_m1:
                        ts = instantes[0]
                        n_v = len(datos_fcd.get(ts, []))
                        n_c = len([t for t in tuplas if t["t"] == ts])
                        n_c_v2v = len(set(
                            tuple(sorted([t["vehiculo_i"], t["vehiculo_j"]]))
                            for t in tuplas_v2v if t["t"] == ts
                        ))
                        st.markdown(f"**🗺️ {etiquetas[0]}** — t={ts:.0f}s — {n_v} veh, {n_c} V2I, {n_c_v2v} V2V")
                        mapa_q1 = crear_mapa_conectividad(
                            rsus_sim, edificios_sim, proy_sim,
                            tuplas, datos_fcd,
                            timestep_exacto=ts,
                            tuplas_v2v=tuplas_v2v
                        )
                        st_folium(mapa_q1, width=None, height=450, key="mapa_q1", returned_objects=[])

                    with col_m2:
                        ts = instantes[1]
                        n_v = len(datos_fcd.get(ts, []))
                        n_c = len([t for t in tuplas if t["t"] == ts])
                        n_c_v2v = len(set(
                            tuple(sorted([t["vehiculo_i"], t["vehiculo_j"]]))
                            for t in tuplas_v2v if t["t"] == ts
                        ))
                        st.markdown(f"**🗺️ {etiquetas[1]}** — t={ts:.0f}s — {n_v} veh, {n_c} V2I, {n_c_v2v} V2V")
                        mapa_q2 = crear_mapa_conectividad(
                            rsus_sim, edificios_sim, proy_sim,
                            tuplas, datos_fcd,
                            timestep_exacto=ts,
                            tuplas_v2v=tuplas_v2v
                        )
                        st_folium(mapa_q2, width=None, height=450, key="mapa_q2", returned_objects=[])

                    # Fila 2: mapas 75% y 100%
                    col_m3, col_m4 = st.columns(2)
                    with col_m3:
                        ts = instantes[2]
                        n_v = len(datos_fcd.get(ts, []))
                        n_c = len([t for t in tuplas if t["t"] == ts])
                        n_c_v2v = len(set(
                            tuple(sorted([t["vehiculo_i"], t["vehiculo_j"]]))
                            for t in tuplas_v2v if t["t"] == ts
                        ))
                        st.markdown(f"**🗺️ {etiquetas[2]}** — t={ts:.0f}s — {n_v} veh, {n_c} V2I, {n_c_v2v} V2V")
                        mapa_q3 = crear_mapa_conectividad(
                            rsus_sim, edificios_sim, proy_sim,
                            tuplas, datos_fcd,
                            timestep_exacto=ts,
                            tuplas_v2v=tuplas_v2v
                        )
                        st_folium(mapa_q3, width=None, height=450, key="mapa_q3", returned_objects=[])

                    with col_m4:
                        ts = instantes[3]
                        n_v = len(datos_fcd.get(ts, []))
                        n_c = len([t for t in tuplas if t["t"] == ts])
                        n_c_v2v = len(set(
                            tuple(sorted([t["vehiculo_i"], t["vehiculo_j"]]))
                            for t in tuplas_v2v if t["t"] == ts
                        ))
                        st.markdown(f"**🗺️ {etiquetas[3]}** — t={ts:.0f}s — {n_v} veh, {n_c} V2I, {n_c_v2v} V2V")
                        mapa_q4 = crear_mapa_conectividad(
                            rsus_sim, edificios_sim, proy_sim,
                            tuplas, datos_fcd,
                            timestep_exacto=ts,
                            tuplas_v2v=tuplas_v2v
                        )
                        st_folium(mapa_q4, width=None, height=450, key="mapa_q4", returned_objects=[])



            else:
                st.info(
                    "📭 No se generaron tuplas de visibilidad. Posibles causas:\n"
                    "- El radio de cobertura OBU es demasiado pequeño\n"
                    "- Los vehículos no pasan cerca de los RSU\n"
                    "- Todos los edificios bloquean la línea de vista\n\n"
                    "Prueba aumentar el radio de cobertura OBU o el número de vehículos."
                )
