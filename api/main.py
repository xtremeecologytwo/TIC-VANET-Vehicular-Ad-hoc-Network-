"""
API REST de SmartCityNet (FastAPI)
==================================
Expone el backend VANET (SUMO, LoS, multisalto, optimización) como una API HTTP
para el frontend React. NO reimplementa la ciencia: envuelve las funciones que
ya existen en `backend/` y `optimizacion/`, y devuelve las geometrías ya
convertidas a **lat/lon** para que el cliente (react-leaflet) las use directo.

Ejecutar en desarrollo (desde la raíz del repo):
    uvicorn api.main:app --reload --port 8000

El estado del escenario se mantiene en memoria (herramienta de un solo usuario,
como la app de escritorio) y se persiste en `output/` con las mismas funciones
del backend, de modo que al reiniciar el servidor se puede retomar el último
escenario.
"""

import os
import sys

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# La raíz del repo debe estar en el path para importar backend/ y optimizacion/
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
OUTPUT_DIR = os.path.join(RAIZ, "output")

from backend.descargar_osm import descargar_mapa_osm
from backend.sumo_pipeline import ejecutar_pipeline_sumo
from backend.parsear_xml import (
    parsear_junctions, parsear_edificios, obtener_proyeccion,
    filtrar_junctions_rsu, convertir_xy_a_lonlat,
)
from backend.simulacion_sumo import ejecutar_simulacion_sumo, parsear_fcd
from backend.visibilidad import (
    generar_tuplas_visibilidad, guardar_tuplas_json,
    generar_tuplas_v2v, guardar_tuplas_v2v_json,
)
from backend.exportar_dat import exportar_dat_desde_memoria
from optimizacion.optimizar_rsu import optimizar


# ============================================================
# ESTADO EN MEMORIA (un escenario a la vez)
# ============================================================
STATE: dict = {
    "junctions": None,     # {id: {"x","y"}}
    "edificios": None,     # {id: [[x,y], ...]}
    "proy": None,          # proyección SUMO ↔ lon/lat
    "net_xml": None,
    "bbox": None,          # [min_lon, min_lat, max_lon, max_lat]
    "rsus": None,          # RSU filtradas {id: {"x","y","grado"}}
    "datos_fcd": None,     # {t: [{"id","x","y","speed",...}]}
    "tuplas_v2i": None,
    "matrices_v2v": None,
    "tuplas_v2v": None,
    "params": {},
}


# ============================================================
# HELPERS DE CONVERSIÓN A lat/lon
# ============================================================
def _proy():
    if STATE["proy"] is None:
        raise HTTPException(409, "No hay escenario cargado. Genera uno primero.")
    return STATE["proy"]


def _ll(x, y):
    """SUMO (x,y) → [lat, lon] redondeado."""
    lat, lon = convertir_xy_a_lonlat(x, y, STATE["proy"])
    return [round(lat, 6), round(lon, 6)]


def _edificios_geojson():
    """Edificios como lista de anillos [[lat,lon], ...] para el mapa."""
    return [[_ll(px, py) for px, py in verts]
            for verts in (STATE["edificios"] or {}).values() if len(verts) >= 3]


def _rsus_geojson(rsus):
    """RSU como [{id, lat, lon, grado}]."""
    out = []
    for rid, r in rsus.items():
        lat, lon = _ll(r["x"], r["y"])
        out.append({"id": str(rid), "lat": lat, "lon": lon, "grado": r.get("grado")})
    return out


def _bounds():
    """[[lat_min,lon_min],[lat_max,lon_max]] del escenario, para encuadrar el mapa."""
    o = STATE["proy"]["orig"]  # [lon_min, lat_min, lon_max, lat_max]
    return [[o[1], o[0]], [o[3], o[2]]]


