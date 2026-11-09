"""
powerbi.py — las campañas en Power BI, sin armar nada a mano
============================================================
`scn.py powerbi` escribe un PROYECTO de Power BI (`.pbip`) en
datos/reportes/powerbi/: unos archivos de texto que Power BI Desktop abre como
un informe normal. Lleva:

  * el MODELO: una tabla por campaña, leída del CSV de `scn.py exportar` con
    los tipos ya puestos (coma decimal, verdadero/falso) y con las métricas
    resumidas por PROMEDIO, no por suma (cada fila es un punto distinto: sumar
    puntos de distinto H o filtrado no significa nada);
  * el INFORME: una página por campaña con segmentaciones (vehículos,
    filtrado, H, cortado) y cuatro gráficos de líneas —RSU, cobertura,
    multisalto y uso de la capacidad— frente al factor de la campaña (carga,
    presupuesto o vehículos), una línea por configuración física con los
    mismos colores que las figuras de la tesis.

Al abrirlo por primera vez Power BI dice que faltan datos: "Actualizar ahora"
los carga del CSV. Volver a generar SOBRESCRIBE la carpeta: lo que se edite a
mano en Power BI conviene guardarlo con otro nombre.
"""

import json
import os
import shutil
import uuid

import pandas as pd

from . import reporte

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(_RAIZ, "datos", "reportes", "powerbi")
NOMBRE = "SmartCityNet"
CAMPANAS_TESIS = ("fisica_v1", "trafico_v1", "presupuesto_v1")

# (columna, tipo en Power Query, tipo en el modelo, resumen, formato)
COLUMNAS = [
    ("punto", "type text", "string", "none", None),
    ("vehiculos", "Int64.Type", "int64", "none", "0"),
    ("filtrado", "type text", "string", "none", None),
    ("fisica", "type text", "string", "none", None),
    ("tasa_mbps", "type number", "double", "none", "0"),
    ("criterio", "type text", "string", "none", None),
    ("radio_m", "type number", "double", "none", "0"),
    ("H", "Int64.Type", "int64", "none", "0"),
    ("carga_mult", "type number", "double", "none", "×0"),
    ("carga_kbps", "type number", "double", "none", "0"),
    ("cap_kbps", "type number", "double", "none", "0"),
    ("presupuesto", "type text", "string", "none", None),
    ("max_rsu", "type number", "double", "none", "0"),
    ("Y", "Int64.Type", "int64", "none", "0"),
    ("cvr", "Int64.Type", "int64", "average", "#,0"),
    ("q_reach", "type number", "double", "average", "0.0"),
    ("n_rsu", "type number", "double", "average", "0"),
    ("cobertura_pct", "type number", "double", "average", "0.0"),
    ("conectados", "type number", "double", "average", "0"),
    ("multisalto", "type number", "double", "average", "0"),
    ("frac_multisalto", "type number", "double", "average", "0.0%"),
    ("uso_capacidad", "type number", "double", "average", "0.0%"),
    ("segundos_solver", "type number", "double", "average", "0"),
    ("status", "type text", "string", "none", None),
    ("cortado", "type logical", "boolean", "none", None),
    ("optimo", "type logical", "boolean", "none", None),
    ("reutilizado", "type logical", "boolean", "none", None),
]

# (columna, título del gráfico, nombre del eje Y)
GRAFICOS = (("n_rsu", "RSU desplegadas", "RSU desplegadas"),
            ("cobertura_pct", "Cobertura (%)", "Cobertura (%)"),
            ("frac_multisalto", "Servidos por multisalto", "Servidos por multisalto (%)"),
            ("uso_capacidad", "Uso medio de la capacidad", "Uso de la capacidad (%)"))


# ======================================================================
# Modelo
# ======================================================================

def _etiqueta_fisica(tasa, criterio, radio) -> str:
    """La misma etiqueta que construye la consulta M (para fijar los colores)."""
    return f"{float(tasa):g} Mb/s {criterio} ({float(radio):g} m)"


