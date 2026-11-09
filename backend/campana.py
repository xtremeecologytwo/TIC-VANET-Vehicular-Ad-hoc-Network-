"""
campana.py — campañas de pruebas por lotes (scn.py campana)
===========================================================
Una CAMPAÑA es un experimento factorial: un área, una semilla y unas listas de
niveles para cada factor; se ejecuta el producto cartesiano. Se describe en un
archivo YAML (campanas/*.yaml) que se versiona con el código: ese archivo ES la
especificación del experimento que se cita en la tesis.

Los factores
------------
  vehiculos : demanda. Máximo 5000 (por encima, M2/M3 colapsan en esta máquina).
  fisica    : configuración física de 802.11p, "TASA:CRITERIO" (p. ej. "6:r90")
              o "clasica". Cada una fija JUNTOS, desde el modelo del tutor
              (backend/capa_fisica.py, carpeta Luis Urquiza/):
                  radio OBU  = r80 / r90 de esa tasa (con interferente)
                  P[h]       = Gamma_h  (o Gamma_h - 1, según `p_h`)
                  Cap[r]     = alfa * C0(tasa, paquete)   en kb/s
                  L[s][v]    = carga por vehículo          en kb/s
              "clasica" = los valores de antes (300 m, P = 1..H, Cap 300, L 10),
              útil como línea base.
  H         : saltos máximos (1..6; Gamma_h existe hasta 6).
  filtrado  : conjunto de candidatas, por nombre (A..D del artículo V5) o
              definido en la sección `filtrados` del YAML.
  carga     : (opcional) multiplicador de la carga por vehículo L[s][v]:
              2 = el doble de `fisica_base.carga_kbps`. Solo cambia la Ec. 4,
              así que mide cuándo la capacidad de las RSU empieza a mandar.
  presupuesto: (opcional) número máximo de RSU (MaxR, Ec. 5). "libre" = sin
              límite; los demás niveles se definen en la sección
              `presupuestos` del YAML, con un valor fijo o uno por demanda.
Los dos opcionales solo entran en la clave del punto si el YAML los usa: las
claves de las campañas anteriores no cambian.

Lo que se reutiliza
-------------------
Con una semilla fija, M1 (red + rutas) depende solo de la demanda, y M2 (SUMO
+ línea de vista) de la demanda, el filtrado y el radio. El orden de ejecución
es vehículos -> filtrado -> física -> H, y la última simulación se guarda en
memoria: los puntos que solo cambian H no repiten nada salvo el CVR y CPLEX.
Entre campañas, el almacén de etapas (datos/cache) evita repetir SUMO.

Y M3 tampoco se repite: cada despliegue guarda la huella de su problema (el
CVR con todos sus parámetros + los topes). Si otra corrida, de esta o de otra
campaña, ya resolvió EXACTAMENTE el mismo problema, se copia su resultado
(p. ej. la carga x1 de una campaña y el presupuesto "libre" de otra).

M3 con tope
-----------
Cada punto resuelve el lexicográfico con un tope TOTAL (por defecto 5400 s =
1 h 30, la regla del tutor) repartido por nivel: `reparto_tope` (por defecto
optimizar_rsu.FRACCIONES_NIVEL) y, si el punto tiene MaxR, `reparto_tope_limitado`
(por defecto FRACCIONES_NIVEL_LIMITADO: con el número de RSU limitado el
difícil es el nivel 1). Si no termina, se guarda la mejor solución hallada y
el estado lo dice ("multi-objective non-optimal").

En paralelo
-----------
Con `paralelo` > 1, este proceso prepara los puntos (simulación + CVR, uno a
uno, que es rápido) y reparte las optimizaciones entre varios procesos, cada
uno con su parte de los núcleos. Un punto solo se lanza si su memoria estimada
cabe en la RAM libre: los pesados esperan turno en vez de llevar a Windows a
paginar. Solo este proceso escribe en el catálogo.

Reanudar
--------
Cada punto tiene una clave (`punto`). Si ya hay una corrida HECHA de esa clave
con su despliegue en el catálogo, se salta. Cortar con Ctrl+C y volver a lanzar
la misma campaña continúa donde quedó.

Varias semillas
---------------
Con `semillas: [42, 1, 2, ...]` en vez de `semilla`, la campaña se repite con
cada semilla (otro tráfico sobre la misma área y las mismas candidatas). Cada
semilla es una campaña aparte en el catálogo, `<nombre>_s<semilla>`, con su
huella, su carpeta y su reanudación; todas llevan `familia: <nombre>`, que es
lo que junta `scn.py reporte --semillas` para dar medias e intervalos.
"""

import copy
import hashlib
import itertools
import json
import os
import signal
import sys
import time
import traceback

import yaml

from . import flujo
from . import capa_fisica
from .catalogo import Catalogo, registrar_corrida_completa, manifest_actualizar
from .exportar_dat import construir_datos_opl, escribir_dat
from .sumo_pipeline import SEMILLA_POR_DEFECTO, _hilos, _ram_disponible_gb

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# optimizar_rsu se importa por nombre (así lo hacen la API y los scripts)
if os.path.join(_RAIZ, "optimizacion") not in sys.path:
    sys.path.insert(0, os.path.join(_RAIZ, "optimizacion"))
DATOS = os.path.join(_RAIZ, "datos")
CATALOGO = os.path.join(DATOS, "catalogo.sqlite")

MAX_VEHICULOS = 5000          # regla de trabajo: por encima, M2/M3 colapsan
TOPE_M3_S = 5400.0            # 1 h 30 por optimización (indicación del tutor)

# Configuraciones de filtrado del artículo V5 (suplemento_V5/ejecutar_experimentos.py)
FILTRADOS_V5 = {"A": {"gmin": 3, "rho": 15.0}, "B": {"gmin": 3, "rho": 20.0},
                "C": {"gmin": 4, "rho": 20.0}, "D": {"gmin": 5, "rho": 25.0}}

