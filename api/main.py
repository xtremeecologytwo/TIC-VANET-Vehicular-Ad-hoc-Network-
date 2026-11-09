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
# Donde se guardan las corridas. `output/` era la unica carpeta de la web:
# cada "Generar escenario" la pisaba y no quedaba rastro de la anterior. Ahora
# cada escenario de la web tiene su carpeta bajo datos/corridas/, como las del
# CLI; `output/` solo se lee si existe de antes (compatibilidad).
DATOS = os.path.join(RAIZ, "datos")
CORRIDAS = os.path.join(DATOS, "corridas")
CATALOGO = os.path.join(DATOS, "catalogo.sqlite")
PUNTERO_WEB = os.path.join(DATOS, "web_ultima.txt")   # ultima carpeta de la web
OUTPUT_DIR = os.path.join(RAIZ, "output")             # legado

from backend.procesos import cancelar_todo
# El flujo M1->M2 vive en el nucleo, no aqui: la API y el CLI son dos
# clientes del mismo codigo (ver backend/flujo.py).
from backend import flujo
from backend.sumo_pipeline import SEMILLA_POR_DEFECTO
from backend.parsear_xml import obtener_proyeccion, convertir_xy_a_lonlat
from backend.simulacion_sumo import parsear_fcd
from backend.exportar_dat import exportar_dat_desde_memoria
# La web guarda cada corrida igual que el CLI: carpeta propia, manifest.json y
# fila en el catalogo (ver backend/catalogo.py). El CLI queda para los lotes.
from backend import almacen
# Capa fisica de 802.11p (notas del tutor): radios r80/r90, Γ_H y capacidad.
from backend import capa_fisica as fisica
from backend import descargar_osm
import signal
from backend.catalogo import (Catalogo, registrar_corrida_completa,
                              manifest_actualizar, manifest_leer)
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
    # Objetos del nucleo (backend/flujo.py) de la ultima corrida. STATE es
    # solo una CACHE para que la interfaz pueda pedir instantes sueltos sin
    # rehacer el flujo; la logica ya no vive aqui.
    "escenario": None,
    "candidatas": None,
    "conectividad": None,
    # Carpeta de la corrida en curso (datos/corridas/web_...). Ahi van todos
    # los archivos y el manifest.json; es lo que se retoma al reiniciar.
    "carpeta": None,
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


# Tope opcional de edificios enviados al navegador para DIBUJAR.
# Por defecto 0 = SIN TOPE: se mandan todos, que es lo que hace que el mapa se
# vea completo. Con áreas muy grandes (~190 000 polígonos, ~53 MB de JSON) el
# navegador puede ir lento; si eso molesta, poner aquí un número activa un
# muestreo uniforme. NUNCA afecta al cálculo: la línea de vista usa siempre el
# conjunto completo del backend.
MAX_EDIFICIOS_MAPA = int(os.environ.get("MAX_EDIFICIOS_MAPA", 0))


def _edificios_geojson():
    """Edificios como lista de anillos [[lat,lon], ...] para el mapa."""
    todos = [v for v in (STATE["edificios"] or {}).values() if len(v) >= 3]
    # Muestreo uniforme (uno de cada k) solo si se pidió un tope explícito.
    if MAX_EDIFICIOS_MAPA and len(todos) > MAX_EDIFICIOS_MAPA:
        paso = len(todos) // MAX_EDIFICIOS_MAPA + 1
        todos = todos[::paso]
    return [[_ll(px, py) for px, py in verts] for verts in todos]


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


def _bbox_de_la_red(net_xml: str) -> tuple:
    """
    Recupera el rectangulo geografico de un .net.xml ya generado.

    SUMO lo guarda en el atributo `origBoundary` del elemento <location>, como
    "oeste,sur,este,norte". Se usa al rehidratar: el bbox original no se guarda
    en ningun JSON, pero la red si lo lleva dentro.
    """
    import re
    try:
        with open(net_xml, encoding="utf-8", errors="ignore") as f:
            for _ in range(40):
                linea = f.readline()
                if "origBoundary=" in linea:
                    v = re.search(r'origBoundary="([^"]+)"', linea).group(1)
                    w, s_, e, n_ = (float(x) for x in v.split(","))
                    return (w, s_, e, n_)
    except OSError:
        pass
    return (0.0, 0.0, 0.0, 0.0)