def _consulta_m(csv: str, orden_presupuesto: list[str]) -> list[str]:
    nombres = ", ".join(f'"{c[0]}"' for c in COLUMNAS)
    tipos = ", ".join(f'{{"{c[0]}", {c[1]}}}' for c in COLUMNAS)
    niveles = ", ".join(f'"{p}"' for p in orden_presupuesto)
    return [
        "let",
        f'    Origen = Csv.Document(File.Contents("{csv}"), [Delimiter=";", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
        "    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars=true]),",
        f"    Columnas = Table.SelectColumns(Encabezados, {{{nombres}}}, MissingField.UseNull),",
        # es-ES: el CSV va con coma decimal (formato de Excel en español)
        f'    Tipos = Table.TransformColumnTypes(Columnas, {{{tipos}}}, "es-ES"),',
        '    Fisica = Table.AddColumn(Tipos, "fisica_etq", each Number.ToText([tasa_mbps]) & " Mb/s " '
        '& [criterio] & " (" & Number.ToText([radio_m]) & " m)", type text),',
        # Orden de la leyenda: de mayor a menor radio, como en las figuras
        '    OrdenFisica = Table.AddColumn(Fisica, "orden_fisica", each -[radio_m], type number),',
        f'    OrdenPres = Table.AddColumn(OrdenFisica, "orden_presupuesto", each List.PositionOf({{{niveles}}}, '
        '[presupuesto]), Int64.Type)',
        "in",
        "    OrdenPres",
    ]


def _tabla(nombre: str, csv: str, orden_presupuesto: list[str]) -> dict:
    cols = []
    for col, _, tipo, resumen, fmt in COLUMNAS:
        c = {"name": col, "dataType": tipo, "sourceColumn": col, "summarizeBy": resumen}
        if fmt:
            c["formatString"] = fmt
        if col == "presupuesto":
            c["sortByColumn"] = "orden_presupuesto"
        cols.append(c)
    cols += [
        {"name": "fisica_etq", "dataType": "string", "sourceColumn": "fisica_etq",
         "summarizeBy": "none", "sortByColumn": "orden_fisica"},
        {"name": "orden_fisica", "dataType": "double", "sourceColumn": "orden_fisica",
         "summarizeBy": "none", "isHidden": True},
        {"name": "orden_presupuesto", "dataType": "int64", "sourceColumn": "orden_presupuesto",
         "summarizeBy": "none", "isHidden": True},
    ]
    return {"name": nombre, "columns": cols,
            "partitions": [{"name": nombre, "mode": "import",
                            "source": {"type": "m", "expression": _consulta_m(csv, orden_presupuesto)}}]}


# ======================================================================
# Informe (formato report.json de Power BI Desktop)
# ======================================================================

def _col(prop):
    return {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": prop}}


def _lit(valor):
    return {"expr": {"Literal": {"Value": valor}}}


def _texto(s):
    return "'" + str(s).replace("'", "''") + "'"


def _contenedor(x, y, w, h, z, visual):
    cfg = {"name": uuid.uuid4().hex[:20],
           "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": z, "width": w, "height": h}}],
           "singleVisual": visual}
    return {"x": x, "y": y, "z": z, "width": w, "height": h,
            "config": json.dumps(cfg, ensure_ascii=False), "filters": "[]"}


def _segmentacion(tabla, prop, titulo, valor=None, unica=True):
    v = {"visualType": "slicer",
         "projections": {"Values": [{"queryRef": f"{tabla}.{prop}", "active": True}]},
         "prototypeQuery": {"Version": 2, "From": [{"Name": "t", "Entity": tabla, "Type": 0}],
                            "Select": [{**_col(prop), "Name": f"{tabla}.{prop}",
                                        "NativeReferenceName": prop}]},
         "objects": {"data": [{"properties": {"mode": _lit("'Basic'")}}],
                     "selection": [{"properties": {"strictSingleSelect": _lit("true" if unica else "false")}}],
                     "header": [{"properties": {"show": _lit("false")}}]},
         "vcObjects": {"title": [{"properties": {"show": _lit("true"), "text": _lit(_texto(titulo))}}]}}
    if valor is not None:
        v["objects"]["general"] = [{"properties": {"filter": {"filter": {
            "Version": 2, "From": [{"Name": "t", "Entity": tabla, "Type": 0}],
            "Where": [{"Condition": {"In": {"Expressions": [_col(prop)],
                                            "Values": [[{"Literal": {"Value": valor}}]]}}}]}}}}]
    return v