FISICA_BASE = {"paquete_bytes": 1000, "escenario": "with_interference",
               "alfa": 0.80, "carga_kbps": 80.0, "p_h": "gamma"}

LIBRE = "libre"               # nivel del factor presupuesto sin límite de RSU

# Memoria de un M3 en función de |CVR| (medido: v5000_A_3-r80_H3, 301 090
# tuplas -> pico de 3,1 GB a los 150 s de CPLEX). Con el árbol de B&B
# acotado por `workmem` (lo que pasa de ahí va a disco), no crece mucho más.
GB_BASE_M3 = 0.3
GB_POR_TUPLA_M3 = 1.0e-5
MEMORIA_CPLEX_MB = 1024       # workmem por proceso al resolver en paralelo
RESERVA_GB = 2.5              # para este proceso (simulación + CVR) y el sistema
ESPERA_MAX_S = 900            # tras 15 min sin sitio, un punto deja de cederlo a otros


class ErrorCampana(Exception):
    pass


# ======================================================================
# Especificación
# ======================================================================

def cargar_spec(ruta: str) -> dict:
    """Lee y valida un YAML de campaña; completa los valores por defecto."""
    with open(ruta, encoding="utf-8") as f:
        spec = yaml.safe_load(f) or {}
    return validar_spec(spec, ruta)


def validar_spec(spec: dict, ruta: str | None = None) -> dict:
    def falta(campo):
        raise ErrorCampana(f"la campaña{' ' + ruta if ruta else ''} no define `{campo}`")

    for campo in ("nombre", "area", "factores"):
        if campo not in spec:
            falta(campo)
    spec.setdefault("descripcion", "")
    if "semillas" in spec:
        if "semilla" in spec:
            raise ErrorCampana("usa `semilla` (una) o `semillas` (una lista), no las dos")
        s = spec["semillas"]
        # type(x) is int: en YAML, `true` también sería un int para isinstance
        if (not isinstance(s, list) or not s or not all(type(x) is int and x >= 0 for x in s)
                or len(set(s)) != len(s)):
            raise ErrorCampana("`semillas` debe ser una lista de enteros >= 0 sin repetir, "
                               "p. ej. [42, 1, 2]")
    else:
        spec.setdefault("semilla", SEMILLA_POR_DEFECTO)
    spec.setdefault("duracion_min", 60)
    spec.setdefault("muestreo_min", 5)
    spec.setdefault("tope_m3_s", TOPE_M3_S)
    spec["fisica_base"] = {**FISICA_BASE, **(spec.get("fisica_base") or {})}
    if spec["fisica_base"]["p_h"] != "gamma":
        # Con "extra" (Gamma_h - 1) la Ec. 4 también multiplicaría la carga por
        # ~0,05 en vez de ~1,05: la capacidad de cada RSU quedaría unas 20 veces
        # más holgada. Hasta separar el P del objetivo del de la capacidad, solo
        # se admite gamma.
        raise ErrorCampana("fisica_base.p_h: solo se admite 'gamma' (con 'extra' la capacidad "
                           "de la Ec. 4 quedaría ~20 veces más holgada)")
    spec["filtrados"] = {**FILTRADOS_V5, **(spec.get("filtrados") or {})}
    from optimizar_rsu import FRACCIONES_NIVEL, FRACCIONES_NIVEL_LIMITADO
    for campo, defecto in (("reparto_tope", FRACCIONES_NIVEL),
                           ("reparto_tope_limitado", FRACCIONES_NIVEL_LIMITADO)):
        r = spec.get(campo) or list(defecto)
        if (not isinstance(r, list) or len(r) != 3
                or not all(isinstance(x, (int, float)) and x > 0 for x in r)):
            raise ErrorCampana(f"`{campo}` debe ser una lista de 3 pesos positivos "
                               f"(nivel 1, 2 y 3), p. ej. [1, 4, 1]")
        spec[campo] = r

    fac = spec["factores"]
    opcionales = [c for c in ("carga", "presupuesto") if c in fac]
    for campo in ("vehiculos", "fisica", "H", "filtrado", *opcionales):
        if campo not in fac:
            falta(f"factores.{campo}")
        if not isinstance(fac[campo], list) or not fac[campo]:
            fac[campo] = [fac[campo]]
    for m in fac.get("carga", []):
        if not isinstance(m, (int, float)) or m <= 0:
            raise ErrorCampana(f"carga = {m!r}: se espera un multiplicador positivo (1, 2, 3...)")
    if "presupuesto" in fac:
        spec.setdefault("presupuestos", {})
        for nivel in fac["presupuesto"]:
            for v in fac["vehiculos"]:
                max_rsu_de(spec, nivel, v)              # valida que esté definido
    for v in fac["vehiculos"]:
        if int(v) > MAX_VEHICULOS:
            raise ErrorCampana(f"vehiculos = {v} supera el máximo de {MAX_VEHICULOS}")
    for h in fac["H"]:
        if not 1 <= int(h) <= capa_fisica.H_MAX:
            raise ErrorCampana(f"H = {h} fuera de 1..{capa_fisica.H_MAX}")
    for f in fac["filtrado"]:
        if f not in spec["filtrados"]:
            raise ErrorCampana(f"filtrado '{f}' no definido (hay: {', '.join(spec['filtrados'])})")
    for f in fac["fisica"]:
        fisica_de(str(f), spec["fisica_base"], 1)        # valida que se pueda calcular
    return spec


