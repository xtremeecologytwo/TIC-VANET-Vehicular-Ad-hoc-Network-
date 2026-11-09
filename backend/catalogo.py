"""
catalogo.py — el registro de corridas de simulación
====================================================
Guarda **qué se ejecutó, con qué parámetros y qué salió**, para poder repetir
una corrida, comparar campañas y reutilizar trabajo ya hecho.

Dos principios
--------------
1. **El disco es la verdad; la base de datos es un índice.** Los artefactos
   pesados —`.net.xml` de cientos de MB, el FCD, el `.dat`— viven en carpetas.
   Aquí solo se guardan sus rutas, sus hashes y las métricas. El catálogo se
   puede **borrar y reconstruir** releyendo las carpetas sin perder nada.

2. **Las tablas siguen las etapas del flujo**, y cada una se identifica por una
   `clave` derivada de sus entradas. Eso da la reutilización gratis: antes de
   ejecutar una etapa se busca su clave; si ya existe, se salta. En la campaña
   del artículo V5, 7 corridas necesitaron **solo 3 simulaciones de SUMO**,
   porque cuatro configuraciones de filtrado compartían la misma movilidad.

Por qué SQLite
--------------
Viene incluido en Python: no hay servidor que instalar ni servicio que
mantener. El acceso es de un solo proceso y el volumen es pequeño —una fila por
corrida—, así que un motor cliente/servidor no aporta nada y sí cuesta memoria.
Además el catálogo es **un archivo**, que se puede adjuntar al material
suplementario del artículo.

El SQL es estándar a propósito (sin funciones propias de SQLite), de modo que
migrar a PostgreSQL el día que haga falta —varias máquinas escribiendo, un
despliegue web, o consultas espaciales con PostGIS— sea cambiar la conexión.

Uso:
    from backend.catalogo import Catalogo

    cat = Catalogo("datos/catalogo.sqlite")
    area_id = cat.registrar_area("quito-centro", bbox, osm_path)
    ...
    cat.cerrar()
"""

import hashlib
import json
import os
import platform
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime

