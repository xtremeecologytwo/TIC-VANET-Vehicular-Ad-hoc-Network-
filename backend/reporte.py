"""
reporte.py — de la base de datos a las figuras de la tesis
==========================================================
`scn.py exportar --campana X`  -> CSV con una fila por corrida (para Power BI,
                                  Excel o lo que se quiera).
`scn.py reporte  --campana X`  -> figuras (PDF vectorial para LaTeX + PNG) y
                                  tablas .tex, en datos/reportes/X/.

Todo se lee del catálogo (datos/catalogo.sqlite): un solo comando regenera
todas las figuras cuando cambian los datos. Cada figura responde UNA pregunta
y lo dice en su título.

Si la campaña tiene los factores `carga` o `presupuesto`, las figuras de
siempre se dibujan con su nivel base (carga x1, presupuesto libre) y se añaden
las de esos factores.

Con `--semillas`, `--campana` es una FAMILIA (una campaña con `semillas` en su
YAML, que se ejecutó como `<familia>_s<semilla>`): las mismas figuras y tablas
con la media de las semillas de cada punto y su intervalo de confianza del
95 % (barras de error), en datos/reportes/<familia>_semillas/, y dos CSV: todas
las corridas y el resumen por punto.
"""

import json
import os
import sqlite3

import numpy as np
import pandas as pd

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOGO = os.path.join(_RAIZ, "datos", "catalogo.sqlite")
DIR_REPORTES = os.path.join(_RAIZ, "datos", "reportes")

COLUMNAS_FACTORES = ["vehiculos", "filtrado", "gmin", "rho", "fisica", "tasa_mbps",
                     "criterio", "radio_m", "P", "cap_kbps", "carga_kbps", "H",
                     "carga_mult", "presupuesto", "max_rsu",
                     "duracion_min", "muestreo_min", "semilla"]


def tabla(campana: str, ruta: str = CATALOGO) -> pd.DataFrame:
    """Una fila por corrida de la campaña, con factores, métricas y despliegue."""
    con = sqlite3.connect(ruta)
    q = """
    SELECT c.uuid, c.campana, c.punto, c.estado, c.error, c.inicio, c.fin, c.factores,
           c.carpeta, a.nombre AS area, cd.n AS Y, r.n_instantes, r.N, r.K, r.cvr, r.q_reach, r.k_por_n,
           r.m1, r.m2, r.m3, r.t_links_s, r.t_hops_s,
           d.n_rsu, d.cobertura_pct, d.conectados, d.desconectados, d.directos,
           d.multisalto, d.status, d.objetivos, d.segundos_solver, d.segundos_total,
           d.limite_tiempo, d.topes, d.origen, d.ids AS rsu_ids
    FROM corrida c
    JOIN candidatas cd ON cd.id = c.candidatas_id
    JOIN movilidad m ON m.id = c.movilidad_id
    JOIN red rd ON rd.id = m.red_id
    JOIN area a ON a.id = rd.area_id
    LEFT JOIN resultado r ON r.corrida_id = c.id
    LEFT JOIN despliegue d ON d.corrida_id = c.id
    WHERE c.campana = ?
    ORDER BY c.id"""
    df = pd.read_sql_query(q, con, params=(campana,))
    con.close()
    if df.empty:
        return df
    fac = df["factores"].apply(lambda s: json.loads(s) if s else {})
    for col in COLUMNAS_FACTORES:
        df[col] = fac.apply(lambda d: d.get(col))
    df["P"] = df["P"].apply(lambda p: "/".join(f"{x:.3f}" for x in p) if p else "1..H")
    obj = df["objetivos"].apply(lambda s: json.loads(s) if s else [None] * 3)
    df["f1_desconectada"] = obj.apply(lambda o: o[0] if o else None)
    df["f2_instalacion"] = obj.apply(lambda o: o[1] if o else None)
    df["f3_saltos"] = obj.apply(lambda o: o[2] if o else None)
    df["huella"] = fac.apply(lambda d: d.get("huella"))
    s = df["status"].fillna("").str.lower()
    # Sin solución útil: M3 terminó sin despliegue (error, interrupción, nivel 1
    # sin cobertura). Con el código actual esas corridas quedan "fallidas"; esto
    # protege de las antiguas, que se guardaban como 0 RSU.
    df["sin_solucion"] = (df["status"].notna() & df["cobertura_pct"].isna()
                          & ~s.str.contains("sin candidatas")) | s.str.contains("sin cobertura")
    df.loc[df["sin_solucion"], ["n_rsu", "cobertura_pct"]] = np.nan
    df["cortado"] = s.str.contains("non-optimal|time limit") & ~df["sin_solucion"]
    df["optimo"] = s.str.contains("optimal") & ~s.str.contains("non-optimal") & ~df["sin_solucion"]
    df["frac_multisalto"] = df["multisalto"] / df["conectados"].replace(0, np.nan)
    # Uso medio de la capacidad de las RSU encendidas: el nivel 3 del
    # lexicográfico, sum(Rts * P[h] * L), es exactamente la carga que reciben
    # las RSU reales sumada en todos los instantes (el lado izquierdo de la
    # Ec. 4); dividido entre RSU x instantes x Cap da la fracción media usada.
    cap = pd.to_numeric(df["cap_kbps"], errors="coerce")
    df["uso_capacidad"] = (pd.to_numeric(df["f3_saltos"], errors="coerce")
                           / (df["n_rsu"].replace(0, np.nan) * df["n_instantes"] * cap))
    df["reutilizado"] = df["origen"].notna()
    # Si hay repeticiones del mismo punto (reintentos), vale la última hecha.
    df = df[df["estado"] == "hecha"].drop_duplicates("punto", keep="last")
    # Solo los puntos que define el YAML de la campaña (si lo hay): una corrida
    # suelta con el mismo --campana no debe colarse en las figuras.
    spec = _spec(campana, ruta)
    if spec is not None:
        try:
            from .campana import puntos as _puntos, validar_spec
            validos = {p["punto"] for p in _puntos(validar_spec(dict(spec)))}
            df = df[df["punto"].isin(validos)]
        except Exception:  # noqa: BLE001 - si el spec no se puede expandir, no se filtra
            pass
    return df.drop(columns=["factores", "objetivos"])