def _eje(titulo, **extra):
    """Eje con su nombre visible (el de la columna, p. ej. carga_mult, no dice nada)."""
    return [{"properties": {**extra, "showAxisTitle": _lit("true"), "titleText": _lit(_texto(titulo))}}]


def _lineas(tabla, x, y, titulo, colores, titulo_x, titulo_y):
    puntos = [{"properties": {"fill": {"solid": {"color": _lit(_texto(color))}}},
               "selector": {"data": [{"scopeId": {"Comparison": {
                   "ComparisonKind": 0,
                   "Left": {"Column": {"Expression": {"SourceRef": {"Entity": tabla}},
                                       "Property": "fisica_etq"}},
                   "Right": {"Literal": {"Value": _texto(etq)}}}}}]}}
              for etq, color in colores.items()]
    return {"visualType": "lineChart",
            "projections": {"Category": [{"queryRef": f"{tabla}.{x}", "active": True}],
                            "Y": [{"queryRef": f"Avg({tabla}.{y})"}],
                            "Series": [{"queryRef": f"{tabla}.fisica_etq"}]},
            "prototypeQuery": {"Version": 2, "From": [{"Name": "t", "Entity": tabla, "Type": 0}],
                               "Select": [
                                   {**_col(x), "Name": f"{tabla}.{x}", "NativeReferenceName": x},
                                   {"Aggregation": {"Expression": _col(y), "Function": 1},
                                    "Name": f"Avg({tabla}.{y})", "NativeReferenceName": f"Promedio de {y}"},
                                   {**_col("fisica_etq"), "Name": f"{tabla}.fisica_etq",
                                    "NativeReferenceName": "fisica_etq"}]},
            "drillFilterOtherVisuals": True,
            "objects": {"legend": [{"properties": {"position": _lit("'Right'"), "showTitle": _lit("false")}}],
                        "categoryAxis": _eje(titulo_x, axisType=_lit("'Categorical'")),
                        "valueAxis": _eje(titulo_y),
                        "dataPoint": puntos},
            "vcObjects": {"title": [{"properties": {"show": _lit("true"), "text": _lit(_texto(titulo))}}]}}