# ----------------------------------------------------------------------
# Esquema
# ----------------------------------------------------------------------
# Cada tabla corresponde a una etapa del flujo. `clave` es el hash de las
# entradas de esa etapa: es lo que permite saber si ya se calculó antes.
ESQUEMA = """
CREATE TABLE IF NOT EXISTS area (
    id          INTEGER PRIMARY KEY,
    clave       TEXT    NOT NULL UNIQUE,
    nombre      TEXT    NOT NULL,
    min_lon     REAL    NOT NULL,
    min_lat     REAL    NOT NULL,
    max_lon     REAL    NOT NULL,
    max_lat     REAL    NOT NULL,
    osm_sha256  TEXT    NOT NULL,
    ruta_osm    TEXT    NOT NULL,
    descargada  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS red (
    id          INTEGER PRIMARY KEY,
    area_id     INTEGER NOT NULL REFERENCES area(id),
    clave       TEXT    NOT NULL UNIQUE,
    opciones    TEXT    NOT NULL,
    net_sha256  TEXT    NOT NULL,
    ruta        TEXT    NOT NULL,
    creada      TEXT    NOT NULL
);

-- Una movilidad = unas rutas y una traza. Depende de la SEMILLA: cambiarla
-- obliga a rehacer esta etapa, pero no el mapa ni la red.
CREATE TABLE IF NOT EXISTS movilidad (
    id            INTEGER PRIMARY KEY,
    red_id        INTEGER NOT NULL REFERENCES red(id),
    clave         TEXT    NOT NULL UNIQUE,
    n_vehiculos   INTEGER NOT NULL,
    duracion_s    REAL    NOT NULL,
    semilla       INTEGER NOT NULL,
    muestreo_s    REAL    NOT NULL,
    rou_sha256    TEXT,
    fcd_sha256    TEXT,
    ruta          TEXT    NOT NULL,
    creada        TEXT    NOT NULL
);

-- Las candidatas NO dependen de la movilidad: solo de la red y de (g_min, rho).
-- Por eso varias corridas con distinta demanda comparten el mismo conjunto.
CREATE TABLE IF NOT EXISTS candidatas (
    id             INTEGER PRIMARY KEY,
    red_id         INTEGER NOT NULL REFERENCES red(id),
    clave          TEXT    NOT NULL UNIQUE,
    min_grado      INTEGER NOT NULL,
    radio_cluster  REAL    NOT NULL,
    n              INTEGER NOT NULL,
    ids_sha256     TEXT    NOT NULL,
    creada         TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS corrida (
    id             INTEGER PRIMARY KEY,
    uuid           TEXT    NOT NULL UNIQUE,
    campana        TEXT,
    movilidad_id   INTEGER NOT NULL REFERENCES movilidad(id),
    candidatas_id  INTEGER NOT NULL REFERENCES candidatas(id),
    radio_obu      REAL    NOT NULL,
    H              INTEGER NOT NULL,
    bidireccional  INTEGER NOT NULL,
    estado         TEXT    NOT NULL,      -- pendiente | corriendo | hecha | fallida
    inicio         TEXT,
    fin            TEXT,
    error          TEXT,
    carpeta        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS resultado (
    corrida_id   INTEGER PRIMARY KEY REFERENCES corrida(id),
    n_instantes  INTEGER,
    N            INTEGER,     -- instancias vehiculo-instante
    K            INTEGER,     -- pares reales alcanzables
    Y            INTEGER,     -- candidatas usadas
    cvr          INTEGER,     -- |CVR| = K + N
    q_reach      REAL,        -- % de instancias que alcanzan alguna candidata
    k_por_n      REAL,
    m1           INTEGER,
    m2           INTEGER,
    m3           INTEGER,
    t_links_s    REAL,
    t_hops_s     REAL
);

-- 31 filas por corrida en vez de las miles de tuplas del CVR: responde
-- "como evoluciona la cobertura en el tiempo" sin abrir un solo .dat.
CREATE TABLE IF NOT EXISTS instante (
    corrida_id    INTEGER NOT NULL REFERENCES corrida(id),
    s             INTEGER NOT NULL,
    t             REAL    NOT NULL,
    n_vehiculos   INTEGER NOT NULL,
    pares_h1      INTEGER NOT NULL,
    pares_h2      INTEGER NOT NULL,
    pares_h3      INTEGER NOT NULL,
    sin_servicio  INTEGER NOT NULL,
    PRIMARY KEY (corrida_id, s)
);

-- Sin esto, un resultado de hace meses no se puede interpretar: las versiones
-- de SUMO y NumPy cambian el resultado, y el commit dice que codigo lo produjo.
CREATE TABLE IF NOT EXISTS entorno (
    corrida_id  INTEGER PRIMARY KEY REFERENCES corrida(id),
    python      TEXT,
    numpy       TEXT,
    sumo        TEXT,
    commit_git  TEXT,
    hilos       INTEGER,
    plataforma  TEXT
);

-- Resultado de M3 (el despliegue que eligio CPLEX). Una corrida puede no
-- tenerlo: el CLI de campanas se detiene en el CVR. Los ids van como texto
-- separado por comas: son pocos y no se consultan por separado.
CREATE TABLE IF NOT EXISTS despliegue (
    corrida_id       INTEGER PRIMARY KEY REFERENCES corrida(id),
    motor            TEXT,
    lexicografico    INTEGER,
    max_rsu          INTEGER,
    limite_tiempo    REAL,
    status           TEXT,
    objetivo         REAL,
    objetivos        TEXT,
    n_rsu            INTEGER,
    ids              TEXT,
    cobertura_pct    REAL,
    conectados       INTEGER,
    desconectados    INTEGER,
    directos         INTEGER,
    multisalto       INTEGER,
    segundos_solver  REAL,
    segundos_total   REAL
);

-- Una campana = un experimento por lotes (scn.py campana). `spec` es el
-- YAML completo con que se lanzo: es la especificacion del experimento.
CREATE TABLE IF NOT EXISTS campana (
    nombre       TEXT PRIMARY KEY,
    descripcion  TEXT,
    spec         TEXT NOT NULL,
    archivo      TEXT,
    creada       TEXT NOT NULL,
    actualizada  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_corrida_campana ON corrida(campana);
CREATE INDEX IF NOT EXISTS idx_corrida_estado  ON corrida(estado);
"""


