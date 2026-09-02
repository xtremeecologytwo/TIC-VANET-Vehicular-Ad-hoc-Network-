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
from backend.multisalto import analizar_timestep
from optimizacion.optimizar_rsu import optimizar
from api import cronometro as cron


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
    """[[lat_min,lon_min],[lat_max,lon_max]] del escenario, para encuadrar el mapa.

    Usa las esquinas de convBoundary proyectadas con la proyección REAL (no
    origBoundary, que es la descarga original sin recortar), de modo que el
    encuadre coincida con la extensión efectiva de la red y de los edificios.
    """
    c = STATE["proy"]["conv"]  # [x_min, y_min, x_max, y_max]
    a = _ll(c[0], c[1])
    b = _ll(c[2], c[3])
    return [[min(a[0], b[0]), min(a[1], b[1])], [max(a[0], b[0]), max(a[1], b[1])]]


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
        # Cargar el FCD (posiciones vehiculares) para que la animación de
        # conectividad funcione al retomar un escenario ya guardado. El paso de
        # muestreo se infiere de la separación entre snapshots de las matrices.
        fcd_path = os.path.join(OUTPUT_DIR, "fcd.xml")
        if os.path.exists(fcd_path) and STATE["matrices_v2v"]:
            keys = sorted(float(k) for k in STATE["matrices_v2v"].keys())
            step = (keys[1] - keys[0]) if len(keys) >= 2 else 120.0
            datos, _ = parsear_fcd(fcd_path, step)
            STATE["datos_fcd"] = datos
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
    # MaxR del modelo: nº máximo de RSU que se pueden desplegar. `null` (por
    # defecto) = sin límite efectivo; `exportar_dat` lo fija al nº de RSU
    # candidatas, con lo que la restricción existe pero nunca ata.
    max_rsu: int | None = Field(None, ge=1)
    # Límite de tiempo del solver, en segundos. `null` = SIN LÍMITE: CPLEX busca
    # hasta demostrar el óptimo, tarde lo que tarde (la petición HTTP queda
    # esperando todo ese rato). Con un número, al agotarlo devuelve la mejor
    # solución encontrada en vez de seguir probando optimalidad.
    limite_tiempo: float | None = Field(60, ge=5, le=3600)


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
    # Un escenario nuevo abre una sesión de medición nueva: los tiempos de las
    # etapas siguientes se acumulan sobre esta corrida (ver api/cronometro.py).
    cron.nueva_sesion(f"escenario nuevo · {req.num_vehiculos} vehiculos · "
                      f"{req.tiempo_min} min")
    with cron.etapa("M1 - Generar escenario"):
        with cron.subetapa("Descarga OSM"):
            osm_path, err = descargar_mapa_osm(b.min_lon, b.min_lat,
                                               b.max_lon, b.max_lat, OUTPUT_DIR)
        if err:
            raise HTTPException(400, f"Descarga OSM: {err}")

        periodo = (req.tiempo_min * 60) / req.num_vehiculos
        with cron.subetapa("SUMO (netconvert/polyconvert/trips)"):
            pasos = ejecutar_pipeline_sumo(osm_path, OUTPUT_DIR,
                                           num_vehiculos=req.num_vehiculos,
                                           periodo_salida=periodo)
        if any(not p["exito"] for p in pasos):
            fallo = next(p for p in pasos if not p["exito"])
            raise HTTPException(500, f"SUMO ({fallo['paso']}): {fallo['mensaje']}")

        net = os.path.join(OUTPUT_DIR, "mapa.net.xml")
        poly = os.path.join(OUTPUT_DIR, "mapa.poly.xml")
        with cron.subetapa("Parseo junctions + edificios"):
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
        with cron.subetapa("Conversion a lat/lon (respuesta)"):
            respuesta = {
                "n_junctions": len(junctions), "n_edificios": len(edificios),
                "edificios": _edificios_geojson(), "bounds": _bounds(),
                "pasos": [{"paso": p["paso"], "exito": p["exito"],
                           "mensaje": p["mensaje"]} for p in pasos],
            }
    return respuesta


@app.post("/api/rsu/filter")
def rsu_filter(req: RsuReq):
    """M1 — filtra las junctions a RSU candidatas (grado + clustering)."""
    if STATE["junctions"] is None:
        raise HTTPException(409, "Genera un escenario primero.")
    with cron.etapa(f"Filtrar RSU candidatas (grado>={req.min_grado}, "
                    f"cluster={req.radio_cluster:g} m)"):
        with cron.subetapa("Grado + clustering espacial"):
            rsus = filtrar_junctions_rsu(STATE["junctions"], STATE["net_xml"],
                                         min_grado=req.min_grado,
                                         radio_cluster=req.radio_cluster)
        STATE["rsus"] = rsus
        n_orig = len(STATE["junctions"])
        respuesta = {
            "rsus": _rsus_geojson(rsus),
            "n_candidatas": len(rsus), "n_junctions": n_orig,
            "reduccion_pct": round(100 * (1 - len(rsus) / max(n_orig, 1)), 1),
        }
    return respuesta


