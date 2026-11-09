"""
Módulo de Descarga de Datos OSM
===============================
Descarga el archivo .osm de un Bounding Box usando la **Overpass API**.

Antes se usaba la API principal de OpenStreetMap (`/api/0.6/map`), pero esa
rechaza con HTTP 400 cualquier área con más de ~50 000 nodos (el centro de una
ciudad los supera enseguida). Overpass permite áreas mucho más grandes; sus
límites son de tiempo/memoria del servidor, no un tope duro de nodos.

Estrategia para que funcionen áreas grandes (una ciudad entera)
---------------------------------------------------------------
1. **Se pide solo lo que el proyecto usa**: `highway=*` (red vial) y
   `building=*` (obstáculos de la línea de vista). Antes se pedía TODO el
   contenido del rectángulo —árboles, comercios, límites administrativos…—,
   que SUMO descartaba igualmente y que agotaba los recursos del servidor.

2. **Se separan calles y edificios en dos descargas.** Medido sobre el área
   Quito–Sangolquí (0,34° × 0,20°): las calles solas son 61 MB y bajan en 8 s,
   mientras que los edificios de golpe devuelven 504. Los edificios son la
   parte pesada, y separarlos evita que arrastren a las calles.

3. **Los edificios se descargan por cuadrantes, partiendo de forma recursiva.**
   Si un cuadrante falla, se divide en cuatro y se reintenta cada uno. Así el
   troceado se adapta a la densidad: las zonas rurales bajan de una vez y solo
   el núcleo urbano se subdivide.

4. **Se prueban varias instancias de Overpass.** Las públicas se saturan a
   menudo; si una devuelve 504/429 se pasa a la siguiente.

5. **Calles y edificios se descargan EN PARALELO.** Son dos consultas
   independientes y antes iban una detrás de otra. Medido sobre un área de
   Quito: 114 s las calles y 37 s los edificios, 151 s en total; lanzadas a la
   vez, el coste es el de la más lenta.

6. **Lo descargado se guarda en caché por bbox.** Repetir el mismo escenario
   cambiando vehículos o duración —lo que se hace todo el tiempo al calibrar—
   ya no vuelve a descargar nada: los `.osm` se copian de la caché. El área es
   la clave, así que un rectángulo distinto se descarga igual que siempre.

El resultado son VARIOS archivos `.osm`. No se fusionan: `netconvert` y
`polyconvert` aceptan una lista separada por comas en `--osm-files`, así que la
función devuelve exactamente eso.
"""

import hashlib
import subprocess
import json
import os
import queue
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

# Endpoints públicos de Overpass (bbox en orden S,W,N,E). Se prueban en orden.
# El orden NO es alfabético ni por "oficialidad": es el que más veces funciona,
# medido sobre un área grande de Quito. Las instancias públicas se saturan y
# devuelven 504 con frecuencia.
# NO incluir instancias regionales (p. ej. overpass.osm.ch solo tiene Suiza):
# responden 200 con un documento vacío, que parece éxito y no lo es.
OVERPASS_URLS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
OVERPASS_URL = OVERPASS_URLS[0]   # compatibilidad con código que lo importe
# Overpass (su CDN) rechaza con 406 el User-Agent por defecto de requests; hay que
# enviar uno propio identificando la app.
HEADERS = {"User-Agent": "SmartCityNet-VANET/1.0 (TIC EPN; academic use)"}
# Tope de seguridad del área (grados²). Overpass aguanta bastante, pero áreas
# enormes hacen que SUMO (netconvert) tarde muchísimo; este límite evita abusos.
MAX_AREA_DEG2 = 1.5