def por_semilla(spec: dict) -> list[dict]:
    """
    Una campaña con `semillas`, desdoblada en una campaña por semilla
    (`<nombre>_s<semilla>`, con `familia` y la lista completa en
    `semillas_familia`). Sin `semillas`, la propia campaña.
    """
    if "semillas" not in spec:
        return [spec]
    salida = []
    for s in spec["semillas"]:
        una = copy.deepcopy({k: v for k, v in spec.items() if k != "semillas"})
        una.update(nombre=f"{spec['nombre']}_s{s}", semilla=int(s), familia=spec["nombre"],
                   semillas_familia=list(spec["semillas"]))
        salida.append(una)
    return salida


def orden_por_semilla(specs: list[dict], semilla: int | None = None) -> list[tuple[int, dict]]:
    """
    Orden de ejecución de varias campañas: semilla a semilla (la 1.ª semilla de
    todas, luego la 2.ª...), para que al cortar a medias queden semillas
    COMPLETAS de cada campaña. Devuelve (índice de la campaña en `specs`, spec
    de una semilla). Con `semilla`, solo esa.
    """
    unidades = []
    for i, spec in enumerate(specs):
        for k, una in enumerate(por_semilla(spec)):
            if semilla is None or una["semilla"] == semilla:
                unidades.append((k, i, una))
    unidades.sort(key=lambda u: (u[0], u[1]))
    return [(i, una) for _, i, una in unidades]


def max_rsu_de(spec: dict, nivel, vehiculos) -> int | None:
    """MaxR de un nivel del factor `presupuesto` para una demanda (None = libre)."""
    if nivel == LIBRE:
        return None
    tabla = spec.get("presupuestos") or {}
    if nivel not in tabla:
        raise ErrorCampana(f"presupuesto '{nivel}' no definido en `presupuestos` "
                           f"(hay: {', '.join([LIBRE, *map(str, tabla)])})")
    valor = tabla[nivel]
    if isinstance(valor, dict):
        # Las claves son enteros en el YAML pero texto tras guardarlo en JSON
        valor = valor.get(int(vehiculos), valor.get(str(int(vehiculos))))
        if valor is None:
            raise ErrorCampana(f"presupuesto '{nivel}' no define un valor para {vehiculos} vehículos")
    if not isinstance(valor, int) or valor < 1:
        raise ErrorCampana(f"presupuesto '{nivel}': MaxR = {valor!r}, se espera un entero >= 1")
    return valor


def fisica_de(nivel: str, base: dict, H: int, carga_mult: float = 1.0) -> dict:
    """
    Parámetros físicos de un nivel del factor `fisica`, para un H dado.

    "clasica" -> los valores de antes; "TASA:CRITERIO" -> del modelo del tutor.
    `carga_mult` multiplica la carga por vehículo (factor `carga`).
    """
    nivel = str(nivel).strip()
    if nivel == "clasica":
        return {"nivel": "clasica", "tasa_mbps": None, "criterio": None,
                "radio_m": 300.0, "P": None, "cap_kbps": None,
                "carga_kbps": None if carga_mult == 1 else 10.0 * carga_mult,
                "fuente": "valores clásicos (sin modelo físico)"}
    try:
        tasa, criterio = nivel.split(":")
        tasa = float(tasa)
    except ValueError:
        raise ErrorCampana(f"física '{nivel}': se espera 'TASA:CRITERIO' (p. ej. 6:r90) o 'clasica'")
    try:
        r = capa_fisica.resumen(rate_mbps=tasa, packet_bytes=int(base["paquete_bytes"]),
                                escenario=base["escenario"], criterio=criterio,
                                alfa=float(base["alfa"]),
                                carga_kbps=float(base["carga_kbps"]) * float(carga_mult),
                                H=capa_fisica.H_MAX)
    except ValueError as e:
        raise ErrorCampana(f"física '{nivel}': {e}")
    P = r["modelo"]["P_gamma"] if base["p_h"] == "gamma" else r["modelo"]["P_extra"]
    return {"nivel": nivel, "tasa_mbps": tasa, "criterio": criterio,
            "radio_m": float(r["radio_elegido_m"]), "P": [float(x) for x in P[:int(H)]],
            "cap_kbps": float(r["modelo"]["cap_kbps"]), "carga_kbps": float(r["modelo"]["carga_kbps"]),
            "fuente": r["fuente"]["alcance"]}


def config_fija(spec: dict, bbox) -> dict:
    """
    Lo que NO es un factor pero cambia el resultado. Si cambia entre tandas de
    la misma campaña, los puntos viejos y los nuevos no son comparables.
    (tope_m3_s y descripcion quedan fuera: no cambian un óptimo demostrado.)
    """
    usados = {f: spec["filtrados"][f] for f in spec["factores"]["filtrado"]}
    return {"bbox": [round(float(x), 6) for x in bbox], "semilla": int(spec["semilla"]),
            "duracion_min": int(spec["duracion_min"]), "muestreo_min": int(spec["muestreo_min"]),
            "fisica_base": spec["fisica_base"], "filtrados": usados}


def huella(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:16]


def comprobar_huella(cat: Catalogo, spec: dict, bbox) -> list[str]:
    """
    Lanza ErrorCampana si la campaña ya tiene puntos hechos con otra
    configuración fija. Devuelve avisos (p. ej. puntos antiguos sin huella).
    """
    cfg = config_fija(spec, bbox)
    actual = huella(cfg)
    avisos = []
    for h, cfg_vieja in cat.huellas_campana(spec["nombre"]).items():
        if h is None:
            avisos.append("hay puntos de antes de la comprobación de configuración: no se pueden verificar")
            continue
        if h != actual:
            cambios = [k for k in cfg if (cfg_vieja or {}).get(k) != cfg[k]]
            raise ErrorCampana(
                f"la campaña '{spec['nombre']}' ya tiene puntos hechos con otra configuración "
                f"(cambió: {', '.join(cambios) or '?'}). Mezclarlos daría figuras engañosas: "
                f"usa otro `nombre` en el YAML para la configuración nueva.")
    return avisos


