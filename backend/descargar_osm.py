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


def _pedir_a(url: str, query: str) -> tuple[bytes | None, str]:
    """
    Lanza la consulta a UN servidor.

    Retorna (contenido, "") si respondio con datos utiles, o (None, motivo).
    Un 200 no basta: Overpass a veces devuelve 200 con un <remark> de error
    dentro, y las instancias regionales devuelven 200 con un documento vacio.
    """
    try:
        r = requests.post(url, data={"data": query}, headers=HEADERS,
                          timeout=HTTP_TIMEOUT_S)
    except requests.exceptions.Timeout:
        return None, f"tiempo de espera agotado ({HTTP_TIMEOUT_S}s)"
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


def _carrera(urls: list[str], query: str) -> tuple[bytes | None, str]:
    """
    Manda la consulta a varios servidores a la vez y devuelve la PRIMERA
    respuesta con datos.

    Los perdedores no se cancelan -no se puede abortar una peticion HTTP en
    curso- pero se abandonan: corren en hilos `daemon`, asi que no retrasan el
    cierre del proceso ni bloquean el retorno. Es la diferencia con esperar a
    todos: si uno contesta en 20 s y otro esta colgado, se devuelve a los 20 s.
    """
    buzon: queue.Queue = queue.Queue()

    def trabajo(u: str) -> None:
        try:
            buzon.put(_pedir_a(u, query))
        except Exception as e:                      # nunca dejar el buzon vacio
            buzon.put((None, f"error inesperado: {type(e).__name__}"))

    for u in urls:
        threading.Thread(target=trabajo, args=(u,), daemon=True).start()

    motivo = "ningun servidor respondio"
    for _ in urls:
        try:
            contenido, m = buzon.get(timeout=HTTP_TIMEOUT_S + 15)
        except queue.Empty:
            break
        if contenido is not None:
            return contenido, ""
        motivo = m
    return None, motivo


def _consultar(cuerpo: str) -> tuple[bytes | None, str]:
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

    for ronda in range(REINTENTOS):
        if ronda:
            time.sleep(ESPERA_ENTRE_RONDAS)
        for i in range(0, len(OVERPASS_URLS), CARRERA):
            grupo = OVERPASS_URLS[i:i + CARRERA]
            contenido, m = _carrera(grupo, query)
            if contenido is not None:
                return contenido, ""
            motivo = m

    return None, motivo


def _descargar_edificios(bbox: tuple[float, float, float, float], output_dir: str,
                         prefijo: str, profundidad: int = 0) -> tuple[list[str], list[str]]:
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

    contenido, motivo = _consultar(cuerpo)
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

    # Partir en cuatro y reintentar cada cuadrante
    archivos, fallos = [], []
    mid_lat, mid_lon = (s + n) / 2, (w + e) / 2
    cuadrantes = [
        (s, w, mid_lat, mid_lon), (s, mid_lon, mid_lat, e),
        (mid_lat, w, n, mid_lon), (mid_lat, mid_lon, n, e),
    ]
    for k, q in enumerate(cuadrantes):
        a, f_ = _descargar_edificios(q, output_dir, f"{prefijo}_{k}", profundidad + 1)
        archivos += a
        fallos += f_
    return archivos, fallos


# ============================================================
# CACHÉ DE DESCARGAS (por bbox)
# ============================================================


def _clave_cache(bbox: tuple[float, float, float, float]) -> str:
    """Identificador estable de un área. Se redondea a 1e-6° (~0,1 m) para que
    dos clics idénticos den la misma clave pese al ruido del float."""
    txt = ",".join(f"{c:.6f}" for c in bbox)
    return hashlib.sha1(txt.encode()).hexdigest()[:16]


def _dir_cache(output_dir: str, clave: str) -> str:
    raiz = os.environ.get("OSM_CACHE_DIR") or os.path.join(
        os.path.dirname(os.path.abspath(output_dir)), ".osm_cache")
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
        return rutas or None
    except (OSError, ValueError, KeyError):
        return None


def _cache_guardar(carpeta: str, rutas: list[str]) -> None:
    """Guarda los .osm recién descargados. Un fallo aquí no debe romper la
    descarga: la caché es una optimización, no un requisito."""
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
            json.dump({"ts": time.time(), "archivos": nombres}, f)
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

    # ---- 1) Red vial y edificios, EN PARALELO ----
    # Son consultas independientes y antes iban en serie. Overpass admite dos
    # peticiones simultáneas por IP, que es justo lo que se usa aquí; no se
    # paraleliza más para no provocar 429 (demasiadas peticiones).
    #
    # Red vial: una sola consulta (es la parte ligera). Se incluyen las
    # restricciones de giro porque mejoran la red y pesan poco.
    cuerpo_vias = (f'(way["highway"]({s},{w},{n},{e});'
                   f'relation["type"="restriction"]({s},{w},{n},{e}););')

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_vias = pool.submit(_consultar, cuerpo_vias)
        # Los edificios se trocean por cuadrantes, subdividiendo lo que falle.
        fut_edif = pool.submit(_descargar_edificios, (s, w, n, e),
                               output_dir, "map_edificios")
        contenido, motivo = fut_vias.result()
        archivos, fallos = fut_edif.result()

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
    _cache_guardar(carpeta_cache, rutas)

    return ",".join(rutas), None