# Tiempo que se le concede al SERVIDOR de Overpass para resolver la consulta
# (va dentro de la propia query). Ajustable con OVERPASS_TIMEOUT_S.
OVERPASS_TIMEOUT_S = int(os.environ.get("OVERPASS_TIMEOUT_S", 300))
# Tiempo de espera HTTP. Los servidores saturados devuelven 504 en ~40 s, pero
# uno lento que SÍ va a responder puede tardar bastante más, así que conviene
# no cortarlo antes de tiempo.
# Cuanto se espera a un servidor antes de darlo por perdido. Medido: las
# peticiones que SI funcionan tardan entre 23 y 41 s, ninguna se acerca a los
# 300 s que habia antes. Con 120 s queda un margen de 3x sobre la mas lenta
# que triunfo, y un servidor colgado se abandona en la quinta parte de tiempo.
HTTP_TIMEOUT_S = int(os.environ.get("OVERPASS_HTTP_TIMEOUT_S", 120))
# Rondas completas sobre la lista de servidores, con una pausa entre ellas.
# Los 504 son transitorios: probado, la misma consulta que falla en los cuatro
# servidores funciona medio minuto después.
REINTENTOS = int(os.environ.get("OVERPASS_REINTENTOS", 3))
# Cuantos servidores compiten en paralelo por cada consulta. La misma peticion
# se manda a N instancias y se usa la PRIMERA que conteste con datos; las demas
# se abandonan. Asi no hace falta acertar de antemano cual esta sano -el orden
# escrito a mano caduca: se fijo con una medicion y dias despues los dos
# primeros de la lista estaban caidos-.
#
# Se limita a 2 a proposito: son servidores publicos y gratuitos, y mandar la
# misma consulta pesada a los cuatro seria abusar.
CARRERA = int(os.environ.get("OVERPASS_CARRERA", 2))
ESPERA_ENTRE_RONDAS = float(os.environ.get("OVERPASS_ESPERA_S", 20))
# Presupuesto de tiempo de UNA descarga entera (vias + edificios, con todas
# sus rondas y trozos). Sin el, el troceo recursivo de los edificios podia
# reintentar durante horas con Overpass caido -y ese hilo no se interrumpe-.
PRESUPUESTO_S = float(os.environ.get("OVERPASS_PRESUPUESTO_S", 900))
# Memoria máxima que se le pide al servidor, en bytes (1 GB).
OVERPASS_MAXSIZE = int(os.environ.get("OVERPASS_MAXSIZE", 1073741824))
# Cuántas veces se puede partir un cuadrante que falla (4^N cuadrantes finales).
# Con 3 son hasta 64 trozos, suficiente para una ciudad grande.
MAX_PROFUNDIDAD = int(os.environ.get("OVERPASS_MAX_PROFUNDIDAD", 3))

# ---- Caché de descargas -------------------------------------------------
# Overpass es el 74 % del tiempo de M1 y devuelve lo mismo cada vez para un
# área dada. Se guardan los .osm indexados por bbox para no repetir la espera
# al recalibrar el mismo escenario.
#   OSM_CACHE_DIR   carpeta de la caché (por defecto, `.osm_cache` junto a output/)
#   OSM_CACHE_DIAS  antigüedad máxima; 0 desactiva la caché por completo
OSM_CACHE_DIAS = float(os.environ.get("OSM_CACHE_DIAS", 30))