def _pagina(campana: str, df: pd.DataFrame, spec: dict | None) -> dict:
    """Una página: segmentaciones arriba y los cuatro gráficos frente al factor de la campaña."""
    fac = (spec or {}).get("factores", {})
    if "carga" in fac:
        base = (df["carga_kbps"] / df["carga_mult"]).median()
        x, eje, nombre = "carga_mult", "la carga", f"Carga ({campana})"
        titulo_x = f"Carga por vehículo (múltiplo de {base:g} kb/s)"
    elif "presupuesto" in fac:
        x, eje, nombre = "presupuesto", "el presupuesto de RSU", f"Presupuesto ({campana})"
        titulo_x = "Presupuesto de RSU (número máximo de antenas)"
    else:
        x, eje, nombre = "vehiculos", "los vehículos", f"Demanda ({campana})"
        titulo_x = "Vehículos simulados"

    filtrados = [f for f in (fac.get("filtrado") or []) if f in set(df["filtrado"])] or sorted(df["filtrado"].unique())
    segs = []
    if x != "vehiculos":
        segs.append(("vehiculos", "Vehículos", f"{int(df['vehiculos'].max())}L"))
    segs += [("filtrado", "Filtrado", _texto(filtrados[0])),
             ("H", "Saltos máximos H", f"{int(df['H'].max())}L"),
             ("cortado", "Cortado por tiempo (ninguno marcado = todos)", None)]

    fis = (df.drop_duplicates("fisica").sort_values("radio_m", ascending=False))
    colores = {_etiqueta_fisica(r.tasa_mbps, r.criterio, r.radio_m): reporte.CATEGORICA[k % len(reporte.CATEGORICA)]
               for k, r in enumerate(fis.itertuples()) if pd.notna(r.tasa_mbps)}

    vis, z = [], 0
    ancho = (1280 - 20 - 10 * (len(segs) - 1)) / len(segs)
    for i, (prop, tit, val) in enumerate(segs):
        vis.append(_contenedor(10 + i * (ancho + 10), 6, ancho, 118, z,
                               _segmentacion(campana, prop, tit, val, unica=prop != "cortado")))
        z += 1000
    for k, (y, tit, tit_y) in enumerate(GRAFICOS):
        vis.append(_contenedor(10 + (k % 2) * 635, 130 + (k // 2) * 295, 625, 288, z,
                               _lineas(campana, x, y, f"{tit} frente a {eje}", colores, titulo_x, tit_y)))
        z += 1000
    return {"name": "ReportSection" + uuid.uuid4().hex[:20], "displayName": nombre,
            "displayOption": 1, "filters": "[]", "config": "{}",
            "width": 1280, "height": 720, "visualContainers": vis}


# ======================================================================
# Proyecto
# ======================================================================

def _escribir(ruta, obj):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def generar(campanas=None, destino: str = DESTINO) -> str:
    """
    Exporta el CSV de cada campaña y escribe el proyecto. Devuelve la ruta del
    .pbip. Sin `campanas`, las de la tesis que tengan corridas hechas.
    """
    tablas, paginas = [], []
    for c in campanas or CAMPANAS_TESIS:
        df = reporte.tabla(c)
        if df.empty:
            if campanas:
                raise ValueError(f"la campaña '{c}' no tiene corridas hechas")
            continue
        csv = reporte.exportar(c)
        spec = reporte._spec(c)
        presus = reporte._orden_presupuesto(df) if df["presupuesto"].notna().any() else []
        tablas.append(_tabla(c, csv, presus))
        paginas.append(_pagina(c, df, spec))
    if not tablas:
        raise ValueError("ninguna campaña tiene corridas hechas")

    if os.path.isdir(destino):
        shutil.rmtree(destino)
    sm, rp = f"{NOMBRE}.SemanticModel", f"{NOMBRE}.Report"
    _escribir(os.path.join(destino, f"{NOMBRE}.pbip"),
              {"version": "1.0", "artifacts": [{"report": {"path": rp}}],
               "settings": {"enableAutoRecovery": True}})
    _escribir(os.path.join(destino, sm, "definition.pbism"), {"version": "1.0", "settings": {}})
    _escribir(os.path.join(destino, sm, "model.bim"), {
        "compatibilityLevel": 1550,
        "model": {"culture": "es-ES", "sourceQueryCulture": "es-ES",
                  "defaultPowerBIDataSourceVersion": "powerBI_V3",
                  "dataAccessOptions": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
                  "tables": tablas,
                  "annotations": [{"name": "PBI_QueryOrder", "value": json.dumps([t["name"] for t in tablas])},
                                  {"name": "__PBI_TimeIntelligenceEnabled", "value": "0"}]}})
    _escribir(os.path.join(destino, rp, "definition.pbir"),
              {"version": "1.0", "datasetReference": {"byPath": {"path": f"../{sm}"}, "byConnection": None}})
    _escribir(os.path.join(destino, rp, "report.json"), {
        "config": json.dumps({"version": "5.43", "themeCollection": {}, "activeSectionIndex": 0,
                              "defaultDrillFilterOtherVisuals": True}),
        "layoutOptimization": 0, "sections": paginas})
    return os.path.join(destino, f"{NOMBRE}.pbip")
