"""
Módulo de Estilos CSS Premium
=============================
Inyecta estilos personalizados en la aplicación Streamlit
para lograr una interfaz visual moderna y profesional.
"""

import streamlit as st

# Paleta de colores principal
COLORES = {
    "bg_primary": "#0a0e1a",
    "bg_secondary": "#111827",
    "bg_card": "rgba(17, 24, 39, 0.8)",
    "accent_cyan": "#06b6d4",
    "accent_blue": "#3b82f6",
    "accent_purple": "#8b5cf6",
    "accent_emerald": "#10b981",
    "accent_amber": "#f59e0b",
    "accent_red": "#ef4444",
    "text_primary": "#f1f5f9",
    "text_secondary": "#94a3b8",
    "border": "rgba(148, 163, 184, 0.12)",
}


def inyectar_css():
    """Inyecta los estilos CSS personalizados en la app de Streamlit."""
    st.markdown(f"""
    <style>
        /* ===== GOOGLE FONT ===== */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

        /* ===== RESET Y BASE ===== */
        .stApp {{
            font-family: 'Inter', sans-serif;
        }}
        
        .main .block-container {{
            padding-top: 1.5rem;
            padding-bottom: 2rem;
            max-width: 1300px;
        }}

        /* ===== ENCABEZADO HERO ===== */
        .hero-header {{
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 40%, #172554 100%);
            border: 1px solid rgba(139, 92, 246, 0.2);
            border-radius: 16px;
            padding: 2rem 2rem;
            margin-bottom: 1.5rem;
            position: relative;
            overflow: hidden;
        }}
        
        .hero-header::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 3px;
            background: linear-gradient(90deg, {COLORES["accent_cyan"]}, {COLORES["accent_purple"]}, {COLORES["accent_blue"]}, {COLORES["accent_cyan"]});
            background-size: 300% 100%;
            animation: gradient-slide 4s ease infinite;
        }}
        
        .hero-header::after {{
            content: '';
            position: absolute;
            top: -50%;
            right: -10%;
            width: 300px;
            height: 300px;
            background: radial-gradient(circle, rgba(139, 92, 246, 0.08) 0%, transparent 70%);
            pointer-events: none;
        }}
        
        @keyframes gradient-slide {{
            0%, 100% {{ background-position: 0% 50%; }}
            50% {{ background-position: 100% 50%; }}
        }}
        
        .hero-top {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 0.5rem;
        }}
        
        .hero-title {{
            font-size: 1.8rem;
            font-weight: 800;
            background: linear-gradient(135deg, {COLORES["accent_cyan"]}, {COLORES["accent_blue"]}, {COLORES["accent_purple"]});
            background-size: 200% 200%;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            animation: text-gradient 6s ease infinite;
            margin-bottom: 0.4rem;
            letter-spacing: -0.02em;
        }}
        
        @keyframes text-gradient {{
            0%, 100% {{ background-position: 0% 50%; }}
            50% {{ background-position: 100% 50%; }}
        }}
        
        .hero-subtitle {{
            color: {COLORES["text_secondary"]};
            font-size: 0.88rem;
            font-weight: 400;
            line-height: 1.6;
            max-width: 650px;
        }}
        
        .hero-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(6, 182, 212, 0.1);
            border: 1px solid rgba(6, 182, 212, 0.25);
            border-radius: 100px;
            padding: 4px 14px;
            font-size: 0.72rem;
            font-weight: 600;
            color: {COLORES["accent_cyan"]};
            margin-bottom: 0.8rem;
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }}
        
        .hero-tech-tags {{
            display: flex;
            gap: 8px;
            margin-top: 0.8rem;
            flex-wrap: wrap;
        }}
        
        .tech-tag {{
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 6px;
            padding: 3px 10px;
            font-size: 0.68rem;
            font-weight: 500;
            color: {COLORES["text_secondary"]};
            font-family: 'JetBrains Mono', monospace;
        }}

        /* ===== LABEL DEL MAPA ===== */
        .map-label {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 0.6rem;
        }}
        
        .map-label-text {{
            font-size: 0.78rem;
            font-weight: 600;
            color: {COLORES["text_secondary"]};
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }}
        
        .map-label-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: {COLORES["accent_emerald"]};
            animation: pulse-dot 2s ease infinite;
        }}
        
        @keyframes pulse-dot {{
            0%, 100% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.5; transform: scale(0.8); }}
        }}

        /* ===== TARJETAS GLASSMORPHISM ===== */
        .glass-card {{
            background: linear-gradient(145deg, rgba(17, 24, 39, 0.95), rgba(30, 27, 75, 0.5));
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid {COLORES["border"]};
            border-radius: 14px;
            padding: 1.25rem;
            margin-bottom: 0.8rem;
            transition: border-color 0.3s ease, box-shadow 0.3s ease;
        }}
        
        .glass-card:hover {{
            border-color: rgba(139, 92, 246, 0.25);
            box-shadow: 0 4px 20px rgba(139, 92, 246, 0.06);
        }}
        
        .card-title {{
            font-size: 0.75rem;
            font-weight: 600;
            color: {COLORES["text_secondary"]};
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 0.8rem;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .card-title .icon {{
            font-size: 1rem;
        }}

        /* ===== COORDENADAS DISPLAY ===== */
        .coord-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
        }}
        
        .coord-item {{
            background: rgba(6, 182, 212, 0.05);
            border: 1px solid rgba(6, 182, 212, 0.12);
            border-radius: 10px;
            padding: 10px 12px;
            transition: background 0.3s ease;
        }}
        
        .coord-item:hover {{
            background: rgba(6, 182, 212, 0.08);
        }}
        
        .coord-label {{
            font-size: 0.65rem;
            font-weight: 600;
            color: {COLORES["text_secondary"]};
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 3px;
        }}
        
        .coord-value {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.88rem;
            font-weight: 500;
            color: {COLORES["accent_cyan"]};
        }}

        /* ===== PANEL DE INSTRUCCIONES ===== */
        .step {{
            display: flex;
            align-items: flex-start;
            gap: 10px;
            margin-bottom: 10px;
        }}
        
        .step-num {{
            background: linear-gradient(135deg, {COLORES["accent_blue"]}, {COLORES["accent_purple"]});
            color: white;
            font-size: 0.65rem;
            font-weight: 700;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            margin-top: 2px;
        }}
        
        .step-text {{
            color: {COLORES["text_secondary"]};
            font-size: 0.8rem;
            line-height: 1.45;
        }}

        /* ===== BOTÓN PRINCIPAL ===== */
        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, {COLORES["accent_cyan"]} 0%, {COLORES["accent_blue"]} 50%, {COLORES["accent_purple"]} 100%) !important;
            background-size: 200% 200% !important;
            animation: btn-gradient 5s ease infinite !important;
            color: white !important;
            border: none !important;
            border-radius: 12px !important;
            padding: 0.75rem 2rem !important;
            font-weight: 700 !important;
            font-size: 0.95rem !important;
            font-family: 'Inter', sans-serif !important;
            letter-spacing: 0.02em !important;
            transition: box-shadow 0.4s ease, transform 0.2s ease !important;
            box-shadow: 0 4px 20px rgba(6, 182, 212, 0.3) !important;
        }}
        
        @keyframes btn-gradient {{
            0%, 100% {{ background-position: 0% 50%; }}
            50% {{ background-position: 100% 50%; }}
        }}
        
        .stButton > button[kind="primary"]:hover {{
            box-shadow: 0 8px 30px rgba(139, 92, 246, 0.4) !important;
            transform: translateY(-2px) !important;
        }}
        
        .stButton > button[kind="primary"]:active {{
            transform: translateY(0px) !important;
            box-shadow: 0 2px 10px rgba(6, 182, 212, 0.2) !important;
        }}

        /* ===== PIPELINE STEP (log del backend) ===== */
        .pipeline-step {{
            display: flex;
            align-items: center;
            gap: 14px;
            padding: 14px 18px;
            border-radius: 12px;
            margin-bottom: 8px;
            transition: all 0.3s ease;
        }}
        
        .pipeline-step.success {{
            background: rgba(16, 185, 129, 0.06);
            border: 1px solid rgba(16, 185, 129, 0.18);
        }}
        
        .pipeline-step.error {{
            background: rgba(239, 68, 68, 0.06);
            border: 1px solid rgba(239, 68, 68, 0.18);
        }}
        
        .pipeline-step.running {{
            background: rgba(245, 158, 11, 0.06);
            border: 1px solid rgba(245, 158, 11, 0.18);
            animation: pulse-border 2s ease infinite;
        }}
        
        @keyframes pulse-border {{
            0%, 100% {{ border-color: rgba(245, 158, 11, 0.18); }}
            50% {{ border-color: rgba(245, 158, 11, 0.35); }}
        }}
        
        .step-icon {{
            font-size: 1.2rem;
            flex-shrink: 0;
        }}
        
        .step-info {{
            flex-grow: 1;
        }}
        
        .step-name {{
            font-weight: 600;
            font-size: 0.88rem;
            color: {COLORES["text_primary"]};
        }}
        
        .step-detail {{
            font-size: 0.75rem;
            color: {COLORES["text_secondary"]};
            font-family: 'JetBrains Mono', monospace;
            margin-top: 2px;
            word-break: break-all;
        }}

        /* ===== RESUMEN FINAL ===== */
        .summary-card {{
            background: linear-gradient(145deg, rgba(16, 185, 129, 0.06), rgba(6, 182, 212, 0.04));
            border: 1px solid rgba(16, 185, 129, 0.18);
            border-radius: 14px;
            padding: 1.5rem;
            margin-top: 1rem;
            position: relative;
            overflow: hidden;
        }}
        
        .summary-card::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 2px;
            background: linear-gradient(90deg, {COLORES["accent_emerald"]}, {COLORES["accent_cyan"]});
        }}
        
        .summary-title {{
            font-size: 1.05rem;
            font-weight: 700;
            color: {COLORES["accent_emerald"]};
            margin-bottom: 0.8rem;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .summary-stats {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}
        
        .summary-stat {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 8px;
            padding: 8px 16px;
            font-size: 0.85rem;
            transition: background 0.3s;
        }}
        
        .summary-stat:hover {{
            background: rgba(255, 255, 255, 0.07);
        }}
        
        .stat-number {{
            font-family: 'JetBrains Mono', monospace;
            font-weight: 700;
            color: {COLORES["accent_cyan"]};
            font-size: 1.1rem;
        }}
        
        .stat-label {{
            color: {COLORES["text_secondary"]};
            font-size: 0.8rem;
        }}

        /* ===== ESTADO VACÍO ===== */
        .empty-state {{
            text-align: center;
            padding: 1.5rem 1rem;
            color: {COLORES["text_secondary"]};
        }}
        
        .empty-state .empty-icon {{
            font-size: 2.5rem;
            margin-bottom: 0.6rem;
            opacity: 0.4;
            display: block;
        }}
        
        .empty-state .msg {{
            font-size: 0.82rem;
            line-height: 1.5;
        }}

        /* ===== SECCIÓN DIVIDER ===== */
        .section-divider {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin: 1.5rem 0 1rem 0;
        }}
        
        .section-divider .line {{
            flex-grow: 1;
            height: 1px;
            background: linear-gradient(90deg, transparent, {COLORES["border"]}, transparent);
        }}
        
        .section-divider .label {{
            font-size: 0.78rem;
            font-weight: 600;
            color: {COLORES["text_secondary"]};
            text-transform: uppercase;
            letter-spacing: 0.1em;
            white-space: nowrap;
        }}

        /* ===== ARCHIVOS GENERADOS ===== */
        .file-list {{
            display: flex;
            flex-direction: column;
            gap: 6px;
            margin-top: 10px;
        }}
        
        .file-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 10px;
            background: rgba(255, 255, 255, 0.02);
            border-radius: 6px;
            font-size: 0.78rem;
        }}
        
        .file-icon {{ color: {COLORES["accent_amber"]}; }}
        .file-name {{
            font-family: 'JetBrains Mono', monospace;
            color: {COLORES["text_primary"]};
        }}
        .file-desc {{
            color: {COLORES["text_secondary"]};
            margin-left: auto;
            font-size: 0.72rem;
        }}
        
        /* ===== OCULTAR ELEMENTOS STREAMLIT ===== */
        #MainMenu {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}
        header {{ visibility: hidden; }}
        
        /* ===== AJUSTES AL MAPA DE FOLIUM ===== */
        iframe {{
            border-radius: 14px !important;
            border: 1px solid rgba(59, 130, 246, 0.2) !important;
            box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3) !important;
        }}
        
        /* ===== TOOLTIPS Y SPINNERS ===== */
        .stSpinner > div {{
            border-color: {COLORES["accent_cyan"]} !important;
        }}
    </style>
    """, unsafe_allow_html=True)