def clave_punto(veh, filtrado, fisica, H, carga=None, max_rsu=None, con_presupuesto=False) -> str:
    """
    Identificador estable y legible del punto (sirve de nombre de carpeta).

    `carga` (multiplicador) y el presupuesto solo se añaden si la campaña los
    usa como factor: v5000_C_6-r80_H3_x2, v5000_C_6-r80_H3_max60, ..._libre.
    """
    return (f"v{int(veh)}_{filtrado}_{str(fisica).replace(':', '-')}_H{int(H)}"
            + _sufijo(carga, max_rsu, con_presupuesto))


def _sufijo(carga, max_rsu, con_presupuesto) -> str:
    s = f"_x{float(carga):g}" if carga is not None else ""
    if con_presupuesto:
        s += f"_max{int(max_rsu)}" if max_rsu is not None else f"_{LIBRE}"
    return s


def puntos(spec: dict) -> list[dict]:
    """
    El producto cartesiano, en el orden que más reutiliza: veh -> filtrado ->
    física -> H -> carga -> presupuesto (los dos últimos no cambian la simulación).
    """
    fac = spec["factores"]
    cargas = fac.get("carga") or [None]
    presupuestos = fac.get("presupuesto") or [None]
    salida = []
    for veh, filt, fis, H, carga, pres in itertools.product(
            fac["vehiculos"], fac["filtrado"], fac["fisica"], fac["H"], cargas, presupuestos):
        f = spec["filtrados"][filt]
        mult = float(carga) if carga is not None else 1.0
        fi = fisica_de(str(fis), spec["fisica_base"], int(H), carga_mult=mult)
        max_rsu = max_rsu_de(spec, pres, veh) if pres is not None else None
        salida.append({"punto": clave_punto(veh, filt, fis, H, carga, max_rsu, pres is not None),
                       "vehiculos": int(veh), "filtrado": filt, "gmin": int(f["gmin"]),
                       "rho": float(f["rho"]), "fisica": fi, "H": int(H),
                       "carga_mult": None if carga is None else mult,
                       "presupuesto": pres, "max_rsu": max_rsu})
    return salida


def topes_de(spec: dict, max_rsu) -> list[float]:
    """Topes por nivel del punto: el reparto depende de si MaxR aprieta o no."""
    from optimizar_rsu import repartir_tope
    reparto = spec["reparto_tope_limitado"] if max_rsu is not None else spec["reparto_tope"]
    return repartir_tope(float(spec["tope_m3_s"]), reparto)


# ======================================================================
# Un punto
# ======================================================================

class _Memo:
    """La última simulación (M1+M2) en memoria: la reutilizan los puntos que solo cambian H/física."""
    clave = None
    valor = None


def ejecutar_punto(cat: Catalogo, *, optimizar=True, tope_m3_s=TOPE_M3_S, topes=None,
                   **kw) -> dict:
    """
    M1 -> filtrado -> M2 -> CVR -> (M3) -> catálogo + manifest. Devuelve un resumen.

    `kw` son los argumentos de `preparar_punto`. `topes` (por nivel) prevalece
    sobre el reparto por defecto de `tope_m3_s`.

    Lanza flujo.ErrorFlujo / otras excepciones si algo falla; la corrida, si
    llegó a abrirse, queda marcada como fallida.
    """
    from optimizar_rsu import repartir_tope

    prep = preparar_punto(cat, **kw)
    datos = prep.pop("datos")
    if optimizar:
        if topes is None:
            topes = repartir_tope(tope_m3_s)
        clave = clave_m3(datos, topes)
        copia = m3_reutilizado(cat, clave)
        if copia is not None:
            res, seg, origen = copia
        else:
            origen = None
            try:
                res, seg = resolver_m3(datos, topes, memoria_mb=memoria_secuencial_mb())
            except Exception as e:
                cat.cerrar_corrida(prep["uuid"], error=f"M3: {type(e).__name__}: {e}")
                raise
        registrar_m3(cat, prep, res, seg, topes=topes, clave=clave, origen=origen)
    prep["resumen"]["segundos"] = time.perf_counter() - prep["t_ini"]
    return prep["resumen"]


