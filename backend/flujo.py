"""
flujo.py — el flujo M1→M2→M3, sin estado global ni dependencia de la web
========================================================================
Hasta ahora las etapas del proyecto vivían **dentro de los endpoints** de
`api/main.py`, apoyadas en un diccionario global `STATE`. Eso funciona para una
interfaz con un solo usuario, pero impide reutilizarlas: un CLI que quisiera
lanzar campañas por lotes tendría que duplicar la lógica, y dos corridas a la
vez se pisarían el estado.

Este módulo extrae esas etapas a **funciones puras**: reciben lo que necesitan,
devuelven un objeto con el resultado y no guardan nada entre llamadas. La API y
el CLI pasan a ser dos clientes del mismo código.

    generar_escenario(...)     -> Escenario     (M1: OSM + SUMO + parseo)
    filtrar_candidatas(...)    -> Candidatas    (M1: grado + clustering)
    simular_conectividad(...)  -> Conectividad  (M2: SUMO + LoS V2I/V2V)

La optimización (M3) ya vivía aparte, en `optimizacion/optimizar_rsu.py`.

Dos decisiones de diseño
------------------------
1. **Los errores se lanzan como `ErrorFlujo`**, no como `HTTPException`. El
   núcleo no sabe que existe una web: la API traduce la excepción a un código
   HTTP y el CLI la imprime y termina con un código de salida.

2. **El cronómetro es opcional.** Las funciones aceptan `registro`, cualquier
   objeto con `etapa()`, `subetapa()` y `nota()`. La API le pasa su
   `api.cronometro`; quien no quiera medir no pasa nada y se usa un registro
   mudo. Así el núcleo no depende del módulo de medición de la interfaz.
"""

import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, field

from . import almacen
from .descargar_osm import descargar_mapa_osm, leer_origen
from .sumo_pipeline import ejecutar_pipeline_sumo, SEMILLA_POR_DEFECTO
from .parsear_xml import (parsear_junctions, parsear_edificios,
                          obtener_proyeccion, filtrar_junctions_rsu)
from .simulacion_sumo import ejecutar_simulacion_sumo, parsear_fcd
from .visibilidad import (generar_tuplas_visibilidad, guardar_tuplas_json,
                          generar_tuplas_v2v, guardar_tuplas_v2v_json)


# Version del calculo de linea de vista. Entra en la clave de la etapa "los":
# si se cambia el algoritmo hay que subirla, o el almacen serviria tuplas
# calculadas con el metodo viejo.
VERSION_LOS = 1


def _leer_json(ruta: str):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


class ErrorFlujo(Exception):
    """
    Falló una etapa del flujo.

    Lleva `etapa` (cuál) y `codigo` (400 si el problema es de la petición —un
    área imposible de descargar—, 409 si falta un paso previo, 500 si reventó
    una herramienta). La API lo traduce a HTTP; el CLI lo imprime.
    """

    def __init__(self, mensaje: str, etapa: str = "", codigo: int = 500):
        super().__init__(mensaje)
        self.etapa = etapa
        self.codigo = codigo


# ----------------------------------------------------------------------
# Registro de progreso opcional
# ----------------------------------------------------------------------

class _Medicion:
    """Lo que devuelve una etapa cuando no se está midiendo nada."""
    segundos = 0.0


class RegistroMudo:
    """
    Registro que no hace nada. Es el valor por defecto: permite usar el núcleo
    sin arrastrar el cronómetro de la interfaz.
    """

    @contextmanager
    def etapa(self, nombre: str):
        yield _Medicion()

    @contextmanager
    def subetapa(self, nombre: str):
        yield _Medicion()

    def nota(self, texto: str) -> None:
        pass


# ----------------------------------------------------------------------
# Resultados de cada etapa
# ----------------------------------------------------------------------