# ----------------------------------------------------------------------
# Hashes y claves: viven en almacen.py porque los usa tambien la cache de
# etapas en disco. Se reexportan para que el resto del codigo no cambie.
# ----------------------------------------------------------------------
from .almacen import (sha_varios, sha_contenido_xml,  # noqa: E402
                      clave, version_sumo as _version_sumo)


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _commit_git() -> str | None:
    """Commit actual del repositorio, si lo hay. Sirve para saber qué código corrió."""
    try:
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        r = subprocess.run(["git", "-C", raiz, "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except Exception:
        return None


# ----------------------------------------------------------------------
# Catálogo
# ----------------------------------------------------------------------

class Catalogo:
    """
    Acceso al catálogo de corridas.

    Todos los métodos `registrar_*` son **idempotentes**: si la etapa ya está
    registrada con la misma clave, devuelven su id en vez de duplicarla. Eso es
    lo que convierte al catálogo en la caché del flujo.
    """

    def __init__(self, ruta: str = "datos/catalogo.sqlite"):
        os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
        self.ruta = ruta
        # timeout: con una campaña y la interfaz escribiendo a la vez, esperar
        # el turno en vez de fallar con "database is locked" a los 5 s.
        self.con = sqlite3.connect(ruta, timeout=60)
        self.con.row_factory = sqlite3.Row
        # WAL: permite leer mientras se escribe (la interfaz puede consultar el
        # catálogo mientras una campaña sigue corriendo).
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.executescript(ESQUEMA)
        self._migrar()
        self.con.commit()

    def _migrar(self) -> None:
        """
        Columnas añadidas después de crear catálogos que ya existen (CREATE
        TABLE IF NOT EXISTS no añade columnas a una tabla vieja).

        corrida.punto    : clave del punto de la campaña (para no repetirlo)
        corrida.factores : JSON con los niveles de cada factor y la
                           configuración física aplicada (radio, P[h], Cap, L)
        despliegue.topes : JSON con los topes por nivel del lexicográfico
        despliegue.clave_m3 : huella del problema de M3 (datos + topes); dos
                           corridas con la misma huella son el MISMO problema
        despliegue.origen : uuid de la corrida cuyo M3 se reutilizó (o NULL)
        """
        def columnas(tabla):
            return {r[1] for r in self.con.execute(f"PRAGMA table_info({tabla})")}
        c = columnas("corrida")
        if "punto" not in c:
            self.con.execute("ALTER TABLE corrida ADD COLUMN punto TEXT")
        if "factores" not in c:
            self.con.execute("ALTER TABLE corrida ADD COLUMN factores TEXT")
        d = columnas("despliegue")
        for col in ("topes", "clave_m3", "origen"):
            if col not in d:
                self.con.execute(f"ALTER TABLE despliegue ADD COLUMN {col} TEXT")
        self.con.execute("CREATE INDEX IF NOT EXISTS idx_corrida_punto ON corrida(campana, punto)")
        self.con.execute("CREATE INDEX IF NOT EXISTS idx_despliegue_m3 ON despliegue(clave_m3)")

    # -- utilidades internas -------------------------------------------
    def _uno(self, sql: str, args=()) -> sqlite3.Row | None:
        return self.con.execute(sql, args).fetchone()

    def _id_por_clave(self, tabla: str, clave_: str) -> int | None:
        fila = self._uno(f"SELECT id FROM {tabla} WHERE clave = ?", (clave_,))
        return fila["id"] if fila else None

    # -- etapas ---------------------------------------------------------
    def registrar_area(self, nombre: str, bbox: tuple, ruta_osm: str) -> int:
        """
        Un área congelada: el `.osm` descargado una vez y su hash.

        Se identifica por su CONTENIDO —el rectángulo y el hash del OSM—, nunca
        por el nombre: dos corridas del mismo sitio son la misma área aunque
        cada una se etiquete distinto. Identificarla por el nombre hacía que
        cada corrida creara un área nueva, y con ella una red y una movilidad
        nuevas: justo el trabajo que este catálogo existe para no repetir.
        """
        sha = sha_varios(ruta_osm)
        k = clave("area", *bbox, sha)
        existente = self._id_por_clave("area", k)
        if existente:
            return existente
        cur = self.con.execute(
            "INSERT INTO area(clave, nombre, min_lon, min_lat, max_lon, max_lat,"
            " osm_sha256, ruta_osm, descargada) VALUES (?,?,?,?,?,?,?,?,?)",
            (k, nombre, *bbox, sha, ruta_osm, _ahora()))
        self.con.commit()
        return cur.lastrowid

    def registrar_red(self, area_id: int, ruta_net: str, opciones: str) -> int:
        # El hash es del CONTENIDO, no de los bytes: netconvert estampa la
        # fecha de generación en la cabecera, así que dos redes idénticas
        # hechas en momentos distintos no coinciden byte a byte.
        sha = sha_contenido_xml(ruta_net)
        k = clave("red", area_id, opciones, sha)
        existente = self._id_por_clave("red", k)
        if existente:
            return existente
        cur = self.con.execute(
            "INSERT INTO red(area_id, clave, opciones, net_sha256, ruta, creada)"
            " VALUES (?,?,?,?,?,?)",
            (area_id, k, opciones, sha, ruta_net, _ahora()))
        self.con.commit()
        return cur.lastrowid

    def registrar_movilidad(self, red_id: int, n_vehiculos: int, duracion_s: float,
                            semilla: int, muestreo_s: float, carpeta: str,
                            ruta_rou: str | None = None,
                            ruta_fcd: str | None = None) -> int:
        """
        Unas rutas + su traza. La clave incluye la SEMILLA: con otra semilla es
        otra movilidad, aunque el resto de parámetros coincidan.
        """
        k = clave("movilidad", red_id, n_vehiculos, duracion_s, semilla, muestreo_s)
        existente = self._id_por_clave("movilidad", k)
        if existente:
            return existente
        cur = self.con.execute(
            "INSERT INTO movilidad(red_id, clave, n_vehiculos, duracion_s, semilla,"
            " muestreo_s, rou_sha256, fcd_sha256, ruta, creada)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (red_id, k, n_vehiculos, duracion_s, semilla, muestreo_s,
             sha_contenido_xml(ruta_rou) if ruta_rou else None,
             sha_contenido_xml(ruta_fcd) if ruta_fcd else None,
             carpeta, _ahora()))
        self.con.commit()
        return cur.lastrowid

    def registrar_candidatas(self, red_id: int, min_grado: int,
                             radio_cluster: float, rsus: dict) -> int:
        k = clave("candidatas", red_id, min_grado, radio_cluster)
        existente = self._id_por_clave("candidatas", k)
        if existente:
            return existente
        ids = hashlib.sha256(",".join(sorted(map(str, rsus))).encode()).hexdigest()
        cur = self.con.execute(
            "INSERT INTO candidatas(red_id, clave, min_grado, radio_cluster, n,"
            " ids_sha256, creada) VALUES (?,?,?,?,?,?,?)",
            (red_id, k, min_grado, radio_cluster, len(rsus), ids, _ahora()))
        self.con.commit()
        return cur.lastrowid

    # -- corridas -------------------------------------------------------
    def abrir_corrida(self, movilidad_id: int, candidatas_id: int, carpeta: str,
                      radio_obu: float, H: int, bidireccional: bool = True,
                      campana: str | None = None, punto: str | None = None,
                      factores: dict | None = None) -> str:
        """Crea una corrida en estado `corriendo` y devuelve su uuid."""
        u = uuid.uuid4().hex[:12]
        self.con.execute(
            "INSERT INTO corrida(uuid, campana, movilidad_id, candidatas_id,"
            " radio_obu, H, bidireccional, estado, inicio, carpeta, punto, factores)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (u, campana, movilidad_id, candidatas_id, radio_obu, H,
             int(bidireccional), "corriendo", _ahora(), carpeta, punto,
             json.dumps(factores, ensure_ascii=False) if factores else None))
        self.con.commit()
        return u

    def cerrar_corrida(self, uuid_: str, error: str | None = None) -> None:
        self.con.execute(
            "UPDATE corrida SET estado = ?, fin = ?, error = ? WHERE uuid = ?",
            ("fallida" if error else "hecha", _ahora(), error, uuid_))
        self.con.commit()

    def _id_corrida(self, uuid_: str) -> int:
        fila = self._uno("SELECT id FROM corrida WHERE uuid = ?", (uuid_,))
        if fila is None:
            raise KeyError(f"no existe la corrida {uuid_}")
        return fila["id"]

    def guardar_resultado(self, uuid_: str, **campos) -> None:
        """Guarda las métricas agregadas de una corrida."""
        cid = self._id_corrida(uuid_)
        columnas = ["n_instantes", "N", "K", "Y", "cvr", "q_reach", "k_por_n",
                    "m1", "m2", "m3", "t_links_s", "t_hops_s"]
        valores = [campos.get(c) for c in columnas]
        self.con.execute(
            f"INSERT OR REPLACE INTO resultado(corrida_id, {', '.join(columnas)})"
            f" VALUES ({', '.join('?' * (len(columnas) + 1))})",
            (cid, *valores))
        self.con.commit()

    def guardar_instantes(self, uuid_: str, filas: list[dict]) -> None:
        """Resumen por instante: unas pocas decenas de filas por corrida."""
        cid = self._id_corrida(uuid_)
        self.con.executemany(
            "INSERT OR REPLACE INTO instante(corrida_id, s, t, n_vehiculos,"
            " pares_h1, pares_h2, pares_h3, sin_servicio) VALUES (?,?,?,?,?,?,?,?)",
            [(cid, f["s"], f["t"], f["n_vehiculos"], f.get("pares_h1", 0),
              f.get("pares_h2", 0), f.get("pares_h3", 0), f["sin_servicio"])
             for f in filas])
        self.con.commit()

    def guardar_entorno(self, uuid_: str, hilos: int | None = None) -> None:
        """Versiones y commit: sin esto, un resultado viejo no se puede interpretar."""
        try:
            import numpy
            v_numpy = numpy.__version__
        except ImportError:
            v_numpy = None
        self.con.execute(
            "INSERT OR REPLACE INTO entorno(corrida_id, python, numpy, sumo,"
            " commit_git, hilos, plataforma) VALUES (?,?,?,?,?,?,?)",
            (self._id_corrida(uuid_), sys.version.split()[0], v_numpy,
             _version_sumo(), _commit_git(), hilos, platform.platform()))
        self.con.commit()

    def guardar_despliegue(self, uuid_: str, *, motor: str, lexicografico: bool,
                           max_rsu: int | None, limite_tiempo: float | None,
                           status: str, objetivo: float | None, objetivos,
                           n_rsu: int, ids, cobertura: dict | None,
                           segundos_solver: float | None,
                           segundos_total: float | None,
                           topes: list | None = None,
                           clave_m3: str | None = None,
                           origen: str | None = None) -> None:
        """El despliegue que devolvio el solver para esta corrida (M3)."""
        cob = cobertura or {}
        self.con.execute(
            "INSERT OR REPLACE INTO despliegue(corrida_id, motor, lexicografico,"
            " max_rsu, limite_tiempo, status, objetivo, objetivos, n_rsu, ids,"
            " cobertura_pct, conectados, desconectados, directos, multisalto,"
            " segundos_solver, segundos_total)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self._id_corrida(uuid_), motor, int(bool(lexicografico)), max_rsu,
             limite_tiempo, status, objetivo,
             json.dumps(objetivos) if objetivos is not None else None,
             n_rsu, ",".join(str(i) for i in (ids or [])),
             cob.get("cobertura_pct"), cob.get("conectados"),
             cob.get("desconectados"), cob.get("directos"), cob.get("multisalto"),
             segundos_solver, segundos_total))
        self.con.execute("UPDATE despliegue SET topes = ?, clave_m3 = ?, origen = ? WHERE corrida_id = ?",
                         (json.dumps(topes) if topes is not None else None, clave_m3, origen,
                          self._id_corrida(uuid_)))
        self.con.commit()

    def buscar_m3(self, clave_m3: str) -> sqlite3.Row | None:
        """
        Un despliegue ya resuelto del MISMO problema (misma clave_m3) en una
        corrida hecha, o None. Si es la copia de otro, se devuelve igual: lleva
        el mismo resultado y apunta al original en `origen`.
        """
        return self._uno(
            "SELECT d.*, c.uuid FROM despliegue d JOIN corrida c ON c.id = d.corrida_id"
            " WHERE d.clave_m3 = ? AND c.estado = 'hecha' AND d.cobertura_pct IS NOT NULL"
            " ORDER BY d.corrida_id LIMIT 1", (clave_m3,))

    # -- campañas --------------------------------------------------------
    def registrar_campana(self, nombre: str, spec: dict, archivo: str | None = None) -> None:
        """Guarda (o actualiza) la especificación de una campaña."""
        ahora = _ahora()
        texto = json.dumps(spec, ensure_ascii=False, sort_keys=True)
        fila = self._uno("SELECT nombre FROM campana WHERE nombre = ?", (nombre,))
        if fila:
            self.con.execute("UPDATE campana SET spec = ?, archivo = ?, descripcion = ?,"
                             " actualizada = ? WHERE nombre = ?",
                             (texto, archivo, spec.get("descripcion"), ahora, nombre))
        else:
            self.con.execute("INSERT INTO campana(nombre, descripcion, spec, archivo, creada,"
                             " actualizada) VALUES (?,?,?,?,?,?)",
                             (nombre, spec.get("descripcion"), texto, archivo, ahora, ahora))
        self.con.commit()

    def spec_campana(self, nombre: str) -> dict | None:
        fila = self._uno("SELECT spec FROM campana WHERE nombre = ?", (nombre,))
        return json.loads(fila["spec"]) if fila else None

    def huellas_campana(self, campana: str) -> dict:
        """{huella: config_fija} de las corridas HECHAS de una campaña (None = corridas antiguas sin huella)."""
        salida = {}
        for f in self.con.execute("SELECT factores FROM corrida WHERE campana = ? AND estado = 'hecha'",
                                  (campana,)):
            fac = json.loads(f["factores"]) if f["factores"] else {}
            salida.setdefault(fac.get("huella"), fac.get("config_fija"))
        return salida

    def punto_hecho(self, campana: str, punto: str, con_despliegue: bool) -> str | None:
        """uuid de una corrida HECHA de ese punto (y con despliegue, si se pide), o None."""
        sql = ("SELECT c.uuid FROM corrida c"
               + (" JOIN despliegue d ON d.corrida_id = c.id" if con_despliegue else "")
               + " WHERE c.campana = ? AND c.punto = ? AND c.estado = 'hecha'"
               " ORDER BY c.id DESC LIMIT 1")
        fila = self._uno(sql, (campana, punto))
        return fila["uuid"] if fila else None

    # -- consultas ------------------------------------------------------
    def corridas(self, campana: str | None = None) -> list[sqlite3.Row]:
        sql = ("SELECT c.uuid, c.campana, c.estado, c.inicio, c.fin,"
               "       m.n_vehiculos, m.semilla, m.duracion_s,"
               "       k.min_grado, k.radio_cluster, k.n AS candidatas,"
               "       r.N, r.K, r.cvr, r.q_reach, r.t_links_s"
               "  FROM corrida c"
               "  JOIN movilidad m  ON m.id = c.movilidad_id"
               "  JOIN candidatas k ON k.id = c.candidatas_id"
               "  LEFT JOIN resultado r ON r.corrida_id = c.id")
        args = ()
        if campana:
            sql += " WHERE c.campana = ?"
            args = (campana,)
        return self.con.execute(sql + " ORDER BY c.id", args).fetchall()

    def resumen(self) -> dict:
        """Contadores rápidos, para `scn estado`."""
        def n(tabla):
            return self.con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        return {t: n(t) for t in ("area", "red", "movilidad", "candidatas",
                                  "corrida", "resultado", "instante", "despliegue",
                                  "campana")}

    def cerrar(self) -> None:
        self.con.close()


