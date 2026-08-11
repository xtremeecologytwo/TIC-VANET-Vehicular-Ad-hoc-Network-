"""
Módulo de Estilos — Consola científica/ingeniería (tema claro)
==============================================================
Inyecta el CSS de la interfaz SmartCityNet y expone helpers de render.

Dirección de diseño: "instrumento científico", no web decorativa. Fondo claro
frío, un único acento azul acero, verde reservado como color SEMÁNTICO para
"óptimo/desplegado", todos los datos en monoespaciada con cifras tabulares,
hairlines de plano de ingeniería y un motivo sutil de graticula cartográfica.
El tema claro se fija además en .streamlit/config.toml.
"""

import streamlit as st

# Paleta — claro científico/ingeniería
COLORES = {
    "ground": "#f6f7f9",
    "surface": "#ffffff",
    "surface_2": "#fbfcfd",
    "ink": "#0f1b2d",
    "muted": "#5b6b7f",
    "faint": "#8695a6",
    "line": "#e2e6ec",
    "line_strong": "#cfd6df",
    "accent": "#2557a7",
    "accent_deep": "#16407f",
    "accent_wash": "#eaf1fb",
    "ok": "#0f9d6b",
    "ok_wash": "#e6f6ee",
    "warn": "#b9770b",
    "warn_wash": "#fbf3e3",
    "crit": "#c0392b",
    "grid": "rgba(37,87,167,0.05)",
    # compatibilidad hacia atrás (nombres antiguos usados en HTML de app.py)
    "text_primary": "#0f1b2d",
    "text_secondary": "#5b6b7f",
    "accent_cyan": "#2557a7",
    "accent_blue": "#2557a7",
    "accent_purple": "#2557a7",
    "accent_emerald": "#0f9d6b",
    "accent_amber": "#b9770b",
    "accent_red": "#c0392b",
    "border": "#e2e6ec",
}

FONT_SANS = "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
FONT_MONO = "ui-monospace, 'Cascadia Code', 'SF Mono', 'JetBrains Mono', Consolas, monospace"