def _carpeta_previa() -> str | None:
    """
    La carpeta que se retoma al arrancar: la ultima de la web, si su red
    sigue en disco; si no, `output/` de versiones anteriores.
    """
    try:
        with open(PUNTERO_WEB, encoding="utf-8") as f:
            c = f.read().strip()
        if c and os.path.isfile(os.path.join(c, "mapa.net.xml")):
            return c
    except OSError:
        pass
    if os.path.isfile(os.path.join(OUTPUT_DIR, "mapa.net.xml")):
        return OUTPUT_DIR
    return None


def _apuntar_web(carpeta: str) -> None:
    os.makedirs(DATOS, exist_ok=True)
    with open(PUNTERO_WEB, "w", encoding="utf-8") as f:
        f.write(carpeta)


def abortar_todo() -> list[str]:
    """
    Corta todo lo que este en marcha: subprocesos de SUMO y descargas de OSM.

    Lo llaman "Generar escenario" (un escenario nuevo es NUEVO) y el
    manejador de Ctrl+C. Devuelve que subprocesos mato, para el log.
    """
    cortados = cancelar_todo()
    descargar_osm.abortar()
    return cortados


@app.on_event("startup")
def _ctrl_c_que_pare():
    """
    Hace que Ctrl+C pare la API aunque haya una peticion bloqueada.

    uvicorn, al recibir la senal, deja de aceptar conexiones y ESPERA a que
    terminen las peticiones en curso. Los endpoints corren en hilos de anyio
    -que no son daemon- y uno bloqueado en una descarga de Overpass o en
    netconvert no vuelve nunca: el proceso se queda vivo con "Waiting for
    background tasks". Visto en consola, mas de una vez.

    Aqui se envuelve el manejador de uvicorn: antes de cederle la senal se
    matan los subprocesos y se abortan las descargas, de modo que esas
    peticiones fallan en ~1 s y el cierre puede terminar. Solo se puede
    instalar desde el hilo principal, que es donde Starlette ejecuta los
    handlers de arranque sincronos.
    """
    import threading
    if threading.current_thread() is not threading.main_thread():
        return
    senales = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGBREAK"):
        senales.append(signal.SIGBREAK)
    for sig in senales:
        previo = signal.getsignal(sig)

        def manejador(num, marco, _previo=previo):
            cortados = abortar_todo()
            if cortados:
                print(f"  [cierre] cortados: {', '.join(cortados)}", flush=True)
            if callable(_previo):
                _previo(num, marco)

        try:
            signal.signal(sig, manejador)
        except (ValueError, OSError):
            pass