@app.post("/api/simulate")
def simulate(req: SimReq):
    """M2 — corre SUMO, calcula LoS y genera tuplas V2I + V2V + matrices."""
    if STATE["rsus"] is None:
        raise HTTPException(409, "Filtra las RSU primero.")

    tiempo_sim = STATE["params"].get("tiempo_min", 120) * 60
    step = req.step_min * 60.0
    with cron.etapa(f"M2 - Simular conectividad (radio {req.radio_obu:g} m, "
                    f"muestreo {req.step_min} min)"):
        with cron.subetapa("Simulacion SUMO (trafico + FCD)"):
            fcd_path, err = ejecutar_simulacion_sumo(OUTPUT_DIR, tiempo_sim,
                                                     periodo_fcd=step)
        if err:
            raise HTTPException(500, f"Simulación SUMO: {err}")
        with cron.subetapa("Parseo del FCD"):
            datos_fcd, ef = parsear_fcd(fcd_path, step)
        if ef:
            raise HTTPException(500, f"Parseo FCD: {ef}")

        with cron.subetapa("LoS V2I (tuplas de visibilidad)"):
            tuplas_v2i, est_v2i = generar_tuplas_visibilidad(
                datos_fcd, STATE["rsus"], STATE["edificios"], radio_obu=req.radio_obu)
            guardar_tuplas_json(tuplas_v2i, est_v2i, STATE["rsus"], OUTPUT_DIR)

        with cron.subetapa("LoS V2V (matriz A por instante)"):
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


@app.get("/api/timesteps")
def timesteps():
    """Lista de instantes disponibles para la animación de conectividad."""
    src = STATE["datos_fcd"] or STATE["matrices_v2v"]
    if not src:
        return {"timesteps": []}
    return {"timesteps": sorted(float(t) for t in src.keys())}


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
    # MaxR: si el frontend no manda número, `exportar_dat` usa el nº de RSU
    # candidatas conectadas, con lo que la restricción no ata (comportamiento
    # por defecto). El nombre de la etapa deja constancia de cuál se midió.
    etiqueta_maxr = "sin limite" if req.max_rsu is None else str(req.max_rsu)
    etiqueta_lim = ("sin limite" if req.limite_tiempo is None
                    else f"{req.limite_tiempo:g} s")
    with cron.etapa(f"M3 - Optimizar despliegue (H={req.H}, MaxR={etiqueta_maxr}, "
                    f"tope={etiqueta_lim})"):
        with cron.subetapa("Multisalto + construccion del CVR (.dat)"):
            datos = exportar_dat_desde_memoria(
                STATE["matrices_v2v"], STATE["tuplas_v2i"], STATE["rsus"], dat,
                H=req.H, max_rsu=req.max_rsu, solo_rsu_conectados=True)
        with cron.subetapa("Solver CPLEX (branch & bound)") as medida:
            res = optimizar(datos, mostrar_log=False,
                            limite_tiempo=req.limite_tiempo)
        # Tiempo del MOTOR (sin el armado del modelo): es el que hay que
        # comparar contra el límite. Si docplex no lo diera, cae al reloj.
        seg_motor = res.get("segundos_solver")
        if seg_motor is None:
            seg_motor = medida.segundos
        # Cómo terminó el solver: lo necesita el frontend para saber si el
        # tiempo medido es real o es simplemente el límite que se le puso.
        info = _interpretar_status(res["status"], seg_motor, req.limite_tiempo)
        cron.nota(f"status: {res['status']} -> {info['etiqueta']}; "
                  f"motor {seg_motor:.2f} s de un tope de {etiqueta_lim}")

        desplegadas = []
        if res["objetivo"] is not None:
            ids = set(str(r) for r in res["seleccionados_backend"])
            desplegadas = [r for r in _rsus_geojson(STATE["rsus"]) if r["id"] in ids]

        rep = res.get("reparto")
        if rep:
            cron.nota(f"cobertura: {rep['cobertura_pct']:.2f} % "
                      f"({rep['conectados']:.0f}/{rep['n_pares']} pares) | "
                      f"directos {rep['directos']:.0f} | "
                      f"multisalto {rep['multisalto']:.0f} | "
                      f"desconectados {rep['desconectados']:.0f}")

        respuesta = {
            "resumen": datos["resumen"],
            "objetivo": res["objetivo"],
            "n_desplegadas": res["n_rsu_elegidos"],
            "status": res["status"],
            "cobertura": rep,
            "solver": {
                "status": res["status"],
                "segundos": round(float(seg_motor), 2),        # solo el motor
                "segundos_total": round(medida.segundos, 2),   # armado + motor
                "limite_tiempo": req.limite_tiempo,
                **info,
            },
            "desplegadas": desplegadas,
            "candidatas": _rsus_geojson(STATE["rsus"]),
        }
    # Fin del flujo M1→M3: imprime la tabla con la suma de todas las etapas.
    cron.resumen()
    return respuesta