# ----------------------------------------------------------------------
# Registro de una corrida entera y manifiesto en disco
# ----------------------------------------------------------------------
# El CLI y la API hacen exactamente lo mismo al terminar: anotar cada etapa,
# abrir la corrida, guardar metricas, instantes y entorno. Vive aqui para
# que no haya dos versiones que se desincronicen.

def registrar_corrida_completa(cat: "Catalogo", *, esc, cand, con, datos: dict,
                               carpeta: str, H: int, campana: str | None = None,
                               tiempos: dict | None = None,
                               hilos: int | None = None,
                               nombre_area: str | None = None,
                               punto: str | None = None,
                               factores: dict | None = None,
                               carpeta_corrida: str | None = None) -> tuple[str, dict, list]:
    """
    Anota en el catalogo una corrida ya ejecutada (M1 -> M2 -> CVR).

    Parametros:
        esc, cand, con: los objetos de `backend.flujo` (Escenario, Candidatas,
            Conectividad).
        datos: el dict del CVR que devuelve `construir_datos_opl`.
        tiempos: {nombre_subetapa: segundos}; de aqui salen T_links y T_hops.
        punto, factores: identificación del punto de una campaña.
        carpeta_corrida: carpeta propia de la corrida si no es la del escenario
            (en una campaña varias corridas comparten la misma simulación).

    Retorna:
        (uuid de la corrida, metricas agregadas, filas por instante).
    """
    from .exportar_dat import metricas_cvr

    tiempos = tiempos or {}
    bbox = tuple(esc.bbox)
    area_id = cat.registrar_area(nombre_area or nombre_de_area(bbox), bbox, esc.osm_path)
    red_id = cat.registrar_red(area_id, esc.net_xml, "netconvert por defecto")
    mov_id = cat.registrar_movilidad(
        red_id, esc.num_vehiculos, esc.tiempo_simulacion_s, esc.semilla,
        con.step_min * 60.0, carpeta,
        os.path.join(carpeta, "mapa.rou.xml"), os.path.join(carpeta, "fcd.xml"))
    cand_id = cat.registrar_candidatas(red_id, cand.min_grado, cand.radio_cluster,
                                       cand.rsus)
    uuid_ = cat.abrir_corrida(mov_id, cand_id, carpeta_corrida or carpeta,
                              radio_obu=con.radio_obu, H=H,
                              bidireccional=con.bidireccional, campana=campana,
                              punto=punto, factores=factores)

    agregadas, filas = metricas_cvr(datos)
    agregadas["Y"] = cand.n
    # Si la línea de vista salió del almacén no se midió en esta corrida:
    # se guarda NULL (desconocido) y no 0, que parecería un cálculo instantáneo.
    if ("LoS V2I (tuplas de visibilidad)" in tiempos
            or "LoS V2V (matriz A por instante)" in tiempos):
        agregadas["t_links_s"] = (tiempos.get("LoS V2I (tuplas de visibilidad)", 0.0)
                                  + tiempos.get("LoS V2V (matriz A por instante)", 0.0))
    else:
        agregadas["t_links_s"] = None
    agregadas["t_hops_s"] = tiempos.get("CVR + exportacion", 0.0)

    cat.guardar_resultado(uuid_, **agregadas)
    cat.guardar_instantes(uuid_, filas)
    cat.guardar_entorno(uuid_, hilos=hilos)
    cat.cerrar_corrida(uuid_)
    return uuid_, agregadas, filas