def inyectar_css():
    """Inyecta el CSS de la consola clara en la app de Streamlit."""
    C = COLORES
    st.markdown(f"""
    <style>
        /* ===== BASE ===== */
        .stApp {{ background: {C['ground']}; }}
        html, body, [class*="css"] {{ font-family: {FONT_SANS}; }}
        .main .block-container {{
            padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1200px;
        }}
        .mono {{ font-family: {FONT_MONO}; font-variant-numeric: tabular-nums; }}

        /* ===== OCULTAR CHROME DE STREAMLIT ===== */
        #MainMenu {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}
        header[data-testid="stHeader"] {{ background: transparent; height: 0; }}

        /* ===== ENCABEZADO (hero con graticula) ===== */
        .hero-header {{
            position: relative; overflow: hidden;
            background: {C['surface']};
            border: 1px solid {C['line']};
            border-radius: 12px;
            padding: 1.4rem 1.6rem;
            margin-bottom: 1rem;
            box-shadow: 0 1px 2px rgba(15,27,45,0.04), 0 6px 18px rgba(15,27,45,0.05);
        }}
        .hero-header::before {{
            content: ""; position: absolute; inset: 0; pointer-events: none;
            background-image:
                linear-gradient({C['grid']} 1px, transparent 1px),
                linear-gradient(90deg, {C['grid']} 1px, transparent 1px);
            background-size: 34px 34px;
            -webkit-mask-image: linear-gradient(105deg, #000 0%, transparent 62%);
            mask-image: linear-gradient(105deg, #000 0%, transparent 62%);
        }}
        .hero-in {{ position: relative; }}
        .hero-eyebrow {{
            font-family: {FONT_MONO}; font-size: 0.68rem; letter-spacing: 0.14em;
            text-transform: uppercase; color: {C['faint']};
        }}
        .hero-title {{
            font-size: 1.55rem; font-weight: 700; color: {C['ink']};
            letter-spacing: -0.02em; margin: 0.35rem 0 0.3rem; line-height: 1.15;
        }}
        .hero-subtitle {{
            color: {C['muted']}; font-size: 0.86rem; line-height: 1.55; max-width: 72ch;
        }}
        .hero-tech-tags {{ display: flex; gap: 7px; margin-top: 0.85rem; flex-wrap: wrap; }}
        .tech-tag {{
            background: {C['surface_2']}; border: 1px solid {C['line']}; border-radius: 5px;
            padding: 3px 9px; font-size: 0.68rem; color: {C['muted']}; font-family: {FONT_MONO};
        }}
        /* badge antiguo → chip discreto */
        .hero-badge {{
            display: inline-flex; align-items: center; gap: 6px;
            background: {C['accent_wash']}; border: 1px solid {C['line']};
            border-radius: 6px; padding: 3px 10px; font-size: 0.68rem; font-weight: 600;
            color: {C['accent']}; font-family: {FONT_MONO};
            letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 0.5rem;
        }}

        /* ===== STEPPER DE MÓDULOS M1 · M2 · M3 ===== */
        .module-stepper {{
            display: flex; border: 1px solid {C['line']}; border-radius: 12px;
            overflow: hidden; background: {C['surface']}; margin-bottom: 1.1rem;
            box-shadow: 0 1px 2px rgba(15,27,45,0.04);
        }}
        .ms-step {{
            flex: 1; display: flex; align-items: center; gap: 11px;
            padding: 12px 16px; border-right: 1px solid {C['line']};
        }}
        .ms-step:last-child {{ border-right: 0; }}
        .ms-n {{
            font-family: {FONT_MONO}; font-size: 0.72rem; font-weight: 700;
            width: 26px; height: 26px; border-radius: 6px; display: flex;
            align-items: center; justify-content: center; flex-shrink: 0;
            background: {C['accent_wash']}; color: {C['accent']};
        }}
        .ms-step.done .ms-n {{ background: {C['ok_wash']}; color: {C['ok']}; }}
        .ms-step.active .ms-n {{ background: {C['accent']}; color: #fff; }}
        .ms-t {{ font-size: 0.78rem; font-weight: 600; color: {C['ink']}; }}
        .ms-s {{ font-size: 0.68rem; color: {C['faint']}; font-family: {FONT_MONO}; }}

        /* ===== LABEL DEL MAPA ===== */
        .map-label {{ display: flex; align-items: center; gap: 8px; margin-bottom: 0.5rem; }}
        .map-label-text {{
            font-size: 0.72rem; font-weight: 600; color: {C['muted']};
            text-transform: uppercase; letter-spacing: 0.08em; font-family: {FONT_MONO};
        }}
        .map-label-dot {{ width: 8px; height: 8px; border-radius: 50%; background: {C['ok']}; }}

        /* ===== TARJETAS ===== */
        .glass-card {{
            background: {C['surface']}; border: 1px solid {C['line']};
            border-radius: 10px; padding: 1.1rem 1.15rem; margin-bottom: 0.7rem;
            box-shadow: 0 1px 2px rgba(15,27,45,0.04);
        }}
        .card-title {{
            font-size: 0.7rem; font-weight: 600; color: {C['muted']};
            text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.7rem;
            display: flex; align-items: center; gap: 8px; font-family: {FONT_MONO};
        }}
        .card-title .icon {{ font-size: 0.95rem; }}

        /* ===== COORDENADAS ===== */
        .coord-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
        .coord-item {{
            background: {C['surface_2']}; border: 1px solid {C['line']};
            border-radius: 8px; padding: 9px 11px;
        }}
        .coord-label {{
            font-size: 0.62rem; font-weight: 600; color: {C['faint']};
            text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 3px;
            font-family: {FONT_MONO};
        }}
        .coord-value {{
            font-family: {FONT_MONO}; font-size: 0.85rem; font-weight: 600;
            color: {C['accent']}; font-variant-numeric: tabular-nums;
        }}

        /* ===== INSTRUCCIONES (pasos) ===== */
        .step {{ display: flex; align-items: flex-start; gap: 10px; margin-bottom: 9px; }}
        .step-num {{
            background: {C['accent']}; color: #fff; font-size: 0.62rem; font-weight: 700;
            width: 19px; height: 19px; border-radius: 5px; display: flex;
            align-items: center; justify-content: center; flex-shrink: 0; margin-top: 1px;
            font-family: {FONT_MONO};
        }}
        .step-text {{ color: {C['muted']}; font-size: 0.8rem; line-height: 1.45; }}
        .step-text strong {{ color: {C['ink']}; }}

        /* ===== BOTONES ===== */
        .stButton > button {{
            border-radius: 8px !important; font-weight: 600 !important;
            font-family: {FONT_SANS} !important; transition: background .15s, border-color .15s !important;
        }}
        .stButton > button[kind="primary"] {{
            background: {C['accent']} !important; color: #fff !important;
            border: 1px solid {C['accent']} !important; padding: 0.6rem 1.4rem !important;
            font-size: 0.9rem !important; box-shadow: none !important; letter-spacing: 0.01em !important;
        }}
        .stButton > button[kind="primary"]:hover {{
            background: {C['accent_deep']} !important; border-color: {C['accent_deep']} !important;
        }}
        .stButton > button[kind="secondary"] {{
            background: {C['surface']} !important; color: {C['ink']} !important;
            border: 1px solid {C['line_strong']} !important;
        }}
        .stButton > button[kind="secondary"]:hover {{
            border-color: {C['accent']} !important; color: {C['accent']} !important;
        }}

        /* ===== LOG DEL PIPELINE ===== */
        .pipeline-step {{
            display: flex; align-items: center; gap: 12px; padding: 11px 15px;
            border-radius: 9px; margin-bottom: 7px; border: 1px solid {C['line']};
            background: {C['surface']};
        }}
        .pipeline-step.success {{ background: {C['ok_wash']}; border-color: rgba(15,157,107,0.28); }}
        .pipeline-step.error {{ background: #fdecea; border-color: rgba(192,57,43,0.28); }}
        .pipeline-step.running {{ background: {C['warn_wash']}; border-color: rgba(185,119,11,0.3); }}
        .step-icon {{ font-size: 1.05rem; flex-shrink: 0; }}
        .step-info {{ flex-grow: 1; }}
        .step-name {{ font-weight: 600; font-size: 0.85rem; color: {C['ink']}; }}
        .step-detail {{
            font-size: 0.72rem; color: {C['muted']}; font-family: {FONT_MONO};
            margin-top: 2px; word-break: break-all;
        }}

        /* ===== RESUMEN ===== */
        .summary-card {{
            background: {C['ok_wash']}; border: 1px solid rgba(15,157,107,0.28);
            border-radius: 10px; padding: 1.2rem 1.3rem; margin-top: 0.9rem;
        }}
        .summary-title {{
            font-size: 0.98rem; font-weight: 700; color: {C['ok']}; margin-bottom: 0.7rem;
            display: flex; align-items: center; gap: 8px;
        }}
        .summary-stats {{ display: flex; gap: 9px; flex-wrap: wrap; }}
        .summary-stat {{
            display: inline-flex; align-items: center; gap: 6px; background: {C['surface']};
            border: 1px solid {C['line']}; border-radius: 7px; padding: 7px 14px; font-size: 0.82rem;
        }}
        .stat-number {{
            font-family: {FONT_MONO}; font-weight: 700; color: {C['accent']}; font-size: 1.05rem;
            font-variant-numeric: tabular-nums;
        }}
        .stat-label {{ color: {C['muted']}; font-size: 0.78rem; }}
        .file-list {{ display: flex; flex-direction: column; gap: 5px; margin-top: 10px; }}
        .file-item {{
            display: flex; align-items: center; gap: 8px; padding: 6px 10px;
            background: {C['surface']}; border: 1px solid {C['line']}; border-radius: 6px; font-size: 0.76rem;
        }}
        .file-icon {{ color: {C['warn']}; }}
        .file-name {{ font-family: {FONT_MONO}; color: {C['ink']}; }}
        .file-desc {{ color: {C['muted']}; margin-left: auto; font-size: 0.7rem; }}

        /* ===== ESTADO VACÍO ===== */
        .empty-state {{ text-align: center; padding: 1.3rem 1rem; color: {C['faint']}; }}
        .empty-state .empty-icon {{ font-size: 2.2rem; margin-bottom: 0.5rem; opacity: 0.5; display: block; }}
        .empty-state .msg {{ font-size: 0.8rem; line-height: 1.5; }}

        /* ===== DIVIDER DE SECCIÓN ===== */
        .section-divider {{ display: flex; align-items: center; gap: 12px; margin: 1.6rem 0 1rem; }}
        .section-divider .line {{ flex-grow: 1; height: 1px; background: {C['line']}; }}
        .section-divider .label {{
            font-size: 0.74rem; font-weight: 700; color: {C['accent']};
            letter-spacing: 0.06em; white-space: nowrap; font-family: {FONT_MONO};
            background: {C['accent_wash']}; padding: 3px 10px; border-radius: 6px;
        }}

        /* ===== TILES DE ESTADÍSTICAS ===== */
        .sim-stats-grid {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 11px; margin-bottom: 1rem;
        }}
        .sim-stat-card {{
            position: relative; background: {C['surface']}; border: 1px solid {C['line']};
            border-radius: 8px; padding: 14px 15px 14px 18px;
            box-shadow: 0 1px 2px rgba(15,27,45,0.04);
        }}
        .sim-stat-card::before {{
            content: ""; position: absolute; left: 0; top: 12px; bottom: 12px; width: 3px;
            border-radius: 3px; background: {C['accent']};
        }}
        .sim-stat-value {{
            font-family: {FONT_MONO}; font-size: 1.35rem; font-weight: 700; color: {C['ink']};
            font-variant-numeric: tabular-nums; letter-spacing: -0.01em;
        }}
        .sim-stat-label {{
            font-size: 0.66rem; font-weight: 600; color: {C['faint']};
            text-transform: uppercase; letter-spacing: 0.06em; margin-top: 3px;
        }}
        .sim-stat-card.purple::before {{ background: {C['accent']}; }}
        .sim-stat-card.emerald::before {{ background: {C['ok']}; }}
        .sim-stat-card.amber::before {{ background: {C['warn']}; }}
        .sim-stat-card.red::before {{ background: {C['crit']}; }}
        .sim-stat-card.emerald .sim-stat-value {{ color: {C['ok']}; }}

        /* ===== CABECERA DE TABLA DE TUPLAS ===== */
        .tupla-tabla-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 0.6rem; }}
        .tupla-tabla-header .titulo {{ font-size: 0.88rem; font-weight: 600; color: {C['ink']}; }}
        .tupla-tabla-header .badge {{
            background: {C['accent_wash']}; border: 1px solid {C['line']}; border-radius: 6px;
            padding: 2px 9px; font-size: 0.68rem; font-weight: 600; color: {C['accent']};
            font-family: {FONT_MONO};
        }}

        /* ===== LEYENDA ===== */
        .v2i-legend {{
            display: flex; flex-wrap: wrap; gap: 14px; align-items: center; padding: 8px 13px;
            background: {C['surface_2']}; border: 1px solid {C['line']}; border-radius: 8px;
            margin-bottom: 0.8rem; font-size: 0.74rem; color: {C['muted']};
        }}
        .v2i-legend-item {{ display: flex; align-items: center; gap: 5px; }}
        .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
        .legend-line {{ width: 18px; height: 3px; border-radius: 2px; flex-shrink: 0; }}

        /* ===== TEXTO DESCRIPTIVO REUTILIZABLE ===== */
        .desc {{ font-size: 0.82rem; color: {C['muted']}; line-height: 1.55; }}
        .desc strong {{ color: {C['ink']}; }}

        /* ===== WIDGETS NATIVOS DE STREAMLIT ===== */
        [data-testid="stMetric"] {{
            background: {C['surface']}; border: 1px solid {C['line']}; border-radius: 8px;
            padding: 13px 16px; box-shadow: 0 1px 2px rgba(15,27,45,0.04);
        }}
        [data-testid="stMetricValue"] {{
            font-family: {FONT_MONO}; font-variant-numeric: tabular-nums;
            font-weight: 700; color: {C['ink']};
        }}
        [data-testid="stMetricLabel"] {{ color: {C['muted']}; }}
        .stTabs [data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 1px solid {C['line']}; }}
        .stTabs [data-baseweb="tab"] {{
            font-size: 0.82rem; font-weight: 600; color: {C['muted']}; padding: 8px 14px;
        }}
        .stTabs [aria-selected="true"] {{ color: {C['accent']}; }}
        [data-testid="stExpander"] {{
            border: 1px solid {C['line']} !important; border-radius: 9px !important;
            background: {C['surface']} !important;
        }}
        [data-testid="stExpander"] summary {{ font-size: 0.82rem; font-weight: 600; color: {C['ink']}; }}
        .stSpinner > div {{ border-top-color: {C['accent']} !important; }}
        .stSlider [data-baseweb="slider"] [role="slider"] {{ border-color: {C['accent']} !important; }}
        code {{ color: {C['accent']}; background: {C['accent_wash']}; padding: 1px 5px; border-radius: 4px; }}

        /* ===== MAPA DE FOLIUM ENMARCADO ===== */
        iframe {{
            border-radius: 10px !important; border: 1px solid {C['line_strong']} !important;
            box-shadow: 0 1px 2px rgba(15,27,45,0.05), 0 8px 24px rgba(15,27,45,0.06) !important;
        }}
    </style>
    """, unsafe_allow_html=True)