# ============================================================
# APP
# ============================================================
app = FastAPI(title="SmartCityNet API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
def _cargar_output_existente():
    """Si hay un escenario previo en output/, lo carga para poder retomarlo."""
    import json
    try:
        net = os.path.join(OUTPUT_DIR, "mapa.net.xml")
        if not os.path.exists(net):
            return
        STATE["net_xml"] = net
        STATE["proy"] = obtener_proyeccion(net)
        with open(os.path.join(OUTPUT_DIR, "junctions_limpias.json"), encoding="utf-8") as f:
            STATE["junctions"] = json.load(f)
        with open(os.path.join(OUTPUT_DIR, "edificios_limpios.json"), encoding="utf-8") as f:
            STATE["edificios"] = json.load(f)
        v2i_path = os.path.join(OUTPUT_DIR, "tuplas_visibilidad.json")
        if os.path.exists(v2i_path):
            with open(v2i_path, encoding="utf-8") as f:
                d = json.load(f)
            STATE["rsus"] = d.get("rsus")
            STATE["tuplas_v2i"] = d.get("tuplas")
        v2v_path = os.path.join(OUTPUT_DIR, "tuplas_v2v.json")
        if os.path.exists(v2v_path):
            with open(v2v_path, encoding="utf-8") as f:
                d = json.load(f)
            STATE["matrices_v2v"] = d.get("matrices")
            STATE["tuplas_v2v"] = d.get("tuplas_v2v")
    except Exception:
        # Arranque sin escenario previo: no es error.
        pass


# ============================================================
# SCHEMAS
# ============================================================
class BBox(BaseModel):
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float


class ScenarioReq(BaseModel):
    bbox: BBox
    num_vehiculos: int = Field(100, ge=5, le=1000)
    tiempo_min: int = Field(120, ge=1, le=180)


class RsuReq(BaseModel):
    min_grado: int = Field(4, ge=2, le=8)
    radio_cluster: float = Field(20.0, ge=0, le=100)


class SimReq(BaseModel):
    radio_obu: float = Field(300.0, ge=50, le=500)
    step_min: int = Field(2, ge=1, le=30)
    bidireccional: bool = True


class OptReq(BaseModel):
    H: int = Field(3, ge=1, le=6)
    max_rsu: int | None = None


# ============================================================
# ENDPOINTS
# ============================================================
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/state")
def state():
    """Resumen de lo que hay cargado — para que el frontend rehidrate su vista."""
    s = STATE
    return {
        "tiene_escenario": s["junctions"] is not None,
        "tiene_rsus": s["rsus"] is not None,
        "tiene_simulacion": s["matrices_v2v"] is not None,
        "n_junctions": len(s["junctions"]) if s["junctions"] else 0,
        "n_edificios": len(s["edificios"]) if s["edificios"] else 0,
        "n_rsus": len(s["rsus"]) if s["rsus"] else 0,
        "bounds": _bounds() if s["proy"] else None,
    }


@app.get("/api/scenario/buildings")
def scenario_buildings():
    """Edificios del escenario actual (lat/lon) — capa base del mapa."""
    _proy()
    return {"edificios": _edificios_geojson(), "bounds": _bounds()}


@app.post("/api/scenario/generate")
def scenario_generate(req: ScenarioReq):
    """M1 — descarga OSM, corre SUMO y extrae junctions + edificios."""
    b = req.bbox
    osm_path, err = descargar_mapa_osm(b.min_lon, b.min_lat, b.max_lon, b.max_lat, OUTPUT_DIR)
    if err:
        raise HTTPException(400, f"Descarga OSM: {err}")

    periodo = (req.tiempo_min * 60) / req.num_vehiculos
    pasos = ejecutar_pipeline_sumo(osm_path, OUTPUT_DIR,
                                   num_vehiculos=req.num_vehiculos, periodo_salida=periodo)
    if any(not p["exito"] for p in pasos):
        fallo = next(p for p in pasos if not p["exito"])
        raise HTTPException(500, f"SUMO ({fallo['paso']}): {fallo['mensaje']}")

    net = os.path.join(OUTPUT_DIR, "mapa.net.xml")
    poly = os.path.join(OUTPUT_DIR, "mapa.poly.xml")
    junctions, ej = parsear_junctions(net, OUTPUT_DIR)
    edificios, ee = parsear_edificios(poly, OUTPUT_DIR)
    if ej or ee:
        raise HTTPException(500, f"Parseo: {ej or ee}")

    STATE.update({
        "junctions": junctions, "edificios": edificios,
        "proy": obtener_proyeccion(net), "net_xml": net,
        "bbox": [b.min_lon, b.min_lat, b.max_lon, b.max_lat],
        "rsus": None, "datos_fcd": None, "tuplas_v2i": None,
        "matrices_v2v": None, "tuplas_v2v": None,
        "params": {"num_vehiculos": req.num_vehiculos, "tiempo_min": req.tiempo_min},
    })
    return {
        "n_junctions": len(junctions), "n_edificios": len(edificios),
        "edificios": _edificios_geojson(), "bounds": _bounds(),
        "pasos": [{"paso": p["paso"], "exito": p["exito"], "mensaje": p["mensaje"]} for p in pasos],
    }


@app.post("/api/rsu/filter")
def rsu_filter(req: RsuReq):
    """M1 — filtra las junctions a RSU candidatas (grado + clustering)."""
    if STATE["junctions"] is None:
        raise HTTPException(409, "Genera un escenario primero.")
    rsus = filtrar_junctions_rsu(STATE["junctions"], STATE["net_xml"],
                                 min_grado=req.min_grado, radio_cluster=req.radio_cluster)
    STATE["rsus"] = rsus
    n_orig = len(STATE["junctions"])
    return {
        "rsus": _rsus_geojson(rsus),
        "n_candidatas": len(rsus), "n_junctions": n_orig,
        "reduccion_pct": round(100 * (1 - len(rsus) / max(n_orig, 1)), 1),
    }


@app.post("/api/simulate")
def simulate(req: SimReq):
    """M2 — corre SUMO, calcula LoS y genera tuplas V2I + V2V + matrices."""
    if STATE["rsus"] is None:
        raise HTTPException(409, "Filtra las RSU primero.")

    tiempo_sim = STATE["params"].get("tiempo_min", 120) * 60
    step = req.step_min * 60.0
    fcd_path, err = ejecutar_simulacion_sumo(OUTPUT_DIR, tiempo_sim, periodo_fcd=step)
    if err:
        raise HTTPException(500, f"Simulación SUMO: {err}")
    datos_fcd, ef = parsear_fcd(fcd_path, step)
    if ef:
        raise HTTPException(500, f"Parseo FCD: {ef}")

    tuplas_v2i, est_v2i = generar_tuplas_visibilidad(
        datos_fcd, STATE["rsus"], STATE["edificios"], radio_obu=req.radio_obu)
    guardar_tuplas_json(tuplas_v2i, est_v2i, STATE["rsus"], OUTPUT_DIR)

    tuplas_v2v, matrices_v2v, est_v2v = generar_tuplas_v2v(
        datos_fcd, STATE["edificios"], radio_obu=req.radio_obu,
        bidireccional=req.bidireccional)
    guardar_tuplas_v2v_json(tuplas_v2v, matrices_v2v, est_v2v, OUTPUT_DIR)

    STATE.update({
        "datos_fcd": datos_fcd, "tuplas_v2i": tuplas_v2i,
        "matrices_v2v": matrices_v2v, "tuplas_v2v": tuplas_v2v,
        "params": {**STATE["params"], "radio_obu": req.radio_obu,
                   "step_min": req.step_min, "bidireccional": req.bidireccional},
    })
    timesteps = sorted(float(t) for t in datos_fcd.keys())
    return {
        "v2i": {"total_tuplas": est_v2i["total_tuplas"],
                "total_timesteps": est_v2i["total_timesteps"],
                "n_rsus": len(est_v2i["resumen_por_rsu"])},
        "v2v": {"total_tuplas": est_v2v["total_tuplas_v2v"],
                "pares_en_rango": est_v2v["total_pares_en_rango"],
                "n_vehiculos": len(est_v2v["resumen_por_vehiculo"]),
                "bidireccional": est_v2v["bidireccional"]},
        "timesteps": timesteps,
    }


@app.get("/api/connectivity")
def connectivity(t: float):
    """Conectividad de un instante t: vehículos + enlaces V2I y V2V (lat/lon)."""
    if STATE["datos_fcd"] is None:
        raise HTTPException(409, "Corre la simulación primero.")
    # localizar la clave del instante (las claves pueden ser float o str)
    fcd = STATE["datos_fcd"]
    clave = next((k for k in fcd if abs(float(k) - t) < 1e-6), None)
    if clave is None:
        raise HTTPException(404, f"Instante {t} no encontrado.")

    veh = {v["id"]: _ll(v["x"], v["y"]) for v in fcd[clave]}
    vehiculos = [{"id": f"V{vid}", "lat": ll[0], "lon": ll[1]} for vid, ll in veh.items()]

    def _rsu_ll(rid):
        r = STATE["rsus"].get(rid) if STATE["rsus"] else None
        return _ll(r["x"], r["y"]) if r else None

    v2i = []
    for tp in STATE["tuplas_v2i"]:
        if abs(float(tp["t"]) - t) >= 1e-6:
            continue
        a = veh.get(tp["vehiculo"].replace("V", ""))
        b = _rsu_ll(tp["rsu"])
        if a and b:
            v2i.append({"v": tp["vehiculo"], "rsu": str(tp["rsu"]), "a": a, "b": b})

    pares = set()
    v2v = []
    for tp in (STATE["tuplas_v2v"] or []):
        if abs(float(tp["t"]) - t) >= 1e-6:
            continue
        i, j = tp["vehiculo_i"].replace("V", ""), tp["vehiculo_j"].replace("V", "")
        key = tuple(sorted([i, j]))
        if key in pares or i not in veh or j not in veh:
            continue
        pares.add(key)
        v2v.append({"a": veh[i], "b": veh[j]})

    return {"t": t, "vehiculos": vehiculos, "v2i": v2i, "v2v": v2v}


@app.post("/api/optimize")
def optimize(req: OptReq):
    """M3 — construye el CVR, resuelve con docplex/CPLEX y devuelve el despliegue."""
    if STATE["matrices_v2v"] is None or STATE["tuplas_v2i"] is None:
        raise HTTPException(409, "Corre la simulación primero.")
    dat = os.path.join(RAIZ, "optimizacion", "rsu_backend.dat")
    datos = exportar_dat_desde_memoria(
        STATE["matrices_v2v"], STATE["tuplas_v2i"], STATE["rsus"], dat,
        H=req.H, max_rsu=req.max_rsu, solo_rsu_conectados=True)
    res = optimizar(datos, mostrar_log=False)

    desplegadas = []
    if res["objetivo"] is not None:
        ids = set(str(r) for r in res["seleccionados_backend"])
        desplegadas = [r for r in _rsus_geojson(STATE["rsus"]) if r["id"] in ids]

    return {
        "resumen": datos["resumen"],
        "objetivo": res["objetivo"],
        "n_desplegadas": res["n_rsu_elegidos"],
        "status": res["status"],
        "desplegadas": desplegadas,
        "candidatas": _rsus_geojson(STATE["rsus"]),
    }