def preparar_punto(cat: Catalogo, *, bbox, nombre_area, vehiculos, duracion_min, semilla,
                   gmin, rho, fisica: dict, H, muestreo_min, campana, punto, filtrado=None,
                   registro=None, memo: _Memo | None = None, base_carpetas=None,
                   cfg_fija: dict | None = None, carga_mult=None, max_rsu=None,
                   presupuesto=None) -> dict:
    """
    Todo menos M3: M1 -> filtrado -> M2 -> CVR -> catálogo + manifest.

    Devuelve {"uuid", "datos" (el CVR, para M3), "resumen", "t_ini", ...}.
    """
    if int(vehiculos) > MAX_VEHICULOS:
        raise ErrorCampana(f"vehiculos = {vehiculos} supera el máximo de {MAX_VEHICULOS}")
    reg = registro or flujo.RegistroMudo()
    t_ini = time.perf_counter()
    radio = float(fisica["radio_m"])

    base = base_carpetas or os.path.join(DATOS, "corridas", campana or "sueltas")
    carpeta_sim = os.path.join(base, f"v{vehiculos}_t{duracion_min}_s{semilla}"
                                     f"_g{gmin}r{rho:g}_R{radio:g}")
    carpeta_pto = os.path.join(carpeta_sim, f"H{H}_{str(fisica['nivel']).replace(':', '-')}"
                               + _sufijo(carga_mult, max_rsu, presupuesto is not None))
    os.makedirs(carpeta_pto, exist_ok=True)

    clave_sim = (tuple(bbox), vehiculos, duracion_min, semilla, gmin, rho, radio, muestreo_min)
    tiempos: dict = {}
    if memo is not None and memo.clave == clave_sim:
        esc, cand, con, tiempos_sim = memo.valor
        tiempos.update(tiempos_sim)
        reutilizada = True
    else:
        t0 = time.perf_counter()
        esc = flujo.generar_escenario(tuple(bbox), carpeta_sim, num_vehiculos=vehiculos,
                                      tiempo_min=duracion_min, semilla=semilla, registro=reg)
        cand = flujo.filtrar_candidatas(esc, min_grado=gmin, radio_cluster=rho, registro=reg)
        con = flujo.simular_conectividad(esc, cand, radio_obu=radio, step_min=muestreo_min,
                                         registro=reg)
        tiempos.update(getattr(reg, "tiempos", {}) or {})
        tiempos["M1+M2 (s)"] = time.perf_counter() - t0
        if memo is not None:
            memo.clave, memo.valor = clave_sim, (esc, cand, con, dict(tiempos))
        reutilizada = False

    # ---- CVR con la física del punto ----
    t0 = time.perf_counter()
    extra = {}
    if fisica.get("P"):
        extra["penalizaciones"] = list(fisica["P"])
    if fisica.get("cap_kbps"):
        extra["cap_real"] = float(fisica["cap_kbps"])
    if fisica.get("carga_kbps"):
        extra["carga_default"] = float(fisica["carga_kbps"])
    datos = construir_datos_opl(con.matrices_v2v, con.tuplas_v2i, sorted(cand.rsus), H=H,
                                max_rsu=max_rsu, solo_rsu_conectados=True, **extra)
    escribir_dat(datos, os.path.join(carpeta_pto, "dataset.dat"))
    tiempos["CVR + exportacion"] = time.perf_counter() - t0

    factores = {"vehiculos": vehiculos, "filtrado": filtrado, "gmin": gmin, "rho": rho,
                "fisica": fisica["nivel"], "tasa_mbps": fisica["tasa_mbps"],
                "criterio": fisica["criterio"], "radio_m": radio, "P": fisica["P"],
                "cap_kbps": fisica["cap_kbps"], "carga_kbps": fisica["carga_kbps"], "H": H,
                "carga_mult": carga_mult, "presupuesto": presupuesto, "max_rsu": max_rsu,
                "duracion_min": duracion_min, "muestreo_min": muestreo_min, "semilla": semilla,
                "fuente_fisica": fisica["fuente"]}
    if cfg_fija is not None:
        factores["huella"] = huella(cfg_fija)
        factores["config_fija"] = cfg_fija
    uuid_, agregadas, _ = registrar_corrida_completa(
        cat, esc=esc, cand=cand, con=con, datos=datos, carpeta=carpeta_sim,
        carpeta_corrida=carpeta_pto, H=H, campana=campana, tiempos=tiempos,
        hilos=_hilos(vehiculos), nombre_area=nombre_area, punto=punto, factores=factores)

    resumen = {"uuid": uuid_, "punto": punto, "carpeta": carpeta_pto, "metricas": agregadas,
               "Y": cand.n, "reutilizada": reutilizada, "despliegue": None}
    manifest_actualizar(carpeta_pto, origen="cli", uuid=uuid_, campana=campana, punto=punto,
                        bbox=list(bbox), nombre_area=nombre_area, factores=factores,
                        claves=esc.claves, origen_osm=esc.origen_osm, metricas=agregadas,
                        tiempos=tiempos)
    return {"uuid": uuid_, "datos": datos, "resumen": resumen, "t_ini": t_ini,
            "carpeta": carpeta_pto, "max_rsu": max_rsu}


# ======================================================================
# M3 de un punto
# ======================================================================

def clave_m3(datos: dict, topes) -> str:
    """
    Huella del problema de M3: el CVR con todos sus parámetros (P, Cap, L,
    MaxR...), el mapa a los ids reales y los topes. Misma huella = mismo
    problema = mismo resultado.
    """
    h = hashlib.sha256()
    for k in ("hmax", "rInf", "MaxR", "R", "S", "Vs", "Cost", "Cap", "P", "L", "CVR"):
        h.update(json.dumps(datos[k], sort_keys=True, default=str).encode())
    h.update(json.dumps((datos.get("mapas") or {}).get("int_a_rsu") or {},
                        sort_keys=True, default=str).encode())
    h.update(json.dumps({"lexicografico": True, "topes": topes}).encode())
    return h.hexdigest()[:32]


def m3_reutilizado(cat: Catalogo, clave: str):
    """(resultado, segundos, uuid de origen) de un M3 idéntico ya resuelto, o None."""
    if os.environ.get("SCN_CACHE", "1") == "0":
        return None
    f = cat.buscar_m3(clave)
    if f is None:
        return None
    res = {"status": f["status"], "objetivo": f["objetivo"],
           "objetivos": json.loads(f["objetivos"]) if f["objetivos"] else None,
           "n_rsu_elegidos": f["n_rsu"],
           "seleccionados_backend": [x for x in (f["ids"] or "").split(",") if x],
           "reparto": {"cobertura_pct": f["cobertura_pct"], "conectados": f["conectados"],
                       "desconectados": f["desconectados"], "directos": f["directos"],
                       "multisalto": f["multisalto"]},
           "segundos_solver": f["segundos_solver"],
           "topes_por_nivel": json.loads(f["topes"]) if f["topes"] else None,
           "trivial": f["objetivo"] is None}
    return res, f["segundos_total"] or 0.0, f["origen"] or f["uuid"]