def _spec(campana: str, ruta: str = CATALOGO) -> dict | None:
    con = sqlite3.connect(ruta)
    try:
        fila = con.execute("SELECT spec FROM campana WHERE nombre = ?", (campana,)).fetchone()
    except sqlite3.OperationalError:
        fila = None
    con.close()
    return json.loads(fila[0]) if fila else None


def avisos_homogeneidad(df: pd.DataFrame, salvo=()) -> list[str]:
    """Lo que haría engañosas las figuras: puntos de configuraciones distintas mezclados."""
    avisos = []
    for col, nombre in (("area", "áreas"), ("semilla", "semillas"), ("duracion_min", "duraciones"),
                        ("muestreo_min", "muestreos"), ("huella", "configuraciones fijas")):
        if col in salvo:
            continue
        vals = df[col].dropna().unique()
        if len(vals) > 1:
            avisos.append(f"la campaña mezcla {len(vals)} {nombre}: {', '.join(map(str, vals))}")
    n_sin = int(df["sin_solucion"].sum())
    if n_sin:
        avisos.append(f"{n_sin} punto(s) sin solución útil de M3 (no se dibujan)")
    return avisos


def exportar(campana: str, destino: str | None = None) -> str:
    df = tabla(campana)
    if df.empty:
        raise ValueError(f"la campaña '{campana}' no tiene corridas hechas")
    destino = os.path.abspath(destino or os.path.join(DIR_REPORTES, campana, f"{campana}.csv"))
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    # Formato de Excel en español (separador ';' y coma decimal): con ',' y '.'
    # cada fila caía entera en una columna y '89.04' se leía como 8 904. Power BI
    # lo importa bien con la configuración regional "Español". utf-8-sig: tildes.
    df.to_csv(destino, index=False, sep=";", decimal=",", encoding="utf-8-sig")
    return destino


# ======================================================================
# Varias semillas
# ======================================================================

# Lo que se promedia entre semillas; las demás columnas son factores del punto
METRICAS = ["Y", "n_instantes", "N", "K", "cvr", "q_reach", "k_por_n", "n_rsu", "cobertura_pct",
            "conectados", "desconectados", "directos", "multisalto", "frac_multisalto",
            "uso_capacidad", "f1_desconectada", "f2_instalacion", "f3_saltos",
            "segundos_solver", "t_links_s", "t_hops_s"]

# Cuantil 0,975 de la t de Student por grados de libertad (no hay scipy en el entorno)
_T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
         9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120,
         17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 25: 2.060, 30: 2.042, 40: 2.021,
         60: 2.000, 120: 1.980}


def t975(gl: int) -> float:
    """t(0,975; gl): el de la tabla con gl igual o inmediatamente menor (conservador); 1,96 por encima de 120."""
    if gl < 1:
        return float("nan")
    if gl > 120:
        return 1.96
    return _T975[max(k for k in _T975 if k <= gl)]


def campanas_familia(familia: str, ruta: str = CATALOGO) -> list[tuple[str, int]]:
    """(campaña, semilla) de cada semilla de una familia, ordenadas por semilla."""
    con = sqlite3.connect(ruta)
    try:
        filas = con.execute("SELECT nombre, spec FROM campana").fetchall()
    except sqlite3.OperationalError:
        filas = []
    con.close()
    salida = []
    for nombre, texto in filas:
        spec = json.loads(texto) if texto else {}
        if spec.get("familia") == familia:
            salida.append((nombre, int(spec["semilla"])))
    return sorted(salida, key=lambda c: c[1])


def tabla_semillas(familia: str, ruta: str = CATALOGO) -> pd.DataFrame:
    """Una fila por corrida, de todas las semillas de la familia."""
    partes = [tabla(c, ruta) for c, _ in campanas_familia(familia, ruta)]
    partes = [p for p in partes if not p.empty]
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