def _interpretar_status(status: str, segundos: float, limite: float | None) -> dict:
    """
    Traduce el `status` crudo de CPLEX a algo que se pueda leer en la interfaz.

    CPLEX devuelve frases como "integer optimal solution" o "time limit
    exceeded". Lo que le importa a quien mira la pantalla es una sola cosa:
    ¿el resultado está **demostrado** como el mejor, o el solver se quedó sin
    tiempo y entregó lo mejor que había encontrado?

    Parámetros:
        status: cadena tal cual la devuelve `optimizar()`.
        segundos: lo que tardó realmente el solver (medido con el cronómetro).
        limite: el `limite_tiempo` que se le pasó a CPLEX (None = sin límite).

    Retorna:
        dict con "etiqueta" (frase corta), "detalle" (qué significa),
        "optimo" (bool) y "corto_por_tiempo" (bool).
    """
    s = (status or "").lower()
    optimo = "optimal" in s
    # CPLEX dice "time limit exceeded"; como red de seguridad, si el solver
    # consumió prácticamente todo el presupuesto sin declararse óptimo, se
    # trata igual (el reloj mandó, no la dificultad real del problema).
    corto = ("time limit" in s) or (
        limite is not None and not optimo and segundos >= limite * 0.97)

    if optimo:
        etiqueta = "Óptimo demostrado"
        detalle = ("CPLEX terminó solo: no existe un despliegue mejor."
                   if "tolerance" not in s else
                   "CPLEX terminó solo, dentro de su tolerancia estándar (0,01 %).")
    elif corto:
        etiqueta = "Cortado por tiempo"
        tope = f"el límite de {limite:g} s" if limite is not None else "el tiempo"
        detalle = (f"Agotó {tope}. La solución sirve, pero podría existir "
                   f"una mejor.")
    elif "community-limit-exceeded" in s:
        etiqueta = "Modelo demasiado grande"
        detalle = "Falta el motor completo de CPLEX Studio (la edición Community no basta)."
    else:
        etiqueta = status or "sin solución"
        detalle = "El solver no devolvió una solución utilizable."

    return {"etiqueta": etiqueta, "detalle": detalle,
            "optimo": optimo, "corto_por_tiempo": corto}


@app.get("/api/tuples/v2i")
def tuples_v2i(limit: int = 500):
    """Tuplas de visibilidad V2I ⟨t, V, RSU⟩ (paginadas con `limit`)."""
    if STATE["tuplas_v2i"] is None:
        raise HTTPException(409, "Corre la simulación primero.")
    t = STATE["tuplas_v2i"]
    return {"total": len(t), "tuplas": t[:limit]}


@app.get("/api/tuples/v2v")
def tuples_v2v(limit: int = 500):
    """Tuplas de conectividad V2V ⟨t, Vi, Vj⟩ (paginadas con `limit`)."""
    if STATE["tuplas_v2v"] is None:
        raise HTTPException(409, "Corre la simulación primero.")
    t = STATE["tuplas_v2v"]
    return {"total": len(t), "tuplas": t[:limit]}


def _mkey(t: float):
    """Localiza la clave del instante t en matrices_v2v (float o str)."""
    m = STATE["matrices_v2v"] or {}
    return next((k for k in m if abs(float(k) - t) < 1e-6), None)


@app.get("/api/multihop")
def multihop(t: float, H: int = 3):
    """
    Análisis de un instante: matrices A (V2V), B (V2I), acumuladas R_h,
    primera aparición S_h, desconexión D_H y vector d. Alimenta tanto el visor
    de matrices A/B como el de multisalto.
    """
    if STATE["matrices_v2v"] is None or STATE["rsus"] is None:
        raise HTTPException(409, "Corre la simulación primero.")
    key = _mkey(t)
    if key is None:
        raise HTTPException(404, f"Instante {t} no encontrado.")
    rsu_ids = sorted(STATE["rsus"].keys())
    res = analizar_timestep(STATE["matrices_v2v"][key], STATE["tuplas_v2i"],
                            float(t), rsu_ids, H=H, forzar_simetria=True)
    return {
        "t": t, "H": H,
        "vehiculos": res["vehiculos"],
        "rsu_ids": [str(r) for r in res["rsu_ids"]],
        "A": res["A"].tolist(),
        "B": res["B"].tolist(),
        "R": [m.tolist() for m in res["R"]],
        "S": [m.tolist() for m in res["S"]],
        "D": res["D"].tolist(),
        "d": res["d"].tolist(),
        "resumen": res["resumen"],
    }