def resolver_m3(datos: dict, topes, hilos=None, memoria_mb=None) -> tuple[dict, float]:
    """
    M3 de un punto -> (resultado de optimizar_rsu.optimizar, segundos).

    Corre igual en este proceso o en uno aparte (no toca el catálogo).
    """
    from optimizar_rsu import optimizar as resolver
    if not datos["CVR"] or len(datos["R"]) <= 1:
        # Nadie alcanza ninguna candidata: el "despliegue" es vacío y la
        # cobertura es 0 %, un resultado legítimo (no un fallo del solver).
        n = sum(len(datos["Vs"][s]) for s in datos["S"])
        return ({"status": "sin candidatas alcanzables", "objetivo": None, "objetivos": None,
                 "n_rsu_elegidos": 0, "seleccionados_backend": [],
                 "reparto": {"n_pares": n, "conectados": 0.0, "desconectados": float(n),
                             "cobertura_pct": 0.0, "directos": 0.0, "multisalto": 0.0,
                             "por_salto": {}},
                 "segundos_solver": 0.0, "topes_por_nivel": None, "trivial": True}, 0.0)
    t0 = time.perf_counter()
    res = resolver(datos, lexicografico=True, topes_por_nivel=topes, hilos=hilos,
                   memoria_mb=memoria_mb)
    return res, time.perf_counter() - t0


def registrar_m3(cat: Catalogo, prep: dict, res: dict, seg_total: float, *, topes,
                 clave=None, origen=None) -> dict:
    """
    Guarda el resultado de M3 de un punto preparado y devuelve el resumen del
    despliegue (también queda en prep["resumen"]["despliegue"]).

    Lanza KeyboardInterrupt si CPLEX fue interrumpido con Ctrl+C, y
    ErrorCampana si no hay solución útil; en ambos casos la corrida queda
    fallida y el punto se repite al reanudar.
    """
    from optimizar_rsu import estado_solver
    uuid_ = prep["uuid"]
    if res.get("interrumpido"):
        # Ctrl+C dentro de CPLEX: su manejador aborta el solve y vuelve
        # sin KeyboardInterrupt. Se marca la corrida y se propaga, para que
        # la campaña se detenga y el punto se repita al reanudar.
        cat.cerrar_corrida(uuid_, error=f"interrumpida durante M3 ({res['status']})")
        raise KeyboardInterrupt
    if res.get("sin_solucion") or (res.get("objetivo") is None and not res.get("trivial")):
        # Sin despliegue utilizable (error de CPLEX, memoria, nivel 1 sin
        # cobertura): no se guarda como resultado; queda fallida y se
        # reintenta al reanudar.
        cat.cerrar_corrida(uuid_, error=f"M3 sin solución útil: {res['status']}")
        raise ErrorCampana(f"M3 sin solución útil: {res['status']}")
    est = estado_solver(res["status"])
    cat.guardar_despliegue(
        uuid_, motor="docplex", lexicografico=True, max_rsu=prep.get("max_rsu"),
        limite_tiempo=sum(topes) if topes else None, status=res["status"],
        objetivo=res["objetivo"], objetivos=res.get("objetivos"),
        n_rsu=res["n_rsu_elegidos"], ids=res.get("seleccionados_backend"),
        cobertura=res.get("reparto"), segundos_solver=res.get("segundos_solver"),
        segundos_total=seg_total, topes=res.get("topes_por_nivel"),
        clave_m3=clave, origen=origen)
    d = {"n_rsu": res["n_rsu_elegidos"], "status": res["status"],
         "optimo": est["optimo"], "cortado": est["cortado"],
         "cobertura_pct": (res.get("reparto") or {}).get("cobertura_pct"),
         "segundos_solver": res.get("segundos_solver"),
         "topes": res.get("topes_por_nivel"), "objetivos": res.get("objetivos"),
         "reutilizado_de": origen}
    prep["resumen"]["despliegue"] = d
    manifest_actualizar(prep["carpeta"], despliegue={**d, "ids": res.get("seleccionados_backend"),
                                                     "reparto": res.get("reparto"),
                                                     "segundos_total": seg_total})
    return d


# ======================================================================
# Memoria y núcleos
# ======================================================================

def gb_estimados_m3(n_cvr: int) -> float:
    return GB_BASE_M3 + GB_POR_TUPLA_M3 * n_cvr


def memoria_secuencial_mb() -> float | None:
    """
    workmem de CPLEX al resolver un punto a la vez: casi toda la RAM libre
    (lo que pase de ahí va a disco, no a la paginación de Windows).
    """
    libre = _ram_disponible_gb()
    if libre is None:
        return None
    return max(512.0, (libre - RESERVA_GB) * 1024 * 0.7)


def _ignorar_ctrl_c():
    # En los procesos de M3: Ctrl+C solo debe abortar a CPLEX (que instala su
    # propio manejador mientras resuelve); fuera del solve lo atiende el
    # proceso principal, que los cierra a todos.
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def orden_pesados_primero(pendientes: list[dict]) -> list[dict]:
    """
    Los puntos más pesados primero (más vehículos, más candidatas, más radio y
    más saltos), para que las optimizaciones largas no queden para el final
    con el resto de núcleos parados. Los de una misma simulación siguen juntos.
    """
    return sorted(pendientes, key=lambda p: (-p["vehiculos"], p["gmin"], p["rho"],
                                             -p["fisica"]["radio_m"], -p["H"]))


# ======================================================================
# La campaña
# ======================================================================

def plan(spec: dict, cat: Catalogo, optimizar: bool = True) -> dict:
    """Cuántos puntos, cuántos ya hechos, y cuánto se reutiliza (sin ejecutar nada)."""
    pts = puntos(spec)
    hechos = [p for p in pts if cat.punto_hecho(spec["nombre"], p["punto"], optimizar)]
    m1 = {p["vehiculos"] for p in pts}
    m2 = {(p["vehiculos"], p["gmin"], p["rho"], p["fisica"]["radio_m"]) for p in pts}
    return {"puntos": pts, "n": len(pts), "hechos": len(hechos),
            "pendientes": [p for p in pts if p not in hechos],
            "simulaciones_M1": len(m1), "simulaciones_M2": len(m2)}