def resumir_semillas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Una fila por punto con la media de cada métrica entre semillas (con el
    nombre de siempre, para que sirvan las mismas figuras), su desviación
    (`_sd`), cuántas semillas entran (`_n`) y el semiancho del intervalo de
    confianza del 95 % (`_ic95`, t de Student). Un punto cuenta como cortado
    si lo fue en alguna semilla; las semillas sin solución no entran en la media.
    """
    g = df.groupby("punto", sort=False)
    constantes = [c for c in ["area", *COLUMNAS_FACTORES] if c in df.columns and c != "semilla"]
    cols = {}
    for m in METRICAS:
        if m not in df.columns:
            continue
        v = pd.to_numeric(df[m], errors="coerce").groupby(df["punto"], sort=False)
        n = v.count()
        sd = v.std(ddof=1)
        cols[m] = v.mean()
        cols[f"{m}_sd"] = sd
        cols[f"{m}_n"] = n
        cols[f"{m}_ic95"] = sd / np.sqrt(n) * n.map(lambda k: t975(int(k) - 1))
    cols["n_semillas"] = g["semilla"].nunique()
    cols["semillas"] = g["semilla"].apply(lambda s: ",".join(str(int(x)) for x in sorted(s.dropna().unique())))
    cols["n_cortados"] = g["cortado"].sum().astype(int)
    cols["cortado"] = cols["n_cortados"] > 0
    cols["sin_solucion"] = g["sin_solucion"].all()
    out = pd.concat([g[constantes].first(), pd.DataFrame(cols)], axis=1)
    out["reutilizado"] = False
    return out.reset_index()


def avisos_semillas(df: pd.DataFrame) -> list[str]:
    """Como avisos_homogeneidad, para una familia: la semilla (y con ella la huella) cambia a propósito."""
    avisos = avisos_homogeneidad(df, salvo=("semilla", "huella"))
    n = df.groupby("punto")["semilla"].nunique()
    if n.nunique() > 1:
        avisos.append(f"no todos los puntos tienen las mismas semillas (entre {n.min()} y {n.max()}): "
                      f"las medias de los incompletos son menos precisas")
    return avisos


def exportar_semillas(familia: str, destino: str | None = None) -> tuple[str, str]:
    """CSV con todas las corridas de la familia y CSV con la media e IC 95 % de cada punto."""
    df = tabla_semillas(familia)
    if df.empty:
        raise ValueError(f"no hay corridas hechas de '{familia}' con semillas "
                         f"(campañas {familia}_s<semilla>)")
    out = os.path.abspath(destino or os.path.join(DIR_REPORTES, f"{familia}_semillas"))
    os.makedirs(out, exist_ok=True)
    crudo = os.path.join(out, f"{familia}_semillas.csv")
    resumen = os.path.join(out, f"{familia}_resumen.csv")
    df.to_csv(crudo, index=False, sep=";", decimal=",", encoding="utf-8-sig")
    resumir_semillas(df).to_csv(resumen, index=False, sep=";", decimal=",", encoding="utf-8-sig")
    return crudo, resumen


def generar_semillas(familia: str, destino: str | None = None) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    df = tabla_semillas(familia)
    if df.empty:
        raise ValueError(f"no hay corridas hechas de '{familia}' con semillas "
                         f"(campañas {familia}_s<semilla>)")
    out = destino or os.path.join(DIR_REPORTES, f"{familia}_semillas")
    os.makedirs(out, exist_ok=True)
    primera = campanas_familia(familia)[0][0]
    with plt.rc_context(ESTILO):
        return _generar(resumir_semillas(df), out, _spec(primera), plt, crudo=df)


# ======================================================================
# Figuras
# ======================================================================
# Colores: categóricos EN ORDEN FIJO para las configuraciones físicas (cada
# una conserva su color en todas las figuras), rampa azul de un solo tono para
# niveles ordenados (vehículos, H) y rojo de estado solo para "cortado por
# tiempo". Paleta validada para daltonismo con 6 series; como tres tonos
# tienen poco contraste sobre blanco, cada serie lleva además su marcador.

CATEGORICA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
MARCADORES = ["o", "s", "^", "D", "v", "P", "X", "*"]
AZUL = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
        "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]   # pasos 100..700
CORTADO = "#d03b3b"
TINTA, TINTA_2, TENUE, REJILLA, EJE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"

ESTILO = {"font.family": "sans-serif", "font.size": 9, "axes.edgecolor": EJE,
          "axes.labelcolor": TINTA_2, "axes.titlecolor": TINTA, "axes.titlesize": 10,
          "xtick.color": EJE, "ytick.color": EJE, "xtick.labelcolor": TINTA_2,
          "ytick.labelcolor": TINTA_2, "axes.grid": True, "grid.color": REJILLA,
          "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
          "lines.linewidth": 1.6, "lines.markersize": 5, "legend.frameon": False,
          "text.color": TINTA, "figure.facecolor": "white"}


def _ordinal(n: int) -> list[str]:
    """n tonos de la rampa azul para niveles ordenados (del paso 250 al 650)."""
    if n == 1:
        return [AZUL[8]]
    return [AZUL[round(3 + 8 * k / (n - 1))] for k in range(n)]


def _orden_fisica(df):
    """Configuraciones físicas ordenadas de mayor a menor radio (clásica primero)."""
    r = df.groupby("fisica")["radio_m"].first().sort_values(ascending=False)
    return list(r.index)


def _etq_fisica(df, nivel):
    if nivel == "clasica":
        return "clásica\n300 m"
    radio = df.loc[df["fisica"] == nivel, "radio_m"].iloc[0]
    tasa, crit = nivel.split(":")
    return f"{tasa} Mb/s {crit}\n{radio:g} m"


def _orden_presupuesto(df) -> list[str]:
    """Niveles de presupuesto de menos a más RSU (libre al final)."""
    niveles = [p for p in dict.fromkeys(df["presupuesto"].dropna())]
    tope = {p: df.loc[df["presupuesto"] == p, "max_rsu"].dropna().max() for p in niveles}
    return sorted(niveles, key=lambda p: np.inf if pd.isna(tope[p]) else tope[p])


def generar(campana: str, destino: str | None = None) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    df = tabla(campana)
    if df.empty:
        raise ValueError(f"la campaña '{campana}' no tiene corridas hechas")
    out = destino or os.path.join(DIR_REPORTES, campana)
    os.makedirs(out, exist_ok=True)
    with plt.rc_context(ESTILO):
        return _generar(df, out, _spec(campana), plt)


def _generar(df, out, spec, plt, crudo=None) -> list[str]:
    """
    Todas las figuras y tablas. `df` tiene una fila por punto: la corrida de
    una campaña, o la media de las semillas (resumir_semillas) con sus columnas
    `_ic95`, que se dibujan como barras de error. `crudo` son las corridas de
    todas las semillas, para la figura del solver.
    """
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.lines import Line2D

    escritos = []
    n_sem = int(df["n_semillas"].max()) if "n_semillas" in df.columns else None

    def barras(ax, xs, sub, ycol, color, escala=1.0):
        """Barras de error del IC 95 % (solo con varias semillas)."""
        ic = f"{ycol}_ic95"
        if ic in sub.columns and sub[ic].notna().any():
            ax.errorbar(xs, escala * sub[ycol], yerr=escala * sub[ic].fillna(0), fmt="none",
                        ecolor=color, elinewidth=0.9, capsize=2.5, alpha=0.85, zorder=3)

    def guardar(fig, nombre):
        if n_sem:
            fig.text(0.995, 0.0, f"media de {n_sem} semillas · barras: IC 95 %", ha="right", va="top",
                     fontsize=7, color=TENUE)
        for ext in ("pdf", "png"):
            ruta = os.path.join(out, f"{nombre}.{ext}")
            fig.savefig(ruta, dpi=170, bbox_inches="tight")
            escritos.append(ruta)
        plt.close(fig)

    fis = _orden_fisica(df)                 # orden (y color) fijo de cada física
    vehs = sorted(df["vehiculos"].dropna().unique())
    Hs = sorted(df["H"].dropna().unique())
    Hmax = Hs[-1]
    # Orden de los filtrados: el del YAML (el primero es la referencia de la
    # tabla y del mapa de calor), no el de inserción en la base de datos.
    orden = (spec or {}).get("factores", {}).get("filtrado") or []
    filts = [f for f in orden if f in set(df["filtrado"])] + \
            [f for f in dict.fromkeys(df["filtrado"]) if f not in orden]
    x = np.arange(len(fis))
    etqs = [_etq_fisica(df, f) for f in fis]
    color_fis = {f: CATEGORICA[k % len(CATEGORICA)] for k, f in enumerate(fis)}
    marca_fis = {f: MARCADORES[k % len(MARCADORES)] for k, f in enumerate(fis)}
    proxy_cortado = Line2D([], [], ls="", marker="o", ms=9, mfc="none", mec=CORTADO, mew=1.4,
                           label="M3 cortado por tiempo" + (" (en alguna semilla)" if n_sem else ""))

    # ---- niveles base de los factores opcionales ----
    cargas = sorted(df["carga_mult"].dropna().unique())
    carga_base = (1.0 if 1.0 in cargas else cargas[0]) if cargas else None
    presus = _orden_presupuesto(df)
    pres_base = ("libre" if "libre" in presus else presus[-1]) if presus else None

    def en_base(d, salvo=None):
        if carga_base is not None and salvo != "carga":
            d = d[d["carga_mult"].isna() | (d["carga_mult"] == carga_base)]
        if pres_base is not None and salvo != "presupuesto":
            d = d[d["presupuesto"].isna() | (d["presupuesto"] == pres_base)]
        return d

    base = en_base(df)
    nota_base = ", ".join(t for t in (f"carga x{carga_base:g}" if carga_base is not None else "",
                                      f"presupuesto {pres_base}" if pres_base else "") if t)
    nota_base = f" [{nota_base}]" if nota_base else ""

    def lineas_por_fisica(ax, sub, xcol, ycol, escala=1.0):
        """Una línea por configuración física; anillo rojo en los puntos cortados."""
        for f in fis:
            s = sub[sub["fisica"] == f].sort_values(xcol)
            if s.empty or s[ycol].isna().all():
                continue
            ax.plot(s[xcol], escala * s[ycol], color=color_fis[f], marker=marca_fis[f],
                    label=_etq_fisica(df, f).replace("\n", ", "))
            barras(ax, s[xcol], s, ycol, color_fis[f], escala)
            c = s[s["cortado"]]
            if not c.empty:
                ax.scatter(c[xcol], escala * c[ycol], s=95, facecolors="none",
                           edgecolors=CORTADO, linewidths=1.4, zorder=5)

    def leyenda_fisica(fig, axs, con_cortado=True):
        handles = [Line2D([], [], color=color_fis[f], marker=marca_fis[f],
                          label=_etq_fisica(df, f).replace("\n", ", ")) for f in fis]
        if con_cortado and df["cortado"].any():
            handles.append(proxy_cortado)
        fig.legend(handles=handles, loc="lower center", ncol=min(len(handles), 4),
                   bbox_to_anchor=(0.5, -0.02), fontsize=8)
        fig.tight_layout(rect=(0, 0.07 + 0.03 * (len(handles) > 4), 1, 1))

    def rejilla_filtrado_veh(titulo):
        fig, axs = plt.subplots(len(filts), len(vehs), figsize=(4.4 * len(vehs), 3.3 * len(filts)),
                                squeeze=False, sharey="row")
        fig.suptitle(titulo, fontsize=11)
        return fig, axs

    # ---- 1 y 2: RSU y cobertura frente a la física, por demanda; paneles por H ----
    col_veh = dict(zip(vehs, _ordinal(len(vehs))))
    for metrica, nombre, eje in (("n_rsu", "rsu_vs_fisica", "RSU desplegadas"),
                                 ("cobertura_pct", "cobertura_vs_fisica", "cobertura (%)")):
        fig, axs = plt.subplots(len(filts), len(Hs), figsize=(4.6 * len(Hs), 3.6 * len(filts)),
                                squeeze=False, sharey=True)
        for i, filt in enumerate(filts):
            for j, H in enumerate(Hs):
                ax = axs[i][j]
                for v in vehs:
                    sub = base[(base["filtrado"] == filt) & (base["H"] == H) & (base["vehiculos"] == v)]
                    y = [sub.loc[sub["fisica"] == f, metrica].mean() if (sub["fisica"] == f).any()
                         else np.nan for f in fis]
                    ax.plot(x, y, marker="o", color=col_veh[v], label=f"{int(v)} veh")
                    if f"{metrica}_ic95" in sub.columns:     # una fila por física, en el orden del eje x
                        barras(ax, x, sub.set_index("fisica").reindex(fis), metrica, col_veh[v])
                    for xx, f in zip(x, fis):           # marca los cortados por tiempo
                        c = sub[(sub["fisica"] == f) & sub["cortado"]]
                        if not c.empty:
                            ax.scatter([xx], [c[metrica].mean()], s=95, facecolors="none",
                                       edgecolors=CORTADO, linewidths=1.4, zorder=5)
                ax.set_title(f"filtrado {filt} · H = {int(H)}")
                ax.set_xticks(x)
                ax.set_xticklabels(etqs, fontsize=7.5)
                if j == 0:
                    ax.set_ylabel(eje)
        h, _ = axs[0][0].get_legend_handles_labels()
        axs[0][0].legend(handles=h + ([proxy_cortado] if base["cortado"].any() else []), fontsize=8)
        fig.suptitle(("¿Cuántas RSU exige cada configuración física?" if metrica == "n_rsu"
                      else "¿Qué cobertura logra el despliegue óptimo?") + nota_base, fontsize=11)
        fig.tight_layout()
        guardar(fig, nombre)

    # ---- 3: valor del multisalto según H ----
    if len(Hs) > 1:
        fig, axs = plt.subplots(1, 2, figsize=(10, 3.8))
        vmax = vehs[-1]
        sub = base[(base["vehiculos"] == vmax) & (base["filtrado"] == filts[0])]
        lineas_por_fisica(axs[0], sub, "H", "cobertura_pct")
        lineas_por_fisica(axs[1], sub, "H", "frac_multisalto", escala=100)
        axs[0].set_ylabel("cobertura (%)")
        axs[1].set_ylabel("servidos por multisalto (%)")
        for ax in axs:
            ax.set_xlabel("saltos máximos H")
            ax.set_xticks(Hs)
        fig.suptitle(f"¿Cuánto aporta el multisalto según el alcance? ({int(vmax)} veh, "
                     f"filtrado {filts[0]}){nota_base}", fontsize=11)
        leyenda_fisica(fig, axs)
        guardar(fig, "multisalto_vs_H")

    # ---- 3b: multisalto frente a la demanda ----
    if len(vehs) > 1 and len(Hs) > 1:
        Hmulti = [h for h in Hs if h > 1]
        fig, axs = plt.subplots(len(Hmulti), len(filts), figsize=(4.4 * len(filts), 3.3 * len(Hmulti)),
                                squeeze=False, sharey=True)
        for i, H in enumerate(Hmulti):
            for j, filt in enumerate(filts):
                ax = axs[i][j]
                lineas_por_fisica(ax, base[(base["H"] == H) & (base["filtrado"] == filt)],
                                  "vehiculos", "frac_multisalto", escala=100)
                ax.set_xticks(vehs)
                ax.set_title(f"filtrado {filt} · H = {int(H)}")
                if j == 0:
                    ax.set_ylabel("servidos por multisalto (%)")
                if i == len(Hmulti) - 1:
                    ax.set_xlabel("vehículos")
        fig.suptitle(f"¿Crece el multisalto con la demanda?{nota_base}", fontsize=11)
        leyenda_fisica(fig, axs)
        guardar(fig, "multisalto_vs_vehiculos")

    # ---- 4: filtrado (respuesta al revisor) ----
    if len(filts) > 1:
        a, b = filts[0], filts[1]
        claves = ["vehiculos", "fisica", "H"]
        m = base[base["filtrado"] == a].merge(base[base["filtrado"] == b], on=claves,
                                              suffixes=(f"_{a}", f"_{b}"))
        if not m.empty:
            fig, axs = plt.subplots(1, 2, figsize=(10, 4))
            for ax, met, eje in ((axs[0], "n_rsu", "RSU desplegadas"), (axs[1], "cobertura_pct", "cobertura (%)")):
                for v in vehs:
                    t = m[m["vehiculos"] == v]
                    ax.scatter(t[f"{met}_{b}"], t[f"{met}_{a}"], color=col_veh[v], s=30,
                               edgecolors="white", linewidths=0.6, label=f"{int(v)} veh")
                    if f"{met}_ic95_{a}" in t.columns:
                        ax.errorbar(t[f"{met}_{b}"], t[f"{met}_{a}"], xerr=t[f"{met}_ic95_{b}"].fillna(0),
                                    yerr=t[f"{met}_ic95_{a}"].fillna(0), fmt="none", ecolor=col_veh[v],
                                    elinewidth=0.7, alpha=0.6, zorder=1)
                lo = np.nanmin([m[f"{met}_{a}"].min(), m[f"{met}_{b}"].min()])
                hi = np.nanmax([m[f"{met}_{a}"].max(), m[f"{met}_{b}"].max()])
                ax.plot([lo, hi], [lo, hi], color=TENUE, lw=1)
                ax.set_xlabel(f"{eje} con filtrado {b}")
                ax.set_ylabel(f"{eje} con filtrado {a}")
            axs[0].legend(fontsize=8)
            fig.suptitle(f"¿Filtrar candidatas empeora el despliegue óptimo? ({a} frente a {b}; "
                         f"sobre la diagonal = igual){nota_base}", fontsize=11)
            fig.tight_layout()
            guardar(fig, "filtrado")

    # ---- 5: escalabilidad del solver (todos los puntos resueltos, sin copias; con
    # varias semillas, cada corrida de cada semilla: aquí no se promedia) ----
    todas = crudo if crudo is not None else df
    s = todas[~todas["reutilizado"]].dropna(subset=["cvr", "segundos_solver"])
    if not s.empty:
        fig, ax = plt.subplots(figsize=(6.4, 4.2))
        for flag, col, etq in ((False, CATEGORICA[0], "óptimo demostrado"), (True, CORTADO, "cortado por tiempo")):
            t = s[s["cortado"] == flag]
            ax.scatter(t["cvr"], t["segundos_solver"].clip(lower=0.05), color=col, s=26,
                       edgecolors="white", linewidths=0.5, label=etq)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("|CVR| (tuplas = variables Rts)")
        ax.set_ylabel("tiempo del solver (s)")
        ax.grid(which="both")
        ax.legend(fontsize=9)
        ax.set_title("¿Cómo crece el tiempo de CPLEX con el tamaño del problema?", fontsize=11)
        guardar(fig, "solver_vs_cvr")

    # ---- 6: mapa de calor RSU (física x demanda) ----
    sub = base[(base["H"] == Hmax) & (base["filtrado"] == filts[0])]
    M = np.array([[sub.loc[(sub["fisica"] == f) & (sub["vehiculos"] == v), "n_rsu"].mean()
                   for v in vehs] for f in fis], dtype=float)
    fig, ax = plt.subplots(figsize=(1.6 + 1.3 * len(vehs), 1.2 + 0.55 * len(fis)))
    mapa = LinearSegmentedColormap.from_list("azul", AZUL)
    im = ax.imshow(M, cmap=mapa, aspect="auto")
    ax.grid(False)
    lo, hi = np.nanmin(M) if np.isfinite(M).any() else 0, np.nanmax(M) if np.isfinite(M).any() else 1
    for i in range(len(fis)):
        for j in range(len(vehs)):
            if not np.isnan(M[i, j]):
                oscuro = hi > lo and (M[i, j] - lo) / (hi - lo) > 0.55
                ax.text(j, i, f"{M[i, j]:.0f}", ha="center", va="center", fontsize=9,
                        color="white" if oscuro else TINTA)
    ax.set_xticks(range(len(vehs)))
    ax.set_xticklabels([f"{int(v)}" for v in vehs])
    ax.set_yticks(range(len(fis)))
    ax.set_yticklabels([e.replace("\n", ", ") for e in etqs], fontsize=8)
    ax.set_xlabel("vehículos")
    fig.colorbar(im, ax=ax, label="RSU desplegadas" + (" (media)" if n_sem else ""))
    ax.set_title(f"RSU desplegadas (H = {int(Hmax)}, filtrado {filts[0]}){nota_base}", fontsize=10)
    guardar(fig, "mapa_calor_rsu")

    # ---- 7: factor carga ----
    if len(cargas) > 1:
        dc = en_base(df, salvo="carga")
        dc = dc[dc["H"] == Hmax]
        kbps = {c: dc.loc[dc["carga_mult"] == c, "carga_kbps"].dropna() for c in cargas}
        tick = [f"x{c:g}\n{kbps[c].iloc[0]:g} kb/s" if not kbps[c].empty else f"x{c:g}" for c in cargas]
        for ycol, nombre, eje, titulo, escala in (
                ("n_rsu", "rsu_vs_carga", "RSU desplegadas",
                 "¿Cuántas RSU más exige el tráfico de cada vehículo?", 1.0),
                ("cobertura_pct", "cobertura_vs_carga", "cobertura (%)",
                 "¿Cuándo deja la capacidad de cubrir a todos?", 1.0),
                ("uso_capacidad", "uso_vs_carga", "uso medio de la capacidad (%)",
                 "¿Cuánto se llenan las RSU encendidas?", 100.0),
                ("frac_multisalto", "multisalto_vs_carga", "servidos por multisalto (%)",
                 "¿Se abandona el multisalto cuando la capacidad escasea?", 100.0)):
            fig, axs = rejilla_filtrado_veh(f"{titulo} (H = {int(Hmax)})")
            for i, filt in enumerate(filts):
                for j, v in enumerate(vehs):
                    ax = axs[i][j]
                    sub = dc[(dc["filtrado"] == filt) & (dc["vehiculos"] == v)]
                    lineas_por_fisica(ax, sub, "carga_mult", ycol, escala)
                    if ycol == "n_rsu" and not sub.empty:
                        # Techo: todas las candidatas encendidas
                        ax.axhline(sub["Y"].max(), color=TENUE, lw=1)
                        ax.annotate(f"Y = {int(sub['Y'].max())} candidatas", (cargas[0], sub["Y"].max()),
                                    xytext=(0, -11), textcoords="offset points", fontsize=7.5,
                                    color=TINTA_2)
                    ax.set_xticks(cargas)
                    ax.set_xticklabels(tick, fontsize=7.5)
                    ax.set_title(f"{int(v)} veh · filtrado {filt}")
                    if j == 0:
                        ax.set_ylabel(eje)
            leyenda_fisica(fig, axs)
            guardar(fig, nombre)

    # ---- 8: factor presupuesto ----
    if len(presus) > 1:
        dp = en_base(df, salvo="presupuesto")
        dp = dp[dp["H"] == Hmax].copy()
        dp["pos"] = dp["presupuesto"].map({p: k for k, p in enumerate(presus)})

        # 8a. curva cobertura - número de RSU
        fig, axs = rejilla_filtrado_veh(f"¿Cuánta cobertura aporta cada RSU de más? "
                                        f"(H = {int(Hmax)}; un punto por presupuesto)")
        for i, filt in enumerate(filts):
            for j, v in enumerate(vehs):
                ax = axs[i][j]
                lineas_por_fisica(ax, dp[(dp["filtrado"] == filt) & (dp["vehiculos"] == v)],
                                  "n_rsu", "cobertura_pct")
                ax.set_title(f"{int(v)} veh · filtrado {filt}")
                if j == 0:
                    ax.set_ylabel("cobertura (%)")
                if i == len(filts) - 1:
                    ax.set_xlabel("RSU desplegadas")
        leyenda_fisica(fig, axs)
        guardar(fig, "cobertura_vs_rsu")

        def ticks_presupuesto(ax, v):
            etq = []
            for p in presus:
                mr = dp.loc[(dp["presupuesto"] == p) & (dp["vehiculos"] == v), "max_rsu"].dropna()
                etq.append(f"{p}\n(máx. {int(mr.iloc[0])})" if not mr.empty else p)
            ax.set_xticks(range(len(presus)))
            ax.set_xticklabels(etq, fontsize=7.5)

        # 8b. multisalto frente al presupuesto
        fig, axs = rejilla_filtrado_veh(f"¿Crece el multisalto cuando hay menos RSU? (H = {int(Hmax)})")
        for i, filt in enumerate(filts):
            for j, v in enumerate(vehs):
                ax = axs[i][j]
                lineas_por_fisica(ax, dp[(dp["filtrado"] == filt) & (dp["vehiculos"] == v)],
                                  "pos", "frac_multisalto", escala=100)
                ticks_presupuesto(ax, v)
                ax.set_title(f"{int(v)} veh · filtrado {filt}")
                if j == 0:
                    ax.set_ylabel("servidos por multisalto (%)")
        leyenda_fisica(fig, axs)
        guardar(fig, "multisalto_vs_presupuesto")

        # 8c. ¿cuánto compensa H la falta de RSU? (demanda mayor, primer filtrado)
        if len(Hs) > 1:
            vmax = vehs[-1]
            dh = en_base(df, salvo="presupuesto")
            dh = dh[(dh["vehiculos"] == vmax) & (dh["filtrado"] == filts[0])].copy()
            dh["pos"] = dh["presupuesto"].map({p: k for k, p in enumerate(presus)})
            ncol = min(3, len(fis))
            nfil = int(np.ceil(len(fis) / ncol))
            fig, axs = plt.subplots(nfil, ncol, figsize=(4.0 * ncol, 3.1 * nfil), squeeze=False,
                                    sharey=True)
            col_H = dict(zip(Hs, _ordinal(len(Hs))))
            for k, f in enumerate(fis):
                ax = axs[k // ncol][k % ncol]
                for H in Hs:
                    t = dh[(dh["fisica"] == f) & (dh["H"] == H)].sort_values("pos")
                    ax.plot(t["pos"], t["cobertura_pct"], color=col_H[H], marker="o",
                            label=f"H = {int(H)}")
                    barras(ax, t["pos"], t, "cobertura_pct", col_H[H])
                    c = t[t["cortado"]]
                    if not c.empty:
                        ax.scatter(c["pos"], c["cobertura_pct"], s=95, facecolors="none",
                                   edgecolors=CORTADO, linewidths=1.4, zorder=5)
                ticks_presupuesto(ax, vmax)
                ax.set_title(_etq_fisica(df, f).replace("\n", ", "))
                if k % ncol == 0:
                    ax.set_ylabel("cobertura (%)")
            for k in range(len(fis), nfil * ncol):
                axs[k // ncol][k % ncol].set_visible(False)
            h, _ = axs[0][0].get_legend_handles_labels()
            fig.legend(handles=h + ([proxy_cortado] if dh["cortado"].any() else []),
                       loc="lower center", ncol=len(h) + 1, bbox_to_anchor=(0.5, -0.02), fontsize=8)
            fig.suptitle(f"¿Compensa el multisalto la falta de RSU? ({int(vmax)} veh, "
                         f"filtrado {filts[0]})", fontsize=11)
            fig.tight_layout(rect=(0, 0.06, 1, 1))
            guardar(fig, "cobertura_vs_presupuesto_H")

    # ---- tablas LaTeX ----
    escritos += _tablas(df, base, out, fis, vehs, Hmax, filts, cargas, presus,
                        en_base, nota_base)
    return escritos


def _etq_fisica_tex(f, radio):
    if f == "clasica":
        return "clásica (300 m)"
    tasa, crit = f.split(":")
    return f"{tasa} Mb/s, $r_{{{crit[1:]}}}$ ({radio:g} m)"


def _tablas(df, base, out, fis, vehs, Hmax, filts, cargas, presus, en_base, nota_base) -> list[str]:
    bs = chr(92)
    daga = "$^" + bs + "dagger$"
    escritos = []
    n_sem = int(df["n_semillas"].max()) if "n_semillas" in df.columns else None
    fmt_rsu = ".1f" if n_sem else ".0f"            # con varias semillas, el número de RSU es una media
    nota_sem = " Media $" + bs + f"pm$ IC 95 % de {n_sem} semillas." if n_sem else ""
    nota_cortado = " (en alguna semilla)" if n_sem else ""

    def val(r, col, fmt, escala=1.0):
        """El valor de la celda; con varias semillas, media ± semiancho del IC 95 %."""
        v = r.get(col)
        if v is None or pd.isna(v):
            return "--"
        texto = format(escala * v, fmt)
        ic = r.get(f"{col}_ic95")
        if ic is not None and pd.notna(ic):
            texto += " $" + bs + "pm$ " + format(escala * ic, fmt)
        return texto

    def escribir(nombre, columnas, cabecera, filas, pie):
        lineas = ["% generado por scn.py reporte -- no editar a mano",
                  bs + "begin{tabular}{" + columnas + "}",
                  bs + "toprule",
                  cabecera + " " + bs * 2,
                  bs + "midrule",
                  *filas,
                  bs + "bottomrule",
                  bs + "end{tabular}",
                  pie]
        ruta = os.path.join(out, nombre)
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lineas) + "\n")
        escritos.append(ruta)

    # Resumen (nivel base)
    filas = []
    for f in fis:
        for v in vehs:
            t = base[(base["fisica"] == f) & (base["vehiculos"] == v) & (base["H"] == Hmax)
                     & (base["filtrado"] == filts[0])]
            if t.empty:
                continue
            r = t.iloc[0]
            cvr = f"{int(round(r['cvr'])):,}".replace(",", bs + ",")
            filas.append(f"{_etq_fisica_tex(f, r['radio_m'])} & {int(v)} & {int(r['Y'])} & {cvr} & "
                         f"{val(r, 'n_rsu', fmt_rsu)} & {val(r, 'cobertura_pct', '.1f')} & "
                         f"{val(r, 'frac_multisalto', '.1f', 100)} & "
                         f"{val(r, 'segundos_solver', '.1f')}{daga if r['cortado'] else ''} " + bs * 2)
    escribir("tabla_resumen.tex", "l r r r r r r r",
             "Física & Veh. & $Y$ & $|" + bs + "mathrm{CVR}|$ & RSU & Cob. (" + bs + "%) & "
             "Multisalto (" + bs + "%) & Solver (s)", filas,
             f"% H = {int(Hmax)}, filtrado {filts[0]}{nota_base}.{nota_sem} " + daga
             + f" = M3 cortado por tiempo{nota_cortado} (mejor solución hallada).")

    # Carga: RSU (cobertura) por nivel
    if len(cargas) > 1:
        dc = en_base(df, salvo="carga")
        filas = []
        for f in fis:
            for v in vehs:
                t = dc[(dc["fisica"] == f) & (dc["vehiculos"] == v) & (dc["H"] == Hmax)
                       & (dc["filtrado"] == filts[0])]
                if t.empty:
                    continue
                celdas = []
                for c in cargas:
                    r = t[t["carga_mult"] == c]
                    if r.empty:
                        celdas.append("--")
                        continue
                    r = r.iloc[0]
                    celdas.append(f"{val(r, 'n_rsu', fmt_rsu)} ({val(r, 'cobertura_pct', '.1f')})"
                                  + (daga if r["cortado"] else ""))
                filas.append(f"{_etq_fisica_tex(f, t['radio_m'].iloc[0])} & {int(v)} & "
                             + " & ".join(celdas) + " " + bs * 2)
        escribir("tabla_carga.tex", "l r " + "r " * len(cargas),
                 "Física & Veh. & " + " & ".join(f"$" + bs + f"times {c:g}$" for c in cargas), filas,
                 f"% RSU desplegadas (cobertura en %), H = {int(Hmax)}, filtrado {filts[0]}.{nota_sem} "
                 + daga + f" = M3 cortado por tiempo{nota_cortado}.")

    # Presupuesto: cobertura (multisalto) por nivel
    if len(presus) > 1:
        dp = en_base(df, salvo="presupuesto")
        filas = []
        for f in fis:
            for v in vehs:
                t = dp[(dp["fisica"] == f) & (dp["vehiculos"] == v) & (dp["H"] == Hmax)
                       & (dp["filtrado"] == filts[0])]
                if t.empty:
                    continue
                celdas = []
                for p in presus:
                    r = t[t["presupuesto"] == p]
                    if r.empty:
                        celdas.append("--")
                        continue
                    r = r.iloc[0]
                    celdas.append(f"{val(r, 'cobertura_pct', '.1f')} ({val(r, 'frac_multisalto', '.1f', 100)})"
                                  + (daga if r["cortado"] else ""))
                filas.append(f"{_etq_fisica_tex(f, t['radio_m'].iloc[0])} & {int(v)} & "
                             + " & ".join(celdas) + " " + bs * 2)
        topes = "; ".join(
            f"{p}: " + ", ".join(f"{int(m)} con {int(v)} veh" for v, m in
                                 dp[dp["presupuesto"] == p].groupby("vehiculos")["max_rsu"].first().dropna().items())
            for p in presus if p != "libre")
        escribir("tabla_presupuesto.tex", "l r " + "r " * len(presus),
                 "Física & Veh. & " + " & ".join(presus), filas,
                 f"% Cobertura en % (servidos por multisalto en %), H = {int(Hmax)}, filtrado {filts[0]}. "
                 f"MaxR: {topes}.{nota_sem} " + daga + f" = M3 cortado por tiempo{nota_cortado}.")
    return escritos