@dataclass
class Escenario:
    """Lo que produce M1: el mapa convertido y listo para simular."""
    carpeta: str
    bbox: tuple                     # (min_lon, min_lat, max_lon, max_lat)
    num_vehiculos: int
    tiempo_min: int
    semilla: int
    osm_path: str
    net_xml: str
    poly_xml: str
    junctions: dict                 # {id: {"x", "y", ...}}
    edificios: dict                 # {id: [[x, y], ...]}
    proy: object                    # proyección para pasar a lat/lon
    pasos: list = field(default_factory=list)   # resultado de cada herramienta
    claves: dict = field(default_factory=dict)  # claves de reutilización (almacen.py)
    origen_osm: dict = field(default_factory=dict)  # de dónde salió el mapa (extracto/Overpass)

    @property
    def tiempo_simulacion_s(self) -> float:
        return self.tiempo_min * 60.0


@dataclass
class Candidatas:
    """RSU candidatas tras filtrar por grado y agrupar espacialmente."""
    rsus: dict                      # {id_junction: {"x", "y", "grado"}}
    min_grado: int
    radio_cluster: float
    n_junctions: int                # cuántas había antes de filtrar

    @property
    def n(self) -> int:
        return len(self.rsus)

    @property
    def reduccion_pct(self) -> float:
        return 100.0 * (1 - self.n / max(self.n_junctions, 1))


@dataclass
class Conectividad:
    """Lo que produce M2: enlaces V2I y V2V por instante."""
    datos_fcd: dict                 # {t: [vehículos]}
    tuplas_v2i: list                # [{"t", "vehiculo", "rsu", "distancia"}]
    tuplas_v2v: list
    matrices_v2v: dict              # {t: {"vehiculos": [...], "A": [[...]]}}
    est_v2i: dict
    est_v2v: dict
    radio_obu: float
    step_min: int
    bidireccional: bool

    @property
    def timesteps(self) -> list:
        return sorted(float(t) for t in self.datos_fcd.keys())


# ----------------------------------------------------------------------
# M1 — escenario
# ----------------------------------------------------------------------

def generar_escenario(bbox: tuple, carpeta: str, num_vehiculos: int = 100,
                      tiempo_min: int = 120, semilla: int | None = None,
                      registro=None) -> Escenario:
    """
    Descarga el área, la convierte con SUMO y extrae junctions y edificios.

    Parámetros:
        bbox: (min_lon, min_lat, max_lon, max_lat).
        carpeta: dónde dejar los archivos del escenario.
        num_vehiculos, tiempo_min: demanda y duración simulada.
        semilla: fija la generación de rutas y la simulación, para que el
            escenario se pueda repetir. `None` usa SEMILLA_POR_DEFECTO.
        registro: cronómetro opcional (ver RegistroMudo).

    Retorna:
        Escenario.

    Lanza:
        ErrorFlujo si falla la descarga, alguna herramienta de SUMO o el parseo.
    """
    reg = registro or RegistroMudo()
    semilla = SEMILLA_POR_DEFECTO if semilla is None else int(semilla)
    min_lon, min_lat, max_lon, max_lat = bbox
    os.makedirs(carpeta, exist_ok=True)

    with reg.etapa("M1 - Generar escenario"):
        with reg.subetapa("Descarga OSM"):
            osm_path, err = descargar_mapa_osm(min_lon, min_lat, max_lon,
                                               max_lat, carpeta)
        if err:
            raise ErrorFlujo(f"Descarga OSM: {err}", "descarga", 400)

        periodo = (tiempo_min * 60) / num_vehiculos
        # Las tres herramientas se cronometran por separado: juntas no se sabe
        # cuál cuesta, y con muchos vehículos randomTrips se lleva casi todo.
        with reg.subetapa("SUMO (netconvert + polyconvert + trips)"):
            pasos = ejecutar_pipeline_sumo(osm_path, carpeta,
                                           num_vehiculos=num_vehiculos,
                                           periodo_salida=periodo,
                                           semilla=semilla)
        for p in pasos:
            if p.get("segundos") is not None:
                reg.nota(f"{p['paso']:.<28} {p['segundos']:8.3f} s"
                         + ("   (reutilizado)" if p.get("cache") else ""))
        fallo = next((p for p in pasos if not p["exito"]), None)
        if fallo:
            raise ErrorFlujo(f"SUMO ({fallo['paso']}): {fallo['mensaje']}",
                             fallo["paso"], 500)

        net = os.path.join(carpeta, "mapa.net.xml")
        poly = os.path.join(carpeta, "mapa.poly.xml")
        archivos_parseo = ["junctions_limpias.json", "edificios_limpios.json"]
        claves = almacen.claves_leer(carpeta)
        clave_parseo = (almacen.clave("parseo", claves["red"], claves["poly"])
                        if claves.get("red") and claves.get("poly") else None)
        with reg.subetapa("Parseo junctions + edificios"):
            # El parseo solo depende de la red y de los poligonos: si los dos
            # salieron del almacen, sus JSON tambien estan ahi. Con una ciudad
            # son ~20 s y decenas de MB que no hace falta rehacer.
            meta = almacen.recuperar("parseo", clave_parseo, archivos_parseo, carpeta)
            if meta:
                junctions = _leer_json(os.path.join(carpeta, archivos_parseo[0]))
                edificios = _leer_json(os.path.join(carpeta, archivos_parseo[1]))
                ej = ee = None
                reg.nota("junctions y edificios reutilizados")
            else:
                almacen.desvincular(*(os.path.join(carpeta, a) for a in archivos_parseo))
                junctions, ej = parsear_junctions(net, carpeta)
                edificios, ee = parsear_edificios(poly, carpeta)
                if not (ej or ee):
                    almacen.guardar("parseo", clave_parseo, carpeta, archivos_parseo,
                                    {"red": claves.get("red"), "poly": claves.get("poly")})
        if ej or ee:
            raise ErrorFlujo(f"Parseo: {ej or ee}", "parseo", 500)

        return Escenario(
            carpeta=carpeta, bbox=tuple(bbox), num_vehiculos=num_vehiculos,
            tiempo_min=tiempo_min, semilla=semilla, osm_path=osm_path,
            net_xml=net, poly_xml=poly, junctions=junctions,
            edificios=edificios, proy=obtener_proyeccion(net), pasos=pasos,
            claves=almacen.claves_leer(carpeta), origen_osm=leer_origen(carpeta),
        )


