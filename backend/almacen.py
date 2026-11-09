"""
almacen.py — reutilización de etapas ya calculadas
===================================================
Cada etapa del flujo (convertir la red, generar rutas, simular la traza,
calcular la línea de vista) es una **función pura de sus entradas**: con el
mismo mapa, los mismos parámetros y la misma semilla produce exactamente el
mismo archivo —está comprobado en `pruebas/determinismo.py`—. Entonces no hay
motivo para calcularla dos veces.

Este módulo guarda la salida de cada etapa bajo una **clave derivada de sus
entradas** y, antes de ejecutar una herramienta, mira si esa clave ya existe.
Si existe, el archivo se **enlaza** en la carpeta de la corrida y la etapa
cuesta milisegundos. Si no, se ejecuta y se guarda para la próxima vez.

Las claves se encadenan, así que nada se reutiliza por error:

    red    = H(versión SUMO, hash del OSM, opciones de netconvert)
    poly   = H(red)
    rutas  = H(red, nº vehículos, periodo, fin, semilla)
    fcd    = H(rutas, duración, muestreo, semilla)
    parseo = H(red, poly)
    los    = H(fcd, candidatas, radio, bidireccional)

Cambiar la semilla invalida rutas, fcd y los, pero **no** red ni poly; cambiar
el radio de la OBU invalida solo los. Es la misma lógica de tablas del
catálogo (`catalogo.py`), llevada al disco.

Por qué enlaces duros y no copias
---------------------------------
Una red de ciudad pesa cientos de MB. Copiarla a cada carpeta de corrida
multiplicaría el disco por el número de corridas. Un enlace duro (`os.link`)
es instantáneo y no ocupa nada: son dos nombres para el mismo archivo. Si el
sistema de archivos no lo permite (otro volumen), se copia.

El riesgo del enlace es que una herramienta **sobrescriba en sitio** el
archivo de la corrida y con ello corrompa el del almacén. Por eso, antes de
ejecutar cualquier herramienta, se rompe el enlace con `desvincular()`: la
herramienta crea un archivo nuevo y el del almacén queda intacto.

Se desactiva con `SCN_CACHE=0` (la prueba de determinismo lo hace: si la
segunda corrida saliera del almacén no probaría nada). La carpeta se elige
con `SCN_CACHE_DIR`; por defecto `datos/cache/`.
"""

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Nombre del archivo que cada corrida lleva con las claves de sus etapas. Lo
# escribe el pipeline de M1 y lo leen M2 y el catálogo: es lo que permite que
# `simular_conectividad` sepa de qué rutas viene sin volver a hashearlas.
ARCHIVO_CLAVES = "claves.json"


def dir_cache() -> str:
    return os.environ.get("SCN_CACHE_DIR") or os.path.join(_RAIZ, "datos", "cache")


def activo() -> bool:
    return os.environ.get("SCN_CACHE", "1").strip().lower() not in ("0", "no", "false", "")


# ----------------------------------------------------------------------
# Hashes
# ----------------------------------------------------------------------

def clave(*partes) -> str:
    """
    Clave de reutilización: hash de las entradas de una etapa.

    Se serializa con `json` y claves ordenadas para que no dependa del orden
    en que se pasen los argumentos ni de la representación de los floats.
    """
    texto = json.dumps(partes, sort_keys=True, default=str)
    return hashlib.sha256(texto.encode()).hexdigest()[:32]