@app.on_event("startup")
def _cargar_output_existente():
    """Si hay un escenario previo en disco, lo carga para poder retomarlo."""
    import json
    try:
        carpeta = _carpeta_previa()
        if not carpeta:
            return
        net = os.path.join(carpeta, "mapa.net.xml")
        # Los parametros reales de la corrida estan en su manifest.json (lo
        # completa cada clic). Sin manifest -la carpeta output/ de antes- se
        # usan los valores por defecto, que es lo que habia.
        man = manifest_leer(carpeta)
        STATE["carpeta"] = carpeta
        STATE["net_xml"] = net
        STATE["proy"] = obtener_proyeccion(net)
        with open(os.path.join(carpeta, "junctions_limpias.json"), encoding="utf-8") as f:
            STATE["junctions"] = json.load(f)
        with open(os.path.join(carpeta, "edificios_limpios.json"), encoding="utf-8") as f:
            STATE["edificios"] = json.load(f)

        bbox = tuple(man["bbox"]) if man.get("bbox") else _bbox_de_la_red(net)
        STATE["bbox"] = list(bbox)
        STATE["escenario"] = flujo.Escenario(
            carpeta=carpeta, bbox=bbox,
            num_vehiculos=int(man.get("vehiculos", 0)),
            tiempo_min=int(man.get("duracion_min", 120)),
            semilla=int(man.get("semilla", SEMILLA_POR_DEFECTO)),
            osm_path=os.path.join(carpeta, "map.osm"), net_xml=net,
            poly_xml=os.path.join(carpeta, "mapa.poly.xml"),
            junctions=STATE["junctions"], edificios=STATE["edificios"],
            proy=STATE["proy"], pasos=[], claves=almacen.claves_leer(carpeta),
        )
        STATE["params"] = {"num_vehiculos": STATE["escenario"].num_vehiculos,
                           "tiempo_min": STATE["escenario"].tiempo_min,
                           "semilla": STATE["escenario"].semilla}

        d1 = d2 = None
        v2i_path = os.path.join(carpeta, "tuplas_visibilidad.json")
        if os.path.exists(v2i_path):
            with open(v2i_path, encoding="utf-8") as f:
                d1 = json.load(f)
            STATE["rsus"] = d1.get("rsus")
            STATE["tuplas_v2i"] = d1.get("tuplas")
            if STATE["rsus"]:
                STATE["candidatas"] = flujo.Candidatas(
                    rsus=STATE["rsus"],
                    min_grado=int(man.get("min_grado", 4)),
                    radio_cluster=float(man.get("radio_cluster", 20.0)),
                    n_junctions=len(STATE["junctions"] or {}))
        v2v_path = os.path.join(carpeta, "tuplas_v2v.json")
        if os.path.exists(v2v_path):
            with open(v2v_path, encoding="utf-8") as f:
                d2 = json.load(f)
            STATE["matrices_v2v"] = d2.get("matrices")
            STATE["tuplas_v2v"] = d2.get("tuplas_v2v")
        # Cargar el FCD (posiciones vehiculares) para que la animación de
        # conectividad funcione al retomar un escenario ya guardado. El paso de
        # muestreo se infiere de la separación entre snapshots de las matrices.
        fcd_path = os.path.join(carpeta, "fcd.xml")
        if os.path.exists(fcd_path) and STATE["matrices_v2v"]:
            keys = sorted(float(k) for k in STATE["matrices_v2v"].keys())
            step = (keys[1] - keys[0]) if len(keys) >= 2 else 120.0
            datos, _ = parsear_fcd(fcd_path, step)
            STATE["datos_fcd"] = datos
        if d1 and d2 and STATE["datos_fcd"] is not None:
            # Con los dos JSON y la traza se reconstruye la Conectividad
            # entera: asi M3 puede registrar la corrida aunque la API se haya
            # reiniciado entre M2 y M3.
            con = flujo.Conectividad(
                datos_fcd=STATE["datos_fcd"], tuplas_v2i=STATE["tuplas_v2i"],
                tuplas_v2v=STATE["tuplas_v2v"], matrices_v2v=STATE["matrices_v2v"],
                est_v2i=d1.get("parametros", {}), est_v2v=d2.get("parametros", {}),
                radio_obu=float(man.get("radio_obu", 300.0)),
                step_min=int(man.get("muestreo_min", 2)),
                bidireccional=bool(man.get("bidireccional", True)))
            STATE["conectividad"] = con
            STATE["params"].update({"radio_obu": con.radio_obu,
                                    "step_min": con.step_min,
                                    "bidireccional": con.bidireccional})
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
    # Topes altos a propósito: el cuello de botella real no es la API sino
    # SUMO y el cálculo de línea de vista. Ver el README para qué esperar
    # a partir de unos miles de vehículos.
    num_vehiculos: int = Field(100, ge=5, le=1_000_000)
    tiempo_min: int = Field(120, ge=1, le=240)   # hasta 4 horas simuladas
    # SEMILLA del escenario. Fija la generacion de rutas (randomTrips) y la
    # simulacion (sumo): con la misma semilla y los mismos parametros, la traza
    # se repite exactamente. `null` toma SEMILLA_POR_DEFECTO (42, la del
    # articulo V5). Es lo que permite comparar configuraciones sobre la MISMA
    # movilidad y rehacer una corrida meses despues.
    semilla: int | None = Field(None, ge=0)


class RsuReq(BaseModel):
    min_grado: int = Field(4, ge=2, le=8)
    radio_cluster: float = Field(20.0, ge=0, le=100)