# ----------------------------------------------------------------------
# M1 — candidatas
# ----------------------------------------------------------------------

def filtrar_candidatas(escenario: Escenario, min_grado: int = 4,
                       radio_cluster: float = 20.0,
                       registro=None) -> Candidatas:
    """
    Reduce las junctions a RSU candidatas: descarta las de grado bajo y agrupa
    las que están a menos de `radio_cluster` metros.

    El grado es el número de VECINOS ÚNICOS en el grafo no dirigido, y el
    desempate del agrupamiento es por id ascendente, de modo que dos corridas
    sobre la misma red dan exactamente el mismo conjunto.
    """
    reg = registro or RegistroMudo()
    with reg.etapa(f"Filtrar RSU candidatas (grado>={min_grado}, "
                   f"cluster={radio_cluster:g} m)"):
        with reg.subetapa("Grado + clustering espacial"):
            rsus = filtrar_junctions_rsu(escenario.junctions, escenario.net_xml,
                                         min_grado=min_grado,
                                         radio_cluster=radio_cluster)
        return Candidatas(rsus=rsus, min_grado=min_grado,
                          radio_cluster=radio_cluster,
                          n_junctions=len(escenario.junctions))


# ----------------------------------------------------------------------
# M2 — conectividad
# ----------------------------------------------------------------------