def sha_archivo(ruta: str, trozo: int = 1 << 20) -> str:
    """SHA-256 de un archivo, leyéndolo por trozos (los hay de cientos de MB)."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while True:
            datos = f.read(trozo)
            if not datos:
                break
            h.update(datos)
    return h.hexdigest()


def sha_varios(rutas: str) -> str:
    """
    SHA-256 combinado de una lista de archivos separada por comas.

    `descargar_mapa_osm` no devuelve un archivo sino la lista que consumen
    `netconvert`/`polyconvert` en `--osm-files`: las vías y los edificios se
    piden por separado, y los edificios pueden venir troceados en cuadrantes.
    El área queda identificada por el conjunto entero, no por uno de ellos.
    """
    h = hashlib.sha256()
    for r in [x.strip() for x in str(rutas).split(",") if x.strip()]:
        h.update(sha_archivo(r).encode())
    return h.hexdigest()


def sha_contenido_xml(ruta: str) -> str:
    """
    SHA-256 del CONTENIDO de un XML de SUMO, ignorando las cabeceras.

    No sirve el hash del archivo: SUMO escribe al principio un comentario con
    la marca de tiempo de generación y la configuración completa —con las
    RUTAS de los archivos—, que cambian entre dos corridas equivalentes en
    carpetas distintas. Se saltan todos los bloques `<!-- ... -->` y se hashea
    el resto, de modo que dos escenarios iguales den el mismo hash.

    Va por líneas, no con `ElementTree`: un FCD de decenas de miles de
    vehículos pesa GB y parsearlo entero solo para hashearlo no cabe en
    memoria.
    """
    h = hashlib.sha256()
    en_comentario = False
    with open(ruta, "rb") as f:
        for linea in f:
            if en_comentario:
                if b"-->" in linea:
                    en_comentario = False
                continue
            if b"<!--" in linea:
                if b"-->" not in linea:
                    en_comentario = True
                continue
            h.update(linea)
    return h.hexdigest()


_VERSION_SUMO: str | None = None


def version_sumo() -> str:
    """
    Primera línea de `sumo --version`, cacheada por proceso.

    Forma parte de todas las claves: una versión nueva de SUMO puede
    convertir la misma red de otra manera, y eso no debe salir del almacén.
    """
    global _VERSION_SUMO
    if _VERSION_SUMO is None:
        try:
            r = subprocess.run(["sumo", "--version"], capture_output=True,
                               text=True, timeout=20)
            _VERSION_SUMO = (r.stdout or "").splitlines()[0].strip() or "desconocida"
        except Exception:
            _VERSION_SUMO = "desconocida"
    return _VERSION_SUMO


# ----------------------------------------------------------------------
# Enlaces
# ----------------------------------------------------------------------

def _enlazar(origen: str, destino: str) -> None:
    """Enlace duro `destino -> origen`; si no se puede, copia."""
    if os.path.abspath(origen) == os.path.abspath(destino):
        return
    if os.path.lexists(destino):
        os.remove(destino)
    try:
        os.link(origen, destino)
    except OSError:
        shutil.copy2(origen, destino)


def desvincular(*rutas: str) -> None:
    """
    Rompe el enlace de un archivo que una herramienta va a sobrescribir.

    Sin esto, `netconvert -o mapa.net.xml` sobre un enlace duro escribiría
    DENTRO del archivo del almacén y dejaría corrupta una entrada que otras
    corridas dan por buena.
    """
    for r in rutas:
        if os.path.lexists(r):
            os.remove(r)


# ----------------------------------------------------------------------
# Recuperar / guardar
# ----------------------------------------------------------------------

def _dir(etapa: str, clave_: str) -> str:
    return os.path.join(dir_cache(), etapa, clave_)


def recuperar(etapa: str, clave_: str, nombres: list[str], destino: str) -> dict | None:
    """
    Si la etapa ya se calculó, enlaza sus archivos en `destino` y devuelve el
    `meta` guardado. Si no, devuelve None y no toca nada.

    Una entrada solo vale si tiene `meta.json`: se escribe al final, así que
    si el proceso murió a medias la entrada queda incompleta y se ignora.
    """
    if not activo() or not clave_:
        return None
    d = _dir(etapa, clave_)
    meta_p = os.path.join(d, "meta.json")
    if not os.path.isfile(meta_p):
        return None
    if not all(os.path.isfile(os.path.join(d, n)) for n in nombres):
        return None
    os.makedirs(destino, exist_ok=True)
    for n in nombres:
        _enlazar(os.path.join(d, n), os.path.join(destino, n))
    with open(meta_p, encoding="utf-8") as f:
        return json.load(f)


def _xml_invalido_para_sumo(ruta: str) -> bool:
    """
    ¿El XML lleva en su cabecera un comentario con '--'?

    Las herramientas de SUMO copian la línea de comandos (con las rutas) en un
    comentario. Si alguna ruta tiene '--', el XML es inválido y SUMO lo rechaza
    al leerlo ("'--' sequence is illegal in comment"). Guardar ese archivo en el
    almacén envenenaría todas las corridas futuras con la misma clave.
    """
    if not ruta.endswith(".xml"):
        return False
    try:
        with open(ruta, "rb") as f:
            cabecera = f.read(65536)
    except OSError:
        return False
    i = 0
    while True:
        a = cabecera.find(b"<!--", i)
        if a < 0:
            return False
        b = cabecera.find(b"-->", a + 4)
        if b < 0:
            return False
        if b"--" in cabecera[a + 4:b]:
            return True
        i = b + 3


def guardar(etapa: str, clave_: str, origen: str, nombres: list[str],
            meta: dict | None = None) -> None:
    """Guarda los archivos recién producidos en `origen` bajo su clave."""
    if not activo() or not clave_:
        return
    if any(_xml_invalido_para_sumo(os.path.join(origen, n)) for n in nombres):
        print(f"  [almacen] no se guarda '{etapa}': el XML tiene '--' en un comentario "
              f"(¿ruta con doble guion?); SUMO no podría leerlo", flush=True)
        return
    d = _dir(etapa, clave_)
    os.makedirs(d, exist_ok=True)
    for n in nombres:
        _enlazar(os.path.join(origen, n), os.path.join(d, n))
    m = dict(meta or {})
    m.update({"etapa": etapa, "clave": clave_, "archivos": list(nombres),
              "guardado": datetime.now().isoformat(timespec="seconds"),
              "bytes": sum(os.path.getsize(os.path.join(d, n)) for n in nombres)})
    # meta.json al final y por sustitución atómica: es la marca de "entrada completa".
    tmp = os.path.join(d, "meta.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2, ensure_ascii=False)
    os.replace(tmp, os.path.join(d, "meta.json"))


# ----------------------------------------------------------------------
# claves.json de la corrida
# ----------------------------------------------------------------------

def claves_leer(carpeta: str) -> dict:
    try:
        with open(os.path.join(carpeta, ARCHIVO_CLAVES), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def claves_escribir(carpeta: str, **nuevas) -> dict:
    """Añade claves al `claves.json` de la corrida sin borrar las que había."""
    actuales = claves_leer(carpeta)
    actuales.update({k: v for k, v in nuevas.items() if v is not None})
    os.makedirs(carpeta, exist_ok=True)
    with open(os.path.join(carpeta, ARCHIVO_CLAVES), "w", encoding="utf-8") as f:
        json.dump(actuales, f, indent=2)
    return actuales


# ----------------------------------------------------------------------
# Diagnóstico
# ----------------------------------------------------------------------

def resumen() -> dict:
    """{etapa: {"entradas": n, "mb": tamaño}} — para `scn estado`."""
    raiz = dir_cache()
    salida = {}
    if not os.path.isdir(raiz):
        return salida
    for etapa in sorted(os.listdir(raiz)):
        d = os.path.join(raiz, etapa)
        if not os.path.isdir(d):
            continue
        n, total = 0, 0
        for entrada in os.listdir(d):
            de = os.path.join(d, entrada)
            if os.path.isfile(os.path.join(de, "meta.json")):
                n += 1
                total += sum(os.path.getsize(os.path.join(de, a))
                             for a in os.listdir(de) if a != "meta.json")
        salida[etapa] = {"entradas": n, "mb": total / 1e6}
    return salida