def renderizar_header():
    """Encabezado con eyebrow, título y chips de tecnología."""
    st.markdown("""
    <div class="hero-header">
      <div class="hero-in">
        <div class="hero-eyebrow">Redes vehiculares ad-hoc · EPN · TIC</div>
        <div class="hero-title">SmartCityNet — Consola de simulación y optimización VANET</div>
        <div class="hero-subtitle">
            Selecciona un área en el mapa, genera la red vial con SUMO, simula la conectividad
            V2V/V2I con línea de vista y resuelve el despliegue de RSU con CPLEX — todo en un mismo flujo.
        </div>
        <div class="hero-tech-tags">
            <span class="tech-tag">OpenStreetMap</span>
            <span class="tech-tag">SUMO</span>
            <span class="tech-tag">Line of Sight</span>
            <span class="tech-tag">Multisalto</span>
            <span class="tech-tag">docplex · CPLEX</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def renderizar_stepper(activo: int = 1):
    """
    Renderiza el stepper de módulos M1 → M2 → M3.

    Parámetros:
        activo: módulo actualmente en curso (1, 2 o 3). Los anteriores se
                marcan como completados (verde) y el activo en azul sólido.
    """
    pasos = [
        ("M1", "Escenario", "OSM → SUMO"),
        ("M2", "Conectividad", "V2V · V2I · multisalto"),
        ("M3", "Optimización", "despliegue de RSU"),
    ]
    html = ['<div class="module-stepper">']
    for i, (n, t, s) in enumerate(pasos, start=1):
        cls = "done" if i < activo else ("active" if i == activo else "")
        html.append(
            f'<div class="ms-step {cls}"><span class="ms-n">{n}</span>'
            f'<div><div class="ms-t">{t}</div><div class="ms-s">{s}</div></div></div>'
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def renderizar_map_label():
    """Label sobre el mapa interactivo."""
    st.markdown("""
    <div class="map-label">
        <div class="map-label-dot"></div>
        <div class="map-label-text">Mapa interactivo — dibuja un rectángulo</div>
    </div>
    """, unsafe_allow_html=True)


def renderizar_instrucciones():
    """Panel de instrucciones de uso."""
    st.markdown("""
    <div class="glass-card">
        <div class="card-title"><span class="icon">▤</span> Cómo usar</div>
        <div class="step">
            <div class="step-num">1</div>
            <div class="step-text">Usa el ícono <strong>▭</strong> en la barra del mapa para dibujar un rectángulo sobre la zona a simular.</div>
        </div>
        <div class="step">
            <div class="step-num">2</div>
            <div class="step-text">Las coordenadas del <em>bounding box</em> aparecerán abajo automáticamente.</div>
        </div>
        <div class="step">
            <div class="step-num">3</div>
            <div class="step-text">Presiona <strong>"Generar escenario"</strong> para descargar OSM y ejecutar SUMO.</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def renderizar_coordenadas(min_lat, min_lon, max_lat, max_lon):
    """Coordenadas del área seleccionada."""
    st.markdown(f"""
    <div class="glass-card">
        <div class="card-title"><span class="icon">◧</span> Área seleccionada</div>
        <div class="coord-grid">
            <div class="coord-item"><div class="coord-label">Lat mín</div><div class="coord-value">{min_lat:.6f}°</div></div>
            <div class="coord-item"><div class="coord-label">Lon mín</div><div class="coord-value">{min_lon:.6f}°</div></div>
            <div class="coord-item"><div class="coord-label">Lat máx</div><div class="coord-value">{max_lat:.6f}°</div></div>
            <div class="coord-item"><div class="coord-label">Lon máx</div><div class="coord-value">{max_lon:.6f}°</div></div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def renderizar_estado_vacio():
    """Estado vacío cuando no hay selección."""
    st.markdown("""
    <div class="glass-card">
        <div class="card-title"><span class="icon">◧</span> Área seleccionada</div>
        <div class="empty-state">
            <span class="empty-icon">▢</span>
            <div class="msg">Dibuja un rectángulo en el mapa<br>para ver las coordenadas aquí</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def renderizar_paso_pipeline(nombre: str, exito: bool, detalle: str):
    """Un paso del pipeline con estado visual."""
    estado = "success" if exito else "error"
    icono = "✓" if exito else "✕"
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
    """Separador de sección con etiqueta."""
    st.markdown(f"""
    <div class="section-divider">
        <div class="label">{texto}</div>
        <div class="line"></div>
    </div>
    """, unsafe_allow_html=True)


def renderizar_resumen(n_junctions: int, n_edificios: int):
    """Resumen final del pipeline del Módulo 1."""
    st.markdown(f"""
    <div class="summary-card">
        <div class="summary-title">✓ Escenario generado</div>
        <div class="summary-stats">
            <span class="summary-stat"><span class="stat-number">{n_junctions}</span><span class="stat-label">intersecciones</span></span>
            <span class="summary-stat"><span class="stat-number">{n_edificios}</span><span class="stat-label">edificios</span></span>
        </div>
        <div class="file-list">
            <div class="file-item"><span class="file-icon">▪</span><span class="file-name">junctions_limpias.json</span><span class="file-desc">Intersecciones viales</span></div>
            <div class="file-item"><span class="file-icon">▪</span><span class="file-name">edificios_limpios.json</span><span class="file-desc">Polígonos de edificios</span></div>
            <div class="file-item"><span class="file-icon">▪</span><span class="file-name">mapa.net.xml</span><span class="file-desc">Red vial SUMO</span></div>
            <div class="file-item"><span class="file-icon">▪</span><span class="file-name">mapa.rou.xml</span><span class="file-desc">Rutas vehiculares</span></div>
        </div>
        <p class="desc" style="margin-top: 12px; margin-bottom: 0;">
            Todos los archivos quedan en la carpeta <code>output/</code>
        </p>
    </div>
    """, unsafe_allow_html=True)


def renderizar_simulacion_stats(estadisticas: dict):
    """Tiles de estadísticas de la simulación V2I."""
    total_tuplas = estadisticas.get("total_tuplas", 0)
    total_ts = estadisticas.get("total_timesteps", 0)
    radio_obu = estadisticas.get("radio_obu", 0)
    num_rsus = len(estadisticas.get("resumen_por_rsu", {}))

    st.markdown(f"""
    <div class="sim-stats-grid">
        <div class="sim-stat-card"><div class="sim-stat-value">{total_tuplas:,}</div><div class="sim-stat-label">Tuplas V2I (LoS)</div></div>
        <div class="sim-stat-card purple"><div class="sim-stat-value">{total_ts}</div><div class="sim-stat-label">Snapshots</div></div>
        <div class="sim-stat-card emerald"><div class="sim-stat-value">{num_rsus}</div><div class="sim-stat-label">RSU activos</div></div>
        <div class="sim-stat-card amber"><div class="sim-stat-value">{radio_obu}m</div><div class="sim-stat-label">Radio OBU</div></div>
    </div>
    """, unsafe_allow_html=True)


def renderizar_v2v_stats(estadisticas_v2v: dict):
    """Tiles de estadísticas de conectividad V2V."""
    total_tuplas = estadisticas_v2v.get("total_tuplas_v2v", 0)
    pares_rango = estadisticas_v2v.get("total_pares_en_rango", 0)
    bidireccional = estadisticas_v2v.get("bidireccional", True)
    num_vehiculos = len(estadisticas_v2v.get("resumen_por_vehiculo", {}))
    bidi_label = "Sí" if bidireccional else "No"

    st.markdown(f"""
    <div class="sim-stats-grid">
        <div class="sim-stat-card"><div class="sim-stat-value">{total_tuplas:,}</div><div class="sim-stat-label">Tuplas V2V</div></div>
        <div class="sim-stat-card purple"><div class="sim-stat-value">{num_vehiculos}</div><div class="sim-stat-label">Vehículos conectados</div></div>
        <div class="sim-stat-card emerald"><div class="sim-stat-value">{pares_rango:,}</div><div class="sim-stat-label">Pares en rango</div></div>
        <div class="sim-stat-card amber"><div class="sim-stat-value">{bidi_label}</div><div class="sim-stat-label">Bidireccional</div></div>
    </div>
    """, unsafe_allow_html=True)