def simular_conectividad(escenario: Escenario, candidatas: Candidatas,
                         radio_obu: float = 300.0, step_min: int = 2,
                         bidireccional: bool = True,
                         guardar_json: bool = True,
                         registro=None) -> Conectividad:
    """
    Corre SUMO, muestrea el FCD y calcula los enlaces con línea de vista.

    Usa la MISMA semilla con la que se generaron las rutas: con otra, la traza
    dejaría de corresponder al escenario.

    Parámetros:
        radio_obu: alcance de radio en metros (V2V y V2I).
        step_min: intervalo de muestreo en minutos.
        bidireccional: simetriza los enlaces V2V.
        guardar_json: escribe las cachés que lee la interfaz. Un CLI que solo
            quiera métricas puede desactivarlo y ahorrarse el disco.
    """
    reg = registro or RegistroMudo()
    step = step_min * 60.0
    carpeta = escenario.carpeta

    with reg.etapa(f"M2 - Simular conectividad (radio {radio_obu:g} m, "
                   f"muestreo {step_min} min)"):
        info = {}
        with reg.subetapa("Simulacion SUMO (trafico + FCD)"):
            fcd_path, err = ejecutar_simulacion_sumo(
                carpeta, escenario.tiempo_simulacion_s, periodo_fcd=step,
                semilla=escenario.semilla, info=info)
        if err:
            raise ErrorFlujo(f"Simulación SUMO: {err}", "sumo", 500)
        if info.get("cache"):
            reg.nota("traza FCD reutilizada (misma red, rutas, duracion y semilla)")

        with reg.subetapa("Parseo del FCD"):
            datos_fcd, ef = parsear_fcd(fcd_path, step)
        if ef:
            raise ErrorFlujo(f"Parseo FCD: {ef}", "fcd", 500)

        # La linea de vista depende de la traza, del conjunto de candidatas,
        # del radio y de la simetria; los edificios ya van implicitos en la
        # traza (misma red -> mismos poligonos). Con decenas de miles de
        # vehiculos es la parte cara de M2, y es O(V^2) por instante.
        claves = almacen.claves_leer(carpeta)
        clave_los = None
        if claves.get("fcd"):
            ids = hashlib.sha256(",".join(sorted(map(str, candidatas.rsus))).encode()).hexdigest()
            clave_los = almacen.clave("los", claves["fcd"], ids, float(radio_obu),
                                      bool(bidireccional), VERSION_LOS)
        archivos_los = ["tuplas_visibilidad.json", "tuplas_v2v.json"]
        meta = almacen.recuperar("los", clave_los, archivos_los, carpeta)

        if meta:
            with reg.subetapa("LoS V2I + V2V (reutilizados)"):
                d = _leer_json(os.path.join(carpeta, archivos_los[0]))
                tuplas_v2i, est_v2i = d["tuplas"], d["parametros"]
                d = _leer_json(os.path.join(carpeta, archivos_los[1]))
                tuplas_v2v, matrices_v2v, est_v2v = (d["tuplas_v2v"], d["matrices"],
                                                     d["parametros"])
        else:
            # Para poder guardarlos en el almacen hacen falta los JSON.
            guardar_json = guardar_json or bool(clave_los)
            almacen.desvincular(*(os.path.join(carpeta, a) for a in archivos_los))
            with reg.subetapa("LoS V2I (tuplas de visibilidad)"):
                tuplas_v2i, est_v2i = generar_tuplas_visibilidad(
                    datos_fcd, candidatas.rsus, escenario.edificios,
                    radio_obu=radio_obu)
                if guardar_json:
                    guardar_tuplas_json(tuplas_v2i, est_v2i, candidatas.rsus, carpeta)

            with reg.subetapa("LoS V2V (matriz A por instante)"):
                tuplas_v2v, matrices_v2v, est_v2v = generar_tuplas_v2v(
                    datos_fcd, escenario.edificios, radio_obu=radio_obu,
                    bidireccional=bidireccional)
                if guardar_json:
                    guardar_tuplas_v2v_json(tuplas_v2v, matrices_v2v, est_v2v, carpeta)
            if clave_los and guardar_json:
                almacen.guardar("los", clave_los, carpeta, archivos_los,
                                {"fcd": claves["fcd"], "n_candidatas": len(candidatas.rsus),
                                 "radio_obu": radio_obu, "bidireccional": bidireccional})

        return Conectividad(
            datos_fcd=datos_fcd, tuplas_v2i=tuplas_v2i, tuplas_v2v=tuplas_v2v,
            matrices_v2v=matrices_v2v, est_v2i=est_v2i, est_v2v=est_v2v,
            radio_obu=radio_obu, step_min=step_min, bidireccional=bidireccional,
        )