def procesos_auto() -> int:
    """
    Cuántas optimizaciones a la vez: una por cada 4 núcleos lógicos (CPLEX
    rinde poco por encima de 4-8 hilos en un mismo árbol), sin pasar de lo que
    cabe en la RAM libre si todas fueran de tamaño medio (~1,5 GB).
    """
    nucleos = os.cpu_count() or 1
    por_nucleos = max(1, nucleos // 4)
    libre = _ram_disponible_gb()
    if libre is None:
        return por_nucleos
    return max(1, min(por_nucleos, int((libre - RESERVA_GB) // 1.5)))


def ejecutar(spec: dict, *, bbox, archivo=None, optimizar=True, solo=None,
             registro_factory=None, imprimir=print, paralelo: int = 1) -> dict:
    """
    Ejecuta los puntos pendientes de la campaña. Sigue aunque un punto falle.
    Ctrl+C corta limpio: los puntos en curso quedan sin despliegue y se
    repiten al relanzar.

    paralelo: cuántas optimizaciones (M3) a la vez, cada una en su proceso y
    con núcleos / paralelo hilos. La simulación y el CVR se preparan en este
    proceso, uno a uno; solo este proceso escribe en el catálogo.
    """
    cat = Catalogo(CATALOGO)
    try:
        avisos = comprobar_huella(cat, spec, bbox)
    except ErrorCampana:
        cat.cerrar()
        raise
    for a in avisos:
        imprimir(f"  aviso: {a}")
    cfg = config_fija(spec, bbox)
    cat.registrar_campana(spec["nombre"], spec, archivo)
    p = plan(spec, cat, optimizar)
    pendientes = p["pendientes"][:solo] if solo else p["pendientes"]
    procesos = max(1, int(paralelo)) if optimizar else 1
    if procesos > 1:
        pendientes = orden_pesados_primero(pendientes)
    carpeta = os.path.join(DATOS, "corridas", spec["nombre"])
    os.makedirs(carpeta, exist_ok=True)
    bitacora = open(os.path.join(carpeta, "campana.log"), "a", encoding="utf-8")

    def log(linea):
        imprimir(linea)
        bitacora.write(time.strftime("%Y-%m-%d %H:%M:%S ") + linea + "\n")
        bitacora.flush()

    log(f"campaña {spec['nombre']}: {p['n']} puntos, {p['hechos']} ya hechos, "
        f"{len(pendientes)} a ejecutar ahora")

    # ---- reparto de núcleos y memoria ----
    hilos = memoria_mb = pool = None
    presupuesto_gb = None
    if procesos > 1:
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor
        nucleos = os.cpu_count() or 1
        hilos = max(1, nucleos // procesos)
        libre = _ram_disponible_gb()
        presupuesto_gb = max(1.0, (libre or 8.0) - RESERVA_GB)
        memoria_mb = MEMORIA_CPLEX_MB
        log(f"en paralelo: {procesos} optimizaciones a la vez, {hilos} hilos cada una "
            f"({nucleos} núcleos lógicos); RAM libre {libre or 0:.1f} GB -> hasta "
            f"{presupuesto_gb:.1f} GB para CPLEX (los puntos pesados esperan turno)")
        pool = ProcessPoolExecutor(max_workers=procesos, initializer=_ignorar_ctrl_c,
                                   mp_context=multiprocessing.get_context("spawn"))

    memo, n_hechos, n_fallidos = _Memo(), 0, 0
    t_campana = time.perf_counter()
    en_vuelo: dict = {}         # future -> lo que hace falta para registrar su M3

    def cerrado(info, d=None, error=None):
        """Anota en la bitácora un punto terminado (bien o mal)."""
        nonlocal n_hechos, n_fallidos
        etq = f"[{n_hechos + n_fallidos + 1}/{len(pendientes)}] {info['pt']['punto']}"
        if error is not None:
            n_fallidos += 1
            log(f"{etq}  FALLO: {type(error).__name__}: {error}")
            if not isinstance(error, ErrorCampana):
                bitacora.write("".join(traceback.format_exception(
                    type(error), error, error.__traceback__)) + "\n")
            return
        n_hechos += 1
        r = info["prep"]["resumen"]
        m = r["metricas"]
        texto = (f"{etq}  |CVR|={m['cvr']:,}  Y={r['Y']}"
                 + (" (sim. reutilizada)" if r["reutilizada"] else ""))
        if d:
            estado = "óptimo" if d["optimo"] else ("CORTADO por tiempo" if d["cortado"] else d["status"])
            cob = f"{d['cobertura_pct']:.1f} %" if d["cobertura_pct"] is not None else "-"
            texto += (f"  -> {d['n_rsu']} RSU, cobertura {cob}, {estado}, "
                      f"solver {d['segundos_solver'] or 0:.0f} s")
            if d.get("reutilizado_de"):
                texto += f" (M3 idéntico ya resuelto: {d['reutilizado_de']})"
        hechos_ya = n_hechos + n_fallidos
        restantes = len(pendientes) - hechos_ya
        eta = (time.perf_counter() - t_campana) / hechos_ya * restantes
        texto += (f"  [{time.perf_counter() - info['prep']['t_ini']:.0f} s; "
                  f"quedan {restantes}, ~{eta / 60:.0f} min]")
        log(texto)

    def terminar_m3(info, res, seg, origen=None):
        try:
            d = registrar_m3(cat, info["prep"], res, seg, topes=info["topes"],
                             clave=info["clave"], origen=origen)
        except ErrorCampana as e:
            cerrado(info, error=e)
            return
        cerrado(info, d)

    def recoger():
        """Espera a que termine al menos una optimización en curso y la registra."""
        from concurrent.futures import wait, FIRST_COMPLETED
        listos = ()
        while not listos:
            # En tramos de 1 s: en Windows una espera sin tope no deja pasar el
            # Ctrl+C hasta que termina el CPLEX en curso (que puede tardar horas).
            listos, _ = wait(list(en_vuelo), timeout=1.0, return_when=FIRST_COMPLETED)
        for fut in listos:
            info = en_vuelo.pop(fut)
            try:
                res, seg = fut.result()
            except Exception as e:  # noqa: BLE001 - error de CPLEX o proceso caído
                cat.cerrar_corrida(info["prep"]["uuid"], error=f"M3: {type(e).__name__}: {e}")
                cerrado(info, error=e)
                continue
            terminar_m3(info, res, seg)

    def cabe(gb):
        if not en_vuelo:
            return True              # siempre al menos una: si no, no avanzaría nunca
        if len(en_vuelo) >= procesos:
            return False
        if sum(i["gb"] for i in en_vuelo.values()) + gb > presupuesto_gb:
            return False
        libre = _ram_disponible_gb()
        return libre is None or libre - gb > 1.0

    def preparar(pt, memo_sim):
        """
        Simulación + CVR + catálogo de un punto. Devuelve lo necesario para
        lanzar su M3, o None si el punto ya quedó cerrado (fallo, sin M3, o M3
        idéntico ya resuelto).
        """
        info = {"pt": pt}
        reg = registro_factory() if registro_factory else None
        try:
            prep = preparar_punto(
                cat, bbox=bbox, nombre_area=spec["area"], vehiculos=pt["vehiculos"],
                duracion_min=int(spec["duracion_min"]), semilla=int(spec["semilla"]),
                gmin=pt["gmin"], rho=pt["rho"], fisica=pt["fisica"], H=pt["H"],
                muestreo_min=int(spec["muestreo_min"]), campana=spec["nombre"],
                punto=pt["punto"], filtrado=pt["filtrado"], registro=reg, memo=memo_sim,
                base_carpetas=carpeta, cfg_fija=cfg, carga_mult=pt.get("carga_mult"),
                max_rsu=pt.get("max_rsu"), presupuesto=pt.get("presupuesto"))
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001 - un punto roto no para la campaña
            cerrado(info, error=e)
            return None
        info["prep"] = prep
        info["datos"] = prep.pop("datos")
        if not optimizar:
            cerrado(info)
            return None
        info["topes"] = topes_de(spec, pt.get("max_rsu"))
        info["clave"] = clave_m3(info["datos"], info["topes"])
        copia = m3_reutilizado(cat, info["clave"])
        if copia is not None:
            res, seg, origen = copia
            terminar_m3(info, res, seg, origen)
            return None
        info["gb"] = gb_estimados_m3(len(info["datos"]["CVR"]))
        return info

    en_espera: list = []        # preparados que aún no caben (por si llega Ctrl+C)
    interrumpida = False
    try:
        if pool is None:
            for pt in pendientes:
                info = preparar(pt, memo)
                if info is None:
                    continue
                try:
                    res, seg = resolver_m3(info.pop("datos"), info["topes"],
                                           memoria_mb=memoria_secuencial_mb())
                except Exception as e:  # noqa: BLE001
                    cat.cerrar_corrida(info["prep"]["uuid"], error=f"M3: {type(e).__name__}: {e}")
                    cerrado(info, error=e)
                    continue
                terminar_m3(info, res, seg)
        else:
            # Los pesados primero; pero si el siguiente pesado no cabe en la RAM,
            # en vez de esperar a que termine otro (pueden ser horas) se adelantan
            # puntos ligeros del final de la cola para no dejar núcleos parados.
            # Cada extremo de la cola guarda su propia simulación en memoria.
            # Si uno lleva más de ESPERA_MAX_S esperando, se deja de adelantar a
            # otros hasta que entre (si no, los ligeros podrían no dejarle nunca).
            from collections import deque
            cola = deque(pendientes)
            memo_ligeros = _Memo()
            while cola or en_espera or en_vuelo:
                bloqueado = False
                for info in list(en_espera):
                    if cabe(info["gb"]):
                        en_espera.remove(info)
                        en_vuelo[pool.submit(resolver_m3, info.pop("datos"), info["topes"],
                                             hilos, memoria_mb)] = info
                    elif time.perf_counter() - info["t_espera"] > ESPERA_MAX_S:
                        bloqueado = True
                        break
                if (not bloqueado and cola and len(en_vuelo) < procesos
                        and len(en_espera) < procesos):
                    info = (preparar(cola.pop(), memo_ligeros) if en_espera
                            else preparar(cola.popleft(), memo))
                    if info is not None:
                        info["t_espera"] = time.perf_counter()
                        en_espera.append(info)
                    continue
                if en_vuelo:
                    recoger()
                # sin nada en curso, cabe() deja lanzar el primero en espera
    except KeyboardInterrupt:
        interrumpida = True
        log("interrumpida por el usuario (Ctrl+C): vuelve a lanzarla para continuar")
        fila = cat.con.execute("SELECT uuid FROM corrida WHERE campana = ? AND estado = 'corriendo'",
                               (spec["nombre"],)).fetchall()
        for f in fila:
            cat.cerrar_corrida(f["uuid"], error="interrumpida")
        # Las optimizaciones en curso (y las que esperaban turno) no llegan a
        # guardar despliegue: esos puntos se repiten al relanzar.
        for info in [*en_vuelo.values(), *en_espera]:
            cat.cerrar_corrida(info["prep"]["uuid"], error="interrumpida durante M3")
    finally:
        if pool is not None:
            for proc in list(getattr(pool, "_processes", {}).values()):
                proc.terminate()     # no esperar a un CPLEX que puede tardar horas
            pool.shutdown(wait=False, cancel_futures=True)
        log(f"fin: {n_hechos} hechos, {n_fallidos} fallidos en esta tanda")
        bitacora.close()
        cat.cerrar()
    return {"hechos": n_hechos, "fallidos": n_fallidos, "interrumpida": interrumpida}