def validar_coordenadas(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> tuple[bool, str]:
    """
    Valida que las coordenadas geográficas estén dentro de rangos válidos.

    Retorna:
        (True, "") si son válidas,
        (False, "mensaje de error") si no lo son.
    """
    # Validar rangos geográficos reales
    if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
        return False, f"Longitud fuera de rango [-180, 180]: min={min_lon}, max={max_lon}"
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        return False, f"Latitud fuera de rango [-90, 90]: min={min_lat}, max={max_lat}"
    # Validar que min < max
    if min_lon >= max_lon:
        return False, f"min_lon ({min_lon}) debe ser menor que max_lon ({max_lon})"
    if min_lat >= max_lat:
        return False, f"min_lat ({min_lat}) debe ser menor que max_lat ({max_lat})"
    # Tope de seguridad (Overpass aguanta grande, pero SUMO tarda mucho en áreas enormes)
    area = (max_lon - min_lon) * (max_lat - min_lat)
    if area > MAX_AREA_DEG2:
        return False, (f"El área seleccionada es muy grande ({area:.3f}°²). "
                       f"Selecciona un área más pequeña (máx ~{MAX_AREA_DEG2}°²).")

    return True, ""


# ============================================================
# CONSULTA A OVERPASS (con reintento entre instancias)
# ============================================================


def _es_vacio(contenido: bytes) -> bool:
    """
    Un documento OSM sin ninguna vía. Puede significar dos cosas: que la zona
    realmente no tiene nada, o que la instancia es regional y no la cubre. En
    ambos casos conviene probar otro servidor antes de darlo por bueno.
    """
    return len(contenido) < 2000 or b"<way" not in contenido


def _pedir_a(url: str, query: str, tope: float | None = None) -> tuple[bytes | None, str]:
    """
    Lanza la consulta a UN servidor.

    Retorna (contenido, "") si respondio con datos utiles, o (None, motivo).
    Un 200 no basta: Overpass a veces devuelve 200 con un <remark> de error
    dentro, y las instancias regionales devuelven 200 con un documento vacio.
    """
    try:
        tope = HTTP_TIMEOUT_S if tope is None else max(1.0, min(tope, HTTP_TIMEOUT_S))
        r = requests.post(url, data={"data": query}, headers=HEADERS, timeout=tope)
    except requests.exceptions.Timeout:
        return None, f"tiempo de espera agotado ({tope:.0f}s)"
    except requests.exceptions.ConnectionError:
        return None, "error de conexion (hay acceso a internet?)"
    except requests.exceptions.RequestException as e:
        return None, f"error de red: {type(e).__name__}"

    if r.status_code == 200:
        if b"<remark>" in r.content and (b"runtime error" in r.content
                                         or b"timed out" in r.content.lower()):
            return None, "el servidor agoto tiempo/memoria procesando la consulta"
        if _es_vacio(r.content):
            return None, "el servidor devolvio un mapa vacio"
        return r.content, ""

    if r.status_code == 429:
        return None, "demasiadas solicitudes (429): el servidor esta limitando el ritmo"
    if r.status_code in (504, 508):
        return None, "el servidor se quedo sin tiempo/recursos (504)"
    return None, f"HTTP {r.status_code}"


# ---- Cancelacion ----
# Una descarga captura la generacion al empezar; `abortar()` la incrementa.
# Cada espera comprueba si su generacion sigue vigente y, si no, vuelve. Es
# un contador y no un booleano para que un escenario nuevo pueda abortar el
# anterior sin que el flag le afecte a el mismo.
_GENERACION = 0


def abortar() -> None:
    """Cancela toda descarga en curso (nuevo escenario, o cierre de la API)."""
    global _GENERACION
    _GENERACION += 1


def _cancelada(gen: int | None) -> bool:
    return gen is not None and gen != _GENERACION


def _esperar(segundos: float, gen: int | None) -> bool:
    """Duerme a trozos de 1 s; devuelve True si la descarga fue cancelada."""
    fin = time.perf_counter() + segundos
    while time.perf_counter() < fin:
        if _cancelada(gen):
            return True
        time.sleep(min(1.0, fin - time.perf_counter()))
    return _cancelada(gen)


def _host(url: str) -> str:
    """'overpass-api.de' a partir de la URL completa, para los mensajes."""
    return url.split("//", 1)[-1].split("/", 1)[0]


def _avisar(texto: str) -> None:
    """
    Escribe en la consola del backend lo que esta haciendo la descarga.

    Es la unica ventana que tiene el usuario mientras Overpass no contesta: la
    peticion HTTP de la interfaz sigue abierta y no puede informar de nada.
    Sin esto, tres rondas de reintentos son trece minutos de reloj de arena.
    """
    print(f"  [overpass] {texto}", flush=True)


def _carrera(urls: list[str], query: str,
             tope: float | None = None, gen: int | None = None) -> tuple[bytes | None, str]:
    """
    Manda la consulta a varios servidores a la vez y devuelve la PRIMERA
    respuesta con datos.

    Los perdedores no se cancelan -no se puede abortar una peticion HTTP en
    curso- pero se abandonan: corren en hilos `daemon`, asi que no retrasan el
    cierre del proceso ni bloquean el retorno. Es la diferencia con esperar a
    todos: si uno contesta en 20 s y otro esta colgado, se devuelve a los 20 s.
    """
    buzon: queue.Queue = queue.Queue()
    t0 = time.perf_counter()
    # El tope por peticion nunca supera HTTP_TIMEOUT_S aunque quede mas
    # presupuesto: es lo que aplica _pedir_a, y lo que se imprime.
    tope = HTTP_TIMEOUT_S if tope is None else max(1.0, min(tope, HTTP_TIMEOUT_S))

    def trabajo(u: str) -> None:
        try:
            contenido, m = _pedir_a(u, query, tope)
        except Exception as e:                      # nunca dejar el buzon vacio
            contenido, m = None, f"error inesperado: {type(e).__name__}"
        buzon.put((contenido, m, u, time.perf_counter() - t0))

    _avisar("pidiendo a " + " y ".join(_host(u) for u in urls)
            + f" (tope {tope:.0f} s cada uno)")
    for u in urls:
        threading.Thread(target=trabajo, args=(u,), daemon=True).start()

    motivo = "ningun servidor respondio"
    pendientes = len(urls)
    limite = time.perf_counter() + tope + 15
    # Sondeo de 1 s en vez de un get bloqueante: asi Ctrl+C o un escenario
    # nuevo pueden cortar la espera. Los hilos HTTP siguen hasta su tope,
    # pero son daemon y nadie los espera.
    while pendientes:
        if _cancelada(gen):
            return None, "descarga cancelada"
        if time.perf_counter() > limite:
            _avisar("ninguno contesto dentro del tope")
            break
        try:
            contenido, m, u, dt = buzon.get(timeout=1.0)
        except queue.Empty:
            continue
        pendientes -= 1
        if contenido is not None:
            _avisar(f"{_host(u)} respondio en {dt:.0f} s ({len(contenido) / 1e6:.1f} MB)")
            return contenido, ""
        _avisar(f"{_host(u)}: {m} ({dt:.0f} s)")
        motivo = m
    return None, motivo


def _consultar(cuerpo: str, plazo: float | None = None,
               gen: int | None = None) -> tuple[bytes | None, str]:
    """
    Ejecuta un cuerpo de consulta Overpass, en carrera entre servidores.

    Parametros:
        cuerpo: la parte de la consulta entre el prologo y la salida, p. ej.
                '(way["highway"](S,W,N,E););'

    Retorna:
        (contenido, "") si algun servidor respondio con datos,
        (None, motivo) si todos fallaron.

    Estrategia: los servidores se agrupan de `CARRERA` en `CARRERA` y cada grupo
    compite; se usa el primero que conteste. Si el grupo entero falla, se pasa al
    siguiente. Los 504 de las instancias publicas son casi siempre transitorios
    -la misma consulta que falla en los cuatro suele funcionar medio minuto
    despues-, asi que todo esto se repite `REINTENTOS` rondas.
    """
    query = (
        f"[out:xml][timeout:{OVERPASS_TIMEOUT_S}][maxsize:{OVERPASS_MAXSIZE}];"
        f"{cuerpo}"
        "(._;>;);"
        "out body;"
    )

    motivo = "no se pudo contactar con ningun servidor de Overpass"

    def restante() -> float | None:
        return None if plazo is None else plazo - time.time()

    for ronda in range(REINTENTOS):
        if ronda:
            r = restante()
            if r is not None and r < ESPERA_ENTRE_RONDAS + 5:
                _avisar("presupuesto de tiempo agotado: no se reintenta mas")
                return None, "presupuesto de tiempo agotado"
            _avisar(f"todos los servidores fallaron; ronda {ronda + 1}/{REINTENTOS} "
                    f"en {ESPERA_ENTRE_RONDAS:.0f} s (suele ser transitorio)")
            if _esperar(ESPERA_ENTRE_RONDAS, gen):
                return None, "descarga cancelada"
        for i in range(0, len(OVERPASS_URLS), CARRERA):
            if _cancelada(gen):
                return None, "descarga cancelada"
            r = restante()
            if r is not None and r < 5:
                _avisar("presupuesto de tiempo agotado: no se reintenta mas")
                return None, "presupuesto de tiempo agotado"
            grupo = OVERPASS_URLS[i:i + CARRERA]
            contenido, m = _carrera(grupo, query, tope=r, gen=gen)
            if contenido is not None:
                return contenido, ""
            motivo = m

    _avisar(f"sin exito tras {REINTENTOS} rondas: {motivo}. Con Overpass saturado "
            f"ayuda subir OVERPASS_HTTP_TIMEOUT_S (hoy {HTTP_TIMEOUT_S}) o elegir un "
            f"area menor")
    return None, motivo


def _descargar_edificios(bbox: tuple[float, float, float, float], output_dir: str,
                         prefijo: str, profundidad: int = 0,
                         plazo: float | None = None,
                         gen: int | None = None) -> tuple[list[str], list[str]]:
    """
    Descarga los edificios de un bbox, partiéndolo en cuatro si el servidor no
    puede con él. La recursión se adapta a la densidad: el campo baja de una
    vez y solo el casco urbano se subdivide.

    Parámetros:
        bbox: (sur, oeste, norte, este) en grados.
        output_dir: carpeta donde escribir los .osm.
        prefijo: nombre base de los archivos (se le añade un índice).
        profundidad: nivel actual de subdivisión (interno).

    Retorna:
        (archivos_escritos, zonas_fallidas)
    """
    s, w, n, e = bbox
    cuerpo = (f'(way["building"]({s},{w},{n},{e});'
              f'relation["building"]({s},{w},{n},{e}););')

    contenido, motivo = _consultar(cuerpo, plazo, gen)
    if contenido is not None:
        ruta = os.path.join(output_dir, f"{prefijo}.osm")
        with open(ruta, "wb") as f:
            f.write(contenido)
        return [ruta], []

    # Un mapa vacío no es un fallo: hay cuadrantes sin edificios (campo, agua).
    if motivo == "el servidor devolvió un mapa vacío":
        return [], []

    if profundidad >= MAX_PROFUNDIDAD:
        return [], [f"({s:.3f},{w:.3f})-({n:.3f},{e:.3f}): {motivo}"]
    # Trocear solo tiene sentido si el problema es el TAMANO del area. Con el
    # presupuesto agotado -o cerca- es que los servidores no responden, y
    # partir en cuatro multiplicaria la espera en vez de resolver nada.
    if _cancelada(gen) or (plazo is not None and plazo - time.time() < 60):
        return [], [f"({s:.3f},{w:.3f})-({n:.3f},{e:.3f}): {motivo}"]

    # Partir en cuatro y reintentar cada cuadrante
    archivos, fallos = [], []
    mid_lat, mid_lon = (s + n) / 2, (w + e) / 2
    cuadrantes = [
        (s, w, mid_lat, mid_lon), (s, mid_lon, mid_lat, e),
        (mid_lat, w, n, mid_lon), (mid_lat, mid_lon, n, e),
    ]
    for k, q in enumerate(cuadrantes):
        a, f_ = _descargar_edificios(q, output_dir, f"{prefijo}_{k}", profundidad + 1, plazo, gen)
        archivos += a
        fallos += f_
    return archivos, fallos




# ============================================================
# EXTRACTO LOCAL (Geofabrik + osmconvert / osmfilter)
# ============================================================
# Overpass es un servicio publico y gratuito que se satura y se cae (el
# 25-sep-2026 los cuatro espejos devolvieron 504 durante horas hasta para una
# manzana). Y ademas cambia a diario: el mapa de hoy no es el de hace tres
# meses, que para una tesis es un problema de reproducibilidad.
#
# La alternativa: un extracto del pais entero, descargado UNA vez de
# Geofabrik (Ecuador: 125 MB) y congelado con su fecha. Cualquier rectangulo
# se recorta en local con osmconvert en segundos, sin red, y se filtra con
# osmfilter para quedarse con lo mismo que se pedia a Overpass (vias,
# edificios y restricciones de giro). Overpass queda como respaldo para un
# area fuera del extracto.
#
# Sobre `--complete-ways`: la opcion de osmconvert que devuelve enteras las
# vias que cruzan el borde no funciona en la build de Windows (salida vacia
# con .pbf y con .o5m, con y sin archivo temporal). Se compensa recortando
# con un MARGEN alrededor del rectangulo: las vias que cruzan el borde
# pedido llegan completas, y las unicas truncadas quedan a ~330 m fuera del
# area, donde no hay candidatas ni vehiculos que medir.

_RAIZ_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_EXTRACTOS = os.environ.get("OSM_EXTRACTOS_DIR") or os.path.join(_RAIZ_REPO, "datos", "osm")
DIR_HERRAMIENTAS = os.path.join(_RAIZ_REPO, "herramientas")
MARGEN_EXTRACTO_DEG = float(os.environ.get("OSM_MARGEN_GRADOS", 0.003))   # ~330 m
# Lo mismo que se pide a Overpass: red vial, obstaculos y giros prohibidos.
FILTRO_EXTRACTO = "highway= building= type=restriction"
ARCHIVO_ORIGEN = "osm_origen.json"


def _herramienta(nombre: str) -> str | None:
    """
    Ruta a osmconvert/osmfilter: variable de entorno (OSMCONVERT / OSMFILTER),
    el PATH, o `herramientas/<nombre>.exe` en el repo. None si no esta.
    """
    ruta = os.environ.get(nombre.upper())
    if ruta and os.path.isfile(ruta):
        return ruta
    ruta = shutil.which(nombre)
    if ruta:
        return ruta
    for candidato in (nombre + ".exe", nombre):
        ruta = os.path.join(DIR_HERRAMIENTAS, candidato)
        if os.path.isfile(ruta):
            return ruta
    return None


def herramientas_extracto() -> dict:
    return {"osmconvert": _herramienta("osmconvert"), "osmfilter": _herramienta("osmfilter")}


def extractos() -> list[dict]:
    """
    Extractos registrados en `datos/osm/`: cada `<archivo>` con su
    `<archivo>.meta.json` (bbox, fecha de los datos, url, md5). Lo escribe
    `scn.py extracto`.
    """
    salida = []
    if not os.path.isdir(DIR_EXTRACTOS):
        return salida
    for nombre in sorted(os.listdir(DIR_EXTRACTOS)):
        if not (nombre.endswith(".osm.pbf") or nombre.endswith(".o5m")):
            continue
        meta_p = os.path.join(DIR_EXTRACTOS, nombre + ".meta.json")
        if not os.path.isfile(meta_p):
            continue
        try:
            with open(meta_p, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        if not meta.get("bbox"):
            continue
        meta["archivo"] = nombre
        meta["ruta"] = os.path.join(DIR_EXTRACTOS, nombre)
        salida.append(meta)
    return salida


def _extracto_para(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> dict | None:
    """El extracto registrado cuyo bbox contiene al pedido (el primero que lo cumpla)."""
    for ext in extractos():
        w, s, e, n = ext["bbox"]
        if w <= min_lon and s <= min_lat and e >= max_lon and n >= max_lat:
            return ext
    return None


def estadisticas_extracto(ruta: str) -> dict:
    """bbox y fecha de los datos de un extracto, con `osmconvert --out-statistics`."""
    conv = _herramienta("osmconvert")
    if not conv:
        raise FileNotFoundError("no se encuentra osmconvert (herramientas/osmconvert.exe)")
    r = subprocess.run([conv, ruta, "--out-statistics"], capture_output=True,
                       text=True, timeout=600)
    valores = {}
    for linea in r.stdout.splitlines():
        if ":" in linea:
            k, v = linea.split(":", 1)
            valores[k.strip()] = v.strip()
    try:
        bbox = [float(valores["lon min"]), float(valores["lat min"]),
                float(valores["lon max"]), float(valores["lat max"])]
    except (KeyError, ValueError):
        raise ValueError(f"osmconvert no devolvio el bbox de {ruta}: {r.stderr[:200]}")
    return {"bbox": bbox, "fecha_datos": valores.get("timestamp max"),
            "nodos": int(valores.get("nodes", 0)), "vias": int(valores.get("ways", 0))}


def registrar_extracto(ruta: str, url: str | None = None, md5: str | None = None) -> dict:
    """Escribe `<archivo>.meta.json` con bbox, fecha de datos, url y md5."""
    meta = estadisticas_extracto(ruta)
    meta.update({"url": url, "md5": md5,
                 "registrado": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "bytes": os.path.getsize(ruta)})
    with open(ruta + ".meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return meta


def _contar(ruta: str, patron: bytes) -> int:
    """Ocurrencias de `patron` en un archivo, por trozos (un .osm de ciudad pesa cientos de MB)."""
    total, cola = 0, b""
    with open(ruta, "rb") as f:
        while True:
            trozo = f.read(1 << 20)
            if not trozo:
                break
            datos = cola + trozo
            total += datos.count(patron)
            cola = datos[-len(patron):]
    return total


def _recortar_extracto(ext: dict, min_lon: float, min_lat: float, max_lon: float,
                       max_lat: float, output_dir: str) -> tuple[list[str] | None, str]:
    """
    Recorta el rectangulo (con margen) del extracto y lo filtra a vias,
    edificios y restricciones. Deja `output_dir/map.osm`.

    Retorna ([map.osm], "") o (None, motivo).
    """
    conv, filt = _herramienta("osmconvert"), _herramienta("osmfilter")
    if not conv or not filt:
        return None, "faltan osmconvert/osmfilter (ver herramientas/README.md)"
    m = MARGEN_EXTRACTO_DEG
    bbox = f"{min_lon - m:.6f},{min_lat - m:.6f},{max_lon + m:.6f},{max_lat + m:.6f}"
    bruto = os.path.join(output_dir, "map_bruto.o5m")
    salida = os.path.join(output_dir, "map.osm")
    t0 = time.perf_counter()
    try:
        r = subprocess.run([conv, ext["ruta"], f"-b={bbox}", "--drop-author",
                            "--out-o5m", f"-o={bruto}"],
                           capture_output=True, text=True, timeout=1800)
        if r.returncode != 0 or not os.path.isfile(bruto):
            return None, f"osmconvert fallo: {r.stderr[:200]}"
        r = subprocess.run([filt, bruto, f"--keep={FILTRO_EXTRACTO}", f"-o={salida}"],
                           capture_output=True, text=True, timeout=1800)
        if r.returncode != 0 or not os.path.isfile(salida):
            return None, f"osmfilter fallo: {r.stderr[:200]}"
    except (subprocess.SubprocessError, OSError) as e:
        return None, f"error ejecutando las herramientas: {type(e).__name__}"
    finally:
        try:
            os.remove(bruto)
        except OSError:
            pass

    vias = _contar(salida, b'k="highway"')
    edificios = _contar(salida, b'k="building"')
    if vias == 0:
        return None, "el recorte no contiene vias (area fuera del extracto o sin calles)"
    if edificios == 0:
        # Igual que con Overpass: sin obstaculos la linea de vista seria
        # perfecta en todas partes, un resultado falso que pareceria correcto.
        return None, "el recorte no contiene edificios: sin obstaculos la linea de vista no es valida"
    _avisar(f"recorte del extracto {ext['archivo']} (datos del {str(ext.get('fecha_datos'))[:10]}) "
            f"en {time.perf_counter() - t0:.1f} s: {vias} vias, {edificios} edificios, "
            f"{os.path.getsize(salida) / 1e6:.1f} MB")
    return [salida], ""


def _escribir_origen(output_dir: str, origen: dict) -> None:
    """`osm_origen.json`: de donde salio el mapa (extracto con fecha, u Overpass). Va al manifest."""
    try:
        with open(os.path.join(output_dir, ARCHIVO_ORIGEN), "w", encoding="utf-8") as f:
            json.dump(origen, f, indent=2)
    except OSError:
        pass


def leer_origen(output_dir: str) -> dict:
    try:
        with open(os.path.join(output_dir, ARCHIVO_ORIGEN), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


# ============================================================
# CACHÉ DE DESCARGAS (por bbox)
# ============================================================


def _clave_cache(bbox: tuple[float, float, float, float]) -> str:
    """Identificador estable de un área. Se redondea a 1e-6° (~0,1 m) para que
    dos clics idénticos den la misma clave pese al ruido del float."""
    txt = ",".join(f"{c:.6f}" for c in bbox)
    return hashlib.sha1(txt.encode()).hexdigest()[:16]


# Carpeta unica para la cache, a nivel de REPOSITORIO.
#
# Antes se derivaba de la carpeta de salida (`dirname(output_dir)/.osm_cache`),
# lo que funcionaba mientras todo iba a `output/` pero se rompe con una carpeta
# por corrida: cada corrida miraba en un sitio distinto y volvia a descargar de
# Overpass lo que ya tenia. La cache tiene sentido precisamente porque el area
# se comparte entre corridas, asi que su sitio no puede depender de la salida.
_RAIZ_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _dir_cache(output_dir: str, clave: str) -> str:
    """Carpeta de cache para un area. `output_dir` se ignora a proposito."""
    raiz = os.environ.get("OSM_CACHE_DIR") or os.path.join(_RAIZ_REPO, ".osm_cache")
    return os.path.join(raiz, clave)


def _cache_recuperar(carpeta: str, output_dir: str) -> list[str] | None:
    """
    Copia los .osm de la caché a `output_dir` y devuelve sus rutas, o None si
    no hay nada utilizable (no existe, caducó, o quedó a medias).

    Se COPIA en vez de usarlos en su sitio para que el resto del flujo siga
    viendo los archivos donde siempre y no haya que tocar nada aguas abajo.
    """
    if OSM_CACHE_DIAS <= 0:
        return None
    meta = os.path.join(carpeta, "meta.json")
    if not os.path.exists(meta):
        return None
    try:
        with open(meta, encoding="utf-8") as f:
            info = json.load(f)
        edad_dias = (time.time() - float(info["ts"])) / 86400.0
        if edad_dias > OSM_CACHE_DIAS:
            return None
        rutas = []
        for nombre in info["archivos"]:
            origen = os.path.join(carpeta, nombre)
            if not os.path.exists(origen):
                return None          # caché incompleta: mejor volver a bajar
            destino = os.path.join(output_dir, nombre)
            shutil.copyfile(origen, destino)
            rutas.append(destino)
        if info.get("origen"):
            _escribir_origen(output_dir, {**info["origen"], "cache": True})
        return rutas or None
    except (OSError, ValueError, KeyError):
        return None


def _cache_guardar(carpeta: str, rutas: list[str],
                   bbox: tuple[float, float, float, float] | None = None,
                   origen: dict | None = None) -> None:
    """Guarda los .osm recién descargados. Un fallo aquí no debe romper la
    descarga: la caché es una optimización, no un requisito.

    El bbox se anota en meta.json: la clave es un hash y no se puede invertir,
    y sin el rectángulo original un área ya descargada no se puede volver a
    pedir cuando Overpass no responde (pasó el 25-sep-2026)."""
    if OSM_CACHE_DIAS <= 0:
        return
    try:
        os.makedirs(carpeta, exist_ok=True)
        nombres = []
        for r in rutas:
            nombre = os.path.basename(r)
            shutil.copyfile(r, os.path.join(carpeta, nombre))
            nombres.append(nombre)
        # El meta se escribe AL FINAL: si el proceso muere a medias, la entrada
        # queda sin meta y `_cache_recuperar` la ignora en vez de servir basura.
        with open(os.path.join(carpeta, "meta.json"), "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "archivos": nombres,
                       "bbox": list(bbox) if bbox else None,
                       "origen": origen}, f)
    except OSError:
        pass


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================


def descargar_mapa_osm(min_lon: float, min_lat: float, max_lon: float, max_lat: float,
                       output_dir: str = "output") -> tuple[str | None, str | None]:
    """
    Descarga el mapa de OpenStreetMap correspondiente al Bounding Box dado.

    Hace dos descargas separadas —calles y edificios— porque los edificios son
    la parte pesada y, en áreas grandes, arrastraban a toda la consulta. Los
    edificios se trocean por cuadrantes según haga falta (ver `_descargar_edificios`).

    Parámetros:
        min_lon, min_lat, max_lon, max_lat: Coordenadas del Bounding Box.
        output_dir: Directorio donde se guardarán los archivos descargados.

    Retorna:
        (rutas, None) si la descarga fue exitosa. `rutas` es una cadena con los
            archivos .osm separados por comas, en el formato que aceptan
            `netconvert`/`polyconvert` en su opción `--osm-files`.
        (None, mensaje_error) si no se pudo obtener la red vial.
    """
    valido, msg_error = validar_coordenadas(min_lon, min_lat, max_lon, max_lat)
    if not valido:
        return None, f"Coordenadas inválidas: {msg_error}"

    os.makedirs(output_dir, exist_ok=True)

    # Limpiar descargas anteriores: si el área nueva es menor, los .osm viejos
    # de edificios se colarían en el mapa y aparecerían polígonos fantasma.
    for nombre in os.listdir(output_dir):
        if nombre.startswith("map_edificios") and nombre.endswith(".osm"):
            try:
                os.remove(os.path.join(output_dir, nombre))
            except OSError:
                pass

    s, w, n, e = min_lat, min_lon, max_lat, max_lon

    # ---- 0) ¿Ya se descargó esta misma área antes? ----
    carpeta_cache = _dir_cache(output_dir, _clave_cache((s, w, n, e)))
    rutas = _cache_recuperar(carpeta_cache, output_dir)
    if rutas:
        print(f"  OSM en cache: {len(rutas)} archivo(s), sin descargar nada")
        return ",".join(rutas), None

    # ---- Extracto local (sin red) ----
    ext = _extracto_para(min_lon, min_lat, max_lon, max_lat)
    if ext is None:
        _avisar("sin extracto local que cubra el area (datos/osm/, ver `scn.py extracto`); "
                "se pide a Overpass")
    else:
        rutas, motivo = _recortar_extracto(ext, min_lon, min_lat, max_lon, max_lat, output_dir)
        if rutas:
            origen = {"fuente": "extracto", "archivo": ext["archivo"],
                      "fecha_datos": ext.get("fecha_datos"), "url": ext.get("url"),
                      "md5": ext.get("md5"), "margen_grados": MARGEN_EXTRACTO_DEG,
                      # El rectangulo PEDIDO: el pipeline poda la red a el, porque
                      # el recorte lleva margen (ver sumo_pipeline).
                      "bbox": [min_lon, min_lat, max_lon, max_lat]}
            _escribir_origen(output_dir, origen)
            _cache_guardar(carpeta_cache, rutas, (min_lon, min_lat, max_lon, max_lat), origen)
            return ",".join(rutas), None
        _avisar(f"el extracto local no sirvio ({motivo}); se pide a Overpass")

    # ---- 1) Red vial y edificios, EN PARALELO ----
    # Son consultas independientes y antes iban en serie. Overpass admite dos
    # peticiones simultáneas por IP, que es justo lo que se usa aquí; no se
    # paraleliza más para no provocar 429 (demasiadas peticiones).
    #
    # Red vial: una sola consulta (es la parte ligera). Se incluyen las
    # restricciones de giro porque mejoran la red y pesan poco.
    plazo = time.time() + PRESUPUESTO_S
    gen = _GENERACION
    _avisar(f"descarga nueva; presupuesto total {PRESUPUESTO_S / 60:.0f} min "
            f"(OVERPASS_PRESUPUESTO_S)")
    cuerpo_vias = (f'(way["highway"]({s},{w},{n},{e});'
                   f'relation["type"="restriction"]({s},{w},{n},{e}););')

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_vias = pool.submit(_consultar, cuerpo_vias, plazo, gen)
        # Los edificios se trocean por cuadrantes, subdividiendo lo que falle.
        fut_edif = pool.submit(_descargar_edificios, (s, w, n, e),
                               output_dir, "map_edificios", 0, plazo, gen)
        contenido, motivo = fut_vias.result()
        archivos, fallos = fut_edif.result()
    if _cancelada(gen):
        return None, "descarga cancelada (escenario nuevo o cierre de la API)"

    if contenido is None:
        return None, (
            f"No se pudo descargar la red vial: {motivo}. Se probaron "
            f"{len(OVERPASS_URLS)} servidores de Overpass. Reduce el área e "
            f"inténtalo de nuevo, o descarga el mapa aparte (p. ej. de Geofabrik) "
            f"y colócalo como {os.path.join(output_dir, 'map.osm')}."
        )

    ruta_vias = os.path.join(output_dir, "map.osm")
    with open(ruta_vias, "wb") as f:
        f.write(contenido)
    rutas = [ruta_vias] + archivos

    if fallos and not archivos:
        # Sin ningún edificio, la línea de vista no tendría obstáculos y los
        # resultados de conectividad serían optimistas: mejor avisar claramente.
        return None, (
            "Se descargó la red vial, pero ningún edificio: sin obstáculos el "
            "cálculo de línea de vista no es válido. Reduce el área e inténtalo "
            f"de nuevo. Motivo: {fallos[0]}"
        )

    # Solo se cachea una descarga COMPLETA (vías + al menos un edificio).
    origen = {"fuente": "overpass", "fecha_descarga": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "servidores": [_host(u) for u in OVERPASS_URLS]}
    _escribir_origen(output_dir, origen)
    _cache_guardar(carpeta_cache, rutas, (min_lon, min_lat, max_lon, max_lat), origen)
    return ",".join(rutas), None