class SimReq(BaseModel):
    # Minimo 10 m: con 27 Mb/s e interferente, r90 es de 20 m (nota del tutor).
    radio_obu: float = Field(300.0, ge=10, le=500)
    step_min: int = Field(2, ge=1, le=30)
    bidireccional: bool = True
    # De donde salio el radio, si vino del panel de capa fisica (solo se anota
    # en el manifest; no cambia el calculo).
    fisica: dict | None = None


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
    # Multi-objetivo lexicográfico de CPLEX: primero la cobertura, y entre las
    # soluciones que la alcanzan, la que use menos RSU. `false` vuelve a la
    # suma ponderada clásica (útil para comparar).
    lexicografico: bool = True
    # ---- Capa fisica (opcional; None = valores clasicos) ----
    # P[1..H] explicitos: los Γ_h del experimento multisalto del tutor en vez
    # de 1..H. Se recortan a H si vienen de mas.
    penalizaciones: list[float] | None = None
    # Cap[r] y L[s][v] en la MISMA unidad (kb/s): α·C₀ de la nota de capacidad
    # y la carga por vehiculo elegida en el panel.
    cap_kbps: float | None = Field(None, gt=0)
    carga_kbps: float | None = Field(None, gt=0)
    # Etiqueta de la configuracion fisica (tasa, bytes, criterio...), para el manifest.
    fisica: dict | None = None


def _parametros_fisicos(req: "OptReq") -> dict:
    """kwargs de `construir_datos_opl` que vienen del panel de capa fisica; vacio = como siempre."""
    extra: dict = {}
    if req.penalizaciones is not None:
        if len(req.penalizaciones) < req.H:
            raise HTTPException(400, f"penalizaciones trae {len(req.penalizaciones)} valores y H={req.H}")
        extra["penalizaciones"] = [float(x) for x in req.penalizaciones[:req.H]]
    if req.cap_kbps is not None:
        extra["cap_real"] = float(req.cap_kbps)
    if req.carga_kbps is not None:
        extra["carga_default"] = float(req.carga_kbps)
    return extra


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
        "carpeta": s.get("carpeta"),
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

    # "Escenario nuevo" quiere decir NUEVO: si quedaba una corrida a medias
    # —porque se pulsó el botón otra vez, o porque una pestaña se recargó— se
    # corta antes de empezar. Si no, las dos se pelean por la CPU y la RAM y las
    # dos van lentas; y no se pueden parar desde la consola, porque el endpoint
    # corre en un hilo del threadpool y un hilo de Python no se interrumpe.
    # Lo que sí se puede matar es el subproceso de SUMO, que es lo que de verdad
    # consume la máquina (ver backend/procesos.py).
    cortados = abortar_todo()

    # Un escenario nuevo abre una sesión de medición nueva: los tiempos de las
    # etapas siguientes se acumulan sobre esta corrida (ver api/cronometro.py).
    # La semilla se resuelve UNA vez y se usa en randomTrips y en sumo, para
    # que las dos etapas pertenezcan al mismo escenario reproducible.
    semilla = SEMILLA_POR_DEFECTO if req.semilla is None else req.semilla

    cron.nueva_sesion(f"escenario nuevo · {req.num_vehiculos} vehiculos · "
                      f"{req.tiempo_min} min · semilla {semilla}")
    if cortados:
        cron.nota(f"corrida anterior cortada: {', '.join(cortados)}")

    # El estado en memoria del escenario viejo deja de valer en cuanto se
    # empieza otro: si M1 falla a mitad, mejor no tener nada que tener una
    # mezcla de los dos.
    STATE["junctions"] = None
    STATE["edificios"] = None
    STATE["rsus"] = None
    # Carpeta propia por escenario, como en el CLI. Lleva la hora porque los
    # parametros del filtrado y de M2 aun no se conocen, y dos sesiones con la
    # misma demanda no deben pisarse. Los archivos pesados no se duplican: si
    # la red o las rutas ya se calcularon, llegan como enlaces del almacen.
    from datetime import datetime
    etiqueta = (f"web_v{req.num_vehiculos}_t{req.tiempo_min}_s{semilla}_"
                f"{datetime.now():%Y%m%d-%H%M%S}")
    carpeta = os.path.join(CORRIDAS, etiqueta)
    os.makedirs(carpeta, exist_ok=True)
    bbox = (b.min_lon, b.min_lat, b.max_lon, b.max_lat)
    try:
        esc = flujo.generar_escenario(
            bbox=bbox, carpeta=carpeta, num_vehiculos=req.num_vehiculos,
            tiempo_min=req.tiempo_min, semilla=semilla, registro=cron)
    except flujo.ErrorFlujo as e:
        raise HTTPException(e.codigo, str(e))
    STATE["carpeta"] = carpeta
    STATE["candidatas"] = None
    STATE["conectividad"] = None
    manifest_actualizar(
        carpeta, origen="web", bbox=list(bbox), vehiculos=esc.num_vehiculos,
        duracion_min=esc.tiempo_min, semilla=esc.semilla, claves=esc.claves,
        origen_osm=esc.origen_osm,
        pasos=[{"paso": p["paso"], "exito": p["exito"], "segundos": p.get("segundos"),
                "cache": p.get("cache", False)} for p in esc.pasos])
    _apuntar_web(carpeta)

    STATE.update({
        "junctions": esc.junctions, "edificios": esc.edificios,
        "proy": esc.proy, "net_xml": esc.net_xml,
        "bbox": list(esc.bbox),
        "rsus": None, "datos_fcd": None, "tuplas_v2i": None,
        "matrices_v2v": None, "tuplas_v2v": None,
        "escenario": esc,
        "params": {"num_vehiculos": esc.num_vehiculos,
                   "tiempo_min": esc.tiempo_min,
                   "semilla": esc.semilla},
    })
    with cron.subetapa("Conversion a lat/lon (respuesta)"):
        respuesta = {
            "n_junctions": len(esc.junctions), "n_edificios": len(esc.edificios),
            "edificios": _edificios_geojson(), "bounds": _bounds(),
            "pasos": [{"paso": p["paso"], "exito": p["exito"],
                       "mensaje": p["mensaje"]} for p in esc.pasos],
        }
    return respuesta