def nombre_de_area(bbox: tuple) -> str:
    """
    Etiqueta legible de un rectangulo, para leerla en los informes.

    No identifica al area -de eso se encarga el hash del OSM-, asi que dos
    nombres distintos del mismo sitio no duplican nada.
    """
    o, s_, e, n_ = bbox
    return "area_%.4f_%.4f_%.4f_%.4f" % (o, s_, e, n_)


ARCHIVO_MANIFEST = "manifest.json"


def manifest_leer(carpeta: str) -> dict:
    try:
        with open(os.path.join(carpeta, ARCHIVO_MANIFEST), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def manifest_actualizar(carpeta: str, **campos) -> dict:
    """
    Escribe o completa el `manifest.json` de una corrida.

    Es la corrida describiendose a si misma: parametros, semilla, metricas y
    tiempos. Si el catalogo se borra, se reconstruye leyendo estos archivos.
    La web lo va rellenando clic a clic (M1 pone el bbox y la semilla, el
    filtrado sus parametros, M2 los suyos, M3 las metricas); el CLI lo
    escribe de una vez al final. Los campos nuevos sustituyen a los viejos.
    """
    m = manifest_leer(carpeta)
    m.update({k: v for k, v in campos.items() if v is not None})
    m["actualizado"] = _ahora()
    os.makedirs(carpeta, exist_ok=True)
    tmp = os.path.join(carpeta, ARCHIVO_MANIFEST + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2, ensure_ascii=False, default=str)
    os.replace(tmp, os.path.join(carpeta, ARCHIVO_MANIFEST))
    return m