def renderizar_header():
    """Renderiza el encabezado hero de la aplicación."""
    st.markdown("""
    <div class="hero-header">
        <div class="hero-badge">🛰️ Módulo 1 — Simulación VANET</div>
        <div class="hero-title">Generador de Escenarios VANET</div>
        <div class="hero-subtitle">
            Selecciona un área geográfica en el mapa, descarga la topología desde OpenStreetMap
            y genera automáticamente la red vial, polígonos de edificios y rutas vehiculares
            usando las herramientas CLI de SUMO.
        </div>
        <div class="hero-tech-tags">
            <span class="tech-tag">OpenStreetMap</span>
            <span class="tech-tag">SUMO</span>
            <span class="tech-tag">netconvert</span>
            <span class="tech-tag">polyconvert</span>
            <span class="tech-tag">randomTrips</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


def renderizar_map_label():
    """Renderiza el label encima del mapa."""
    st.markdown("""
    <div class="map-label">
        <div class="map-label-dot"></div>
        <div class="map-label-text">Mapa Interactivo — Dibuja un rectángulo</div>
    </div>
    """, unsafe_allow_html=True)


def renderizar_instrucciones():
    """Renderiza el panel de instrucciones."""
    st.markdown("""
    <div class="glass-card">
        <div class="card-title"><span class="icon">📋</span> Cómo usar</div>
        <div class="step">
            <div class="step-num">1</div>
            <div class="step-text">Usa el ícono <strong>▭</strong> en la barra del mapa para dibujar un rectángulo sobre la zona que quieras simular.</div>
        </div>
        <div class="step">
            <div class="step-num">2</div>
            <div class="step-text">Las coordenadas del Bounding Box aparecerán abajo automáticamente.</div>
        </div>
        <div class="step">
            <div class="step-num">3</div>
            <div class="step-text">Presiona <strong>"Generar Escenario"</strong> para descargar OSM y ejecutar SUMO.</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def renderizar_coordenadas(min_lat, min_lon, max_lat, max_lon):
    """Renderiza las coordenadas seleccionadas con diseño premium."""
    st.markdown(f"""
    <div class="glass-card">
        <div class="card-title"><span class="icon">📍</span> Área Seleccionada</div>
        <div class="coord-grid">
            <div class="coord-item">
                <div class="coord-label">Lat Mín</div>
                <div class="coord-value">{min_lat:.6f}°</div>
            </div>
            <div class="coord-item">
                <div class="coord-label">Lon Mín</div>
                <div class="coord-value">{min_lon:.6f}°</div>
            </div>
            <div class="coord-item">
                <div class="coord-label">Lat Máx</div>
                <div class="coord-value">{max_lat:.6f}°</div>
            </div>
            <div class="coord-item">
                <div class="coord-label">Lon Máx</div>
                <div class="coord-value">{max_lon:.6f}°</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def renderizar_estado_vacio():
    """Muestra un estado vacío cuando no hay selección."""
    st.markdown("""
    <div class="glass-card">
        <div class="card-title"><span class="icon">📍</span> Área Seleccionada</div>
        <div class="empty-state">
            <span class="empty-icon">🗺️</span>
            <div class="msg">Dibuja un rectángulo en el mapa<br>para ver las coordenadas aquí</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def renderizar_paso_pipeline(nombre: str, exito: bool, detalle: str):
    """Renderiza un paso del pipeline con estado visual."""
    estado = "success" if exito else "error"
    icono = "✅" if exito else "❌"
    st.markdown(f"""
    <div class="pipeline-step {estado}">
        <div class="step-icon">{icono}</div>
        <div class="step-info">
            <div class="step-name">{nombre}</div>
            <div class="step-detail">{detalle}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def renderizar_divider(texto: str):
    """Renderiza un separador de sección con etiqueta."""
    st.markdown(f"""
    <div class="section-divider">
        <div class="line"></div>
        <div class="label">{texto}</div>
        <div class="line"></div>
    </div>
    """, unsafe_allow_html=True)


def renderizar_resumen(n_junctions: int, n_edificios: int):
    """Renderiza el resumen final del pipeline."""
    st.markdown(f"""
    <div class="summary-card">
        <div class="summary-title">🎉 Pipeline Completado</div>
        <div class="summary-stats">
            <span class="summary-stat">
                <span class="stat-number">{n_junctions}</span>
                <span class="stat-label">intersecciones</span>
            </span>
            <span class="summary-stat">
                <span class="stat-number">{n_edificios}</span>
                <span class="stat-label">edificios</span>
            </span>
        </div>
        <div class="file-list">
            <div class="file-item">
                <span class="file-icon">📄</span>
                <span class="file-name">junctions_limpias.json</span>
                <span class="file-desc">Intersecciones viales</span>
            </div>
            <div class="file-item">
                <span class="file-icon">📄</span>
                <span class="file-name">edificios_limpios.json</span>
                <span class="file-desc">Polígonos de edificios</span>
            </div>
            <div class="file-item">
                <span class="file-icon">📄</span>
                <span class="file-name">mapa.net.xml</span>
                <span class="file-desc">Red vial SUMO</span>
            </div>
            <div class="file-item">
                <span class="file-icon">📄</span>
                <span class="file-name">mapa.rou.xml</span>
                <span class="file-desc">Rutas vehiculares</span>
            </div>
        </div>
        <p style="color: #94a3b8; font-size: 0.78rem; margin-top: 12px; margin-bottom: 0;">
            📁 Todos los archivos están en la carpeta <code style="color: #06b6d4;">output/</code>
        </p>
    </div>
    """, unsafe_allow_html=True)