@app.post("/api/rsu/filter")
def rsu_filter(req: RsuReq):
    """M1 — filtra las junctions a RSU candidatas (grado + clustering)."""
    if STATE.get("escenario") is None:
        raise HTTPException(409, "Genera un escenario primero.")
    cand = flujo.filtrar_candidatas(STATE["escenario"],
                                    min_grado=req.min_grado,
                                    radio_cluster=req.radio_cluster,
                                    registro=cron)
    STATE["rsus"] = cand.rsus
    STATE["candidatas"] = cand
    if STATE.get("carpeta"):
        manifest_actualizar(STATE["carpeta"], min_grado=cand.min_grado,
                            radio_cluster=cand.radio_cluster, n_candidatas=cand.n)
    return {
        "rsus": _rsus_geojson(cand.rsus),
        "n_candidatas": cand.n, "n_junctions": cand.n_junctions,
        "reduccion_pct": round(cand.reduccion_pct, 1),
    }


@app.post("/api/simulate")
def simulate(req: SimReq):
    """M2 — corre SUMO, calcula LoS y genera tuplas V2I + V2V + matrices."""
    if STATE.get("candidatas") is None:
        raise HTTPException(409, "Filtra las RSU primero.")

    try:
        con = flujo.simular_conectividad(
            STATE["escenario"], STATE["candidatas"],
            radio_obu=req.radio_obu, step_min=req.step_min,
            bidireccional=req.bidireccional, registro=cron)
    except flujo.ErrorFlujo as e:
        raise HTTPException(e.codigo, str(e))

    STATE.update({
        "datos_fcd": con.datos_fcd, "tuplas_v2i": con.tuplas_v2i,
        "matrices_v2v": con.matrices_v2v, "tuplas_v2v": con.tuplas_v2v,
        "conectividad": con,
        "params": {**STATE["params"], "radio_obu": con.radio_obu,
                   "step_min": con.step_min,
                   "bidireccional": con.bidireccional},
    })
    if STATE.get("carpeta"):
        manifest_actualizar(STATE["carpeta"], radio_obu=con.radio_obu,
                            muestreo_min=con.step_min, bidireccional=con.bidireccional,
                            n_instantes=len(con.timesteps),
                            fisica_radio=req.fisica,
                            claves=almacen.claves_leer(STATE["carpeta"]))
    return {
        "v2i": {"total_tuplas": con.est_v2i["total_tuplas"],
                "total_timesteps": con.est_v2i["total_timesteps"],
                "n_rsus": len(con.est_v2i["resumen_por_rsu"])},
        "v2v": {"total_tuplas": con.est_v2v["total_tuplas_v2v"],
                "pares_en_rango": con.est_v2v["total_pares_en_rango"],
                "n_vehiculos": len(con.est_v2v["resumen_por_vehiculo"]),
                "bidireccional": con.est_v2v["bidireccional"]},
        "timesteps": con.timesteps,
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
    carpeta = STATE.get("carpeta") or OUTPUT_DIR
    dat = os.path.join(carpeta, "dataset.dat")
    # Copia de compatibilidad: los scripts de optimizacion/ (explicar, OPL)
    # siguen leyendo rsu_backend.dat.
    dat_legado = os.path.join(RAIZ, "optimizacion", "rsu_backend.dat")
    # MaxR: si el frontend no manda número, `exportar_dat` usa el nº de RSU
    # candidatas conectadas, con lo que la restricción no ata (comportamiento
    # por defecto). El nombre de la etapa deja constancia de cuál se midió.
    etiqueta_maxr = "sin limite" if req.max_rsu is None else str(req.max_rsu)
    etiqueta_lim = ("sin limite" if req.limite_tiempo is None
                    else f"{req.limite_tiempo:g} s")
    modo = "lexicografico" if req.lexicografico else "suma ponderada"
    with cron.etapa(f"M3 - Optimizar despliegue (H={req.H}, MaxR={etiqueta_maxr}, "
                    f"tope={etiqueta_lim}, {modo})"):
        with cron.subetapa("Multisalto + construccion del CVR (.dat)") as m_cvr:
            extra = _parametros_fisicos(req)
            datos = exportar_dat_desde_memoria(
                STATE["matrices_v2v"], STATE["tuplas_v2i"], STATE["rsus"], dat,
                H=req.H, max_rsu=req.max_rsu, solo_rsu_conectados=True, **extra)
            if extra:
                cron.nota("capa fisica: " + ", ".join(
                    f"{k}={v if not isinstance(v, list) else [round(x, 3) for x in v]}"
                    for k, v in extra.items()))
            try:
                import shutil
                shutil.copyfile(dat, dat_legado)
            except OSError:
                pass
        with cron.subetapa("Solver CPLEX (branch & bound)") as medida:
            res = optimizar(datos, mostrar_log=False,
                            limite_tiempo=req.limite_tiempo,
                            lexicografico=req.lexicografico)
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

        # --- guardar como el CLI: catalogo + manifest.json ---
        # Hace falta la Conectividad en memoria (la hay tras M2, y tambien al
        # retomar una carpeta con sus JSON). Un fallo aqui no invalida el
        # despliegue ya calculado: se anota en consola y se responde igual.
        uuid_corrida = None
        if (STATE.get("conectividad") is not None
                and STATE.get("escenario") is not None
                and STATE.get("candidatas") is not None):
            with cron.subetapa("Registro en el catalogo"):
                try:
                    cat = Catalogo(CATALOGO)
                    try:
                        uuid_corrida, agregadas, _ = registrar_corrida_completa(
                            cat, esc=STATE["escenario"], cand=STATE["candidatas"],
                            con=STATE["conectividad"], datos=datos, carpeta=carpeta,
                            H=req.H, campana="web",
                            tiempos={"CVR + exportacion": m_cvr.segundos})
                        cat.guardar_despliegue(
                            uuid_corrida, motor="docplex",
                            lexicografico=req.lexicografico, max_rsu=req.max_rsu,
                            limite_tiempo=req.limite_tiempo, status=res["status"],
                            objetivo=res["objetivo"], objetivos=res.get("objetivos"),
                            n_rsu=res["n_rsu_elegidos"],
                            ids=res.get("seleccionados_backend"), cobertura=rep,
                            segundos_solver=float(seg_motor),
                            segundos_total=medida.segundos)
                    finally:
                        cat.cerrar()
                    manifest_actualizar(
                        carpeta, uuid=uuid_corrida, campana="web", H=req.H,
                        metricas=agregadas,
                        fisica_modelo=req.fisica, parametros_fisicos=extra or None,
                        despliegue={"status": res["status"], "objetivo": res["objetivo"],
                                    "objetivos": res.get("objetivos"),
                                    "n_rsu": res["n_rsu_elegidos"],
                                    "ids": res.get("seleccionados_backend"),
                                    "cobertura": rep, "max_rsu": req.max_rsu,
                                    "limite_tiempo": req.limite_tiempo,
                                    "lexicografico": req.lexicografico,
                                    "segundos_solver": float(seg_motor)})
                    cron.nota(f"corrida {uuid_corrida} guardada en {carpeta}")
                except Exception as e:  # noqa: BLE001 - el despliegue ya esta calculado
                    cron.nota(f"no se pudo registrar la corrida: {e}")
        else:
            cron.nota("corrida no registrada: falta la conectividad en memoria")

        respuesta = {
            "corrida": uuid_corrida,
            "carpeta": carpeta,
            "resumen": datos["resumen"],
            "objetivo": res["objetivo"],
            "n_desplegadas": res["n_rsu_elegidos"],
            "status": res["status"],
            "cobertura": rep,
            "objetivos": res.get("objetivos"),
            "lexicografico": req.lexicografico,
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
    # "multi-objective non-optimal" contiene "optimal": se excluye a mano, o
    # una solucion cortada por tiempo se mostraria como "Optimo demostrado".
    optimo = "optimal" in s and "non-optimal" not in s
    # CPLEX dice "time limit exceeded"; como red de seguridad, si el solver
    # consumió prácticamente todo el presupuesto sin declararse óptimo, se
    # trata igual (el reloj mandó, no la dificultad real del problema).
    corto = ("time limit" in s) or ("non-optimal" in s) or ("stopped" in s) or (
        limite is not None and not optimo and segundos >= limite * 0.97)

    if "stopped" in s or "abort" in s:
        # Con topes por nivel, agotar el tiempo da "non-optimal" CON solución;
        # "stopped"/"aborted" es una interrupción o un fallo, y no hay despliegue.
        return {"etiqueta": "Sin solución",
                "detalle": "CPLEX se detuvo sin devolver un despliegue (interrupción o error).",
                "optimo": False, "corto_por_tiempo": False}
    if "sin cobertura" in s:
        # Nivel 1 (cobertura) cortado con la solución trivial: no hay despliegue.
        return {"etiqueta": "Sin solución útil",
                "detalle": ("Se agotó el tiempo de la etapa de cobertura sin encontrar un "
                            "despliegue. Sube el límite del solver."),
                "optimo": False, "corto_por_tiempo": True}
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


@app.get("/api/fisica/opciones")
def fisica_opciones():
    """Tasas, tamaños, criterios y α recomendados; y si estan los CSV del tutor."""
    return fisica.opciones()


@app.get("/api/fisica/resumen")
def fisica_resumen(rate: float = fisica.POR_DEFECTO["rate_mbps"],
                   packet_bytes: int = fisica.POR_DEFECTO["packet_bytes"],
                   escenario: str = fisica.POR_DEFECTO["escenario"],
                   criterio: str = fisica.POR_DEFECTO["criterio"],
                   alfa: float = fisica.POR_DEFECTO["alfa"],
                   carga_kbps: float = fisica.POR_DEFECTO["carga_kbps"],
                   H: int = fisica.H_MAX,
                   semilla: int | None = None, n: int | None = None):
    """
    Curva de recepcion, radios r80/r90, Γ_H, capacidad y los parametros ya
    traducidos para M2/M3. Sin `semilla` ni `n` usa los CSV oficiales del
    tutor; con cualquiera de los dos recalcula en vivo con su mismo codigo.
    """
    try:
        return fisica.resumen(rate_mbps=rate, packet_bytes=packet_bytes, escenario=escenario,
                              criterio=criterio, alfa=alfa, carga_kbps=carga_kbps, H=H,
                              semilla=semilla, n_muestras=n)
    except (KeyError, ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e))


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
