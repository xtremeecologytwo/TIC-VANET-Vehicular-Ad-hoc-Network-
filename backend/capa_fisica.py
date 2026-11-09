"""
capa_fisica.py — la capa física de IEEE 802.11p según las notas del tutor
=========================================================================
Hasta ahora tres números del modelo estaban puestos a ojo:

    radio_obu = 300 m          (M2: hasta dónde llega un enlace con línea de vista)
    P[h]      = 1, 2, …, H     (M3: cuánto "cuesta" servir a un vehículo a h saltos)
    Cap[r] = 300, L[s][v] = 10 (M3: capacidad de una RSU y carga de un vehículo)

El tutor entregó dos notas técnicas y un programa que los derivan de un modelo
físico publicado y reproducible con semilla (carpeta `Luis Urquiza/`):

1. **Alcance y multisalto** (`channel_functions.py`, `simulation_methodology.pdf`).
   Monte Carlo de la recepción de un paquete a cada distancia: propagación
   media de Sommer (Empirical Inexpensive, exponente 2.2), fading Rician
   (K=10), interferente co-canal a distancia U(10, 2000) m, ruido térmico kTB,
   sensibilidad del receptor y la curva PER de Reinoso-Chisaguano (modelo 7).
   De ahí salen `r80`/`r90` —la mayor distancia con P(éxito) ≥ 0,8 / 0,9— y
   el factor de penalización multisalto Γ_H = 1/P(ruta de H saltos).

2. **Capacidad unicast** (`ieee80211p_unicast_capacity.pdf`). El techo de una
   RSU después de los overheads MAC: C₀(R, L) = 8L / T₀, y la capacidad
   agregada de planificación α·C₀ con α ≈ 0,80 (contienda moderada).

Este módulo hace de puente: **importa el código del tutor tal cual** (no se
copia ni se modifica, para que lo que corre aquí sea exactamente lo que él
revisó), lee sus CSV oficiales cuando los parámetros coinciden con su
experimento, recalcula en vivo cuando no, y traduce todo a los parámetros que
consumen `simular_conectividad` (radio) y `construir_datos_opl` (P, Cap, L).

Dos observaciones para la defensa
---------------------------------
* Con el objetivo lexicográfico de tres niveles, `P[h]` solo actúa en el
  tercer nivel: decide entre despliegues que ya tienen la cobertura máxima
  con el mínimo de RSU. Su efecto es de desempate. En la suma ponderada
  clásica sí pesa de lleno.
* Los radios dependen de la distribución del interferente, la potencia, la
  sensibilidad, K, el tamaño de paquete y la PER —lo dice el propio tutor—:
  no se presentan como "alcance del estándar" sino como el alcance operativo
  bajo esas hipótesis.
"""

import csv
import importlib.util
import math
import os

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA_TUTOR = os.path.join(_RAIZ, "Luis Urquiza")

# ----------------------------------------------------------------------
# Parámetros del experimento del tutor (README.txt / parameters.json)
# ----------------------------------------------------------------------
TASAS_MBPS = [3.0, 4.5, 6.0, 9.0, 12.0, 18.0, 24.0, 27.0]
TAMANOS_B = [500, 1000]
CRITERIOS = {"r80": 0.80, "r90": 0.90}
ESCENARIOS = ["noise_only", "with_interference"]
SEMILLA_TUTOR = 20260914
MUESTRAS_TUTOR = 5000
H_MAX = 6
DISTANCIAS_M = np.arange(10.0, 1000.0 + 5.0, 5.0)
# Los kwargs físicos que reciben las funciones del tutor, con sus valores.
FISICA = dict(tx_power_dbm=24.0, frequency_hz=5.89e9, path_loss_exponent=2.2,
              rician_k=10.0, bandwidth_hz=10e6, temperature_k=290.0,
              interferer_min_m=10.0, interferer_max_m=2000.0)
MIN_SALTO_M = 10.0

# α recomendados en la nota de capacidad (tabla "Caso homogéneo").
ALFA = {"ligero": 0.84, "base": 0.80, "conservador": 0.72,
        "muy_conservador": 0.63, "estres": 0.55}

# Configuración de partida: el ejemplo que el tutor desarrolla en su documento
# (6 Mb/s, 1000 B) y el criterio que él mismo señala como más favorable al
# multisalto (r90). La carga por vehículo NO viene de las notas: 80 kb/s son
# 10 paquetes/s de 1000 B (un CAM a 10 Hz); es un supuesto pendiente de
# confirmar con el tutor.
POR_DEFECTO = dict(rate_mbps=6.0, packet_bytes=1000, escenario="with_interference",
                   criterio="r90", alfa=ALFA["base"], carga_kbps=80.0)

# ----------------------------------------------------------------------
# Capacidad unicast (nota técnica 2): C₀, C₁, α·C₀
# ----------------------------------------------------------------------
# Tabla "Tasas PHY IEEE 802.11p usadas en el cálculo": bits de datos por
# símbolo OFDM y tasa a la que se responde el ACK (supuesto analítico de Wang).
N_DBPS = {3.0: 24, 4.5: 36, 6.0: 48, 9.0: 72, 12.0: 96, 18.0: 144, 24.0: 192, 27.0: 216}
TASA_ACK = {3.0: 3.0, 4.5: 3.0, 6.0: 6.0, 9.0: 6.0, 12.0: 12.0, 18.0: 12.0, 24.0: 12.0, 27.0: 12.0}
T_PLCP_US = 40.0     # preámbulo 32 µs + símbolo SIGNAL 8 µs
SIFS_US = 32.0
AIFS_US = 110.0      # AC_BE: AIFSN=6 → 32 + 6·13
DELTA_US = 2.0       # propagación, por consistencia con Wang et al.
SLOT_US = 13.0
CW_MIN = 15
MAC_OVERHEAD_B = 28  # cabecera + FCS
ACK_B = 14


def _t_trama_us(n_bytes: int, rate_mbps: float) -> float:
    """Duración de una trama OFDM: PLCP + símbolos de 8 µs, con SERVICE (16 b) y TAIL (6 b)."""
    return T_PLCP_US + 8.0 * math.ceil((16 + 8 * n_bytes + 6) / N_DBPS[float(rate_mbps)])


def capacidad(rate_mbps: float, packet_bytes: int, alfa: float = ALFA["base"]) -> dict:
    """
    C₀, C₁ y la capacidad agregada α·C₀ de una RSU, en Mb/s.

        T₀ = T_D + SIFS + T_A + AIFS + 2δ        (un intercambio DATA/ACK sin backoff)
        C₀ = 8L / T₀                              (techo unicast antes de la contienda)
        C₁ = 8L / (T₀ + CWmin/2 · slot)           (una sola estación saturada)
        C_agg = α · C₀                            (varias estaciones compitiendo)

    Verificado contra las dos tablas de la nota (pruebas/capa_fisica.py):
    6 Mb/s y 500 B → C₀ = 4,158, C₁ = 3,775.
    """
    R = float(rate_mbps)
    L = int(packet_bytes)
    if R not in N_DBPS:
        raise ValueError(f"tasa PHY no soportada: {rate_mbps}")
    t_d = _t_trama_us(L + MAC_OVERHEAD_B, R)
    t_a = _t_trama_us(ACK_B, TASA_ACK[R])
    t0 = t_d + SIFS_US + t_a + AIFS_US + 2 * DELTA_US
    c0 = 8.0 * L / t0
    c1 = 8.0 * L / (t0 + CW_MIN / 2.0 * SLOT_US)
    return {"rate_mbps": R, "packet_bytes": L, "alfa": float(alfa),
            "t_data_us": t_d, "t_ack_us": t_a, "t0_us": t0,
            "c0_mbps": c0, "c1_mbps": c1, "eta1": c1 / R,
            "c_agg_mbps": float(alfa) * c0}


# ----------------------------------------------------------------------
# El código del tutor, importado tal cual
# ----------------------------------------------------------------------
_MODULO = None


def tutor():
    """
    `channel_functions.py` cargado desde `Luis Urquiza/`.

    Se importa por ruta (la carpeta tiene un espacio y no es un paquete) y
    solo la primera vez. No se copia a `backend/` a propósito: lo que se
    ejecuta es el archivo que él entregó, byte a byte.
    """
    global _MODULO
    if _MODULO is None:
        ruta = os.path.join(CARPETA_TUTOR, "channel_functions.py")
        if not os.path.isfile(ruta):
            raise FileNotFoundError(f"no está el código del tutor: {ruta}")
        spec = importlib.util.spec_from_file_location("channel_functions", ruta)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MODULO = mod
    return _MODULO


# ----------------------------------------------------------------------
# Sus resultados oficiales (los CSV que entregó)
# ----------------------------------------------------------------------
_CSV: dict[str, list[dict]] = {}


def _csv(nombre: str) -> list[dict]:
    """Filas de un CSV del tutor, cacheadas; lista vacía si no está."""
    if nombre not in _CSV:
        ruta = os.path.join(CARPETA_TUTOR, nombre)
        filas = []
        if os.path.isfile(ruta):
            with open(ruta, newline="", encoding="utf-8") as f:
                filas = list(csv.DictReader(f))
        _CSV[nombre] = filas
    return _CSV[nombre]


def csv_disponibles() -> bool:
    return all(_csv(n) for n in ("range_summary.csv", "multihop_results.csv",
                                 "distance_curves.csv"))


def _f(x) -> float | None:
    """float o None: los CSV traen '' y 'nan' donde no hubo radio."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def _fila_rango_tutor(rate: float, packet_bytes: int, escenario: str) -> dict | None:
    for r in _csv("range_summary.csv"):
        if (float(r["rate_mbps"]) == rate and int(r["packet_bytes"]) == packet_bytes
                and r["scenario"] == escenario):
            return r
    return None


def _curva_tutor(rate: float, packet_bytes: int, escenario: str) -> list[dict]:
    return [{"distance_m": float(r["distance_m"]),
             "success_probability": float(r["success_probability"])}
            for r in _csv("distance_curves.csv")
            if float(r["rate_mbps"]) == rate and int(r["packet_bytes"]) == packet_bytes
            and r["scenario"] == escenario]


def _multisalto_tutor(rate: float, packet_bytes: int, criterio: str) -> list[dict]:
    filas = [r for r in _csv("multihop_results.csv")
             if float(r["rate_mbps"]) == rate and int(r["packet_bytes"]) == packet_bytes
             and r["radius_criterion"] == criterio]
    return [{"n_hops": int(r["n_hops"]),
             "max_hop_distance_m": _f(r["max_hop_distance_m"]),
             "success_probability": _f(r["success_probability"]),
             "route_per": _f(r["route_per"]),
             "penalty_factor": _f(r["penalty_factor"]),
             "expected_extra_retransmissions": _f(r["expected_extra_retransmissions"]),
             "mean_hop_distance_m": _f(r["mean_hop_distance_m"])}
            for r in sorted(filas, key=lambda r: int(r["n_hops"]))]


# ----------------------------------------------------------------------
# Monte Carlo en vivo (mismas funciones, otra semilla u otro tamaño)
# ----------------------------------------------------------------------
_VIVO: dict[tuple, object] = {}


def curva_alcance(rate: float, packet_bytes: int, escenario: str,
                  semilla: int, n_paquetes: int) -> tuple[list[dict], dict]:
    """
    P(éxito) frente a distancia y los radios r80 / r90 / de sensibilidad.

    Es `simulate_distance_curve` + `reliable_radius` del tutor con SUS
    parámetros físicos. Con la semilla y el tamaño de su experimento no da
    exactamente sus CSV —él deriva un generador hijo distinto para cada
    combinación dentro de un bucle— pero sí la misma estadística.
    """
    clave = ("curva", rate, packet_bytes, escenario, semilla, n_paquetes)
    if clave not in _VIVO:
        cf = tutor()
        rng = np.random.default_rng(semilla)
        filas = cf.simulate_distance_curve(
            DISTANCIAS_M, packet_bytes, rate, rng, n_paquetes,
            with_interference=(escenario == "with_interference"), **FISICA)
        d = [r["distance_m"] for r in filas]
        p = [r["success_probability"] for r in filas]
        radios = {"sensitivity_radius_m": cf.sensitivity_radius_m(
                      rate, tx_power_dbm=FISICA["tx_power_dbm"],
                      frequency_hz=FISICA["frequency_hz"],
                      path_loss_exponent=FISICA["path_loss_exponent"])}
        for nombre, objetivo in CRITERIOS.items():
            radios[f"{nombre}_m"] = _f(cf.reliable_radius(d, p, objetivo))
        _VIVO[clave] = ([{"distance_m": float(a), "success_probability": float(b)}
                         for a, b in zip(d, p)], radios)
    return _VIVO[clave]


def multisalto(rate: float, packet_bytes: int, radio_m: float,
               semilla: int, n_rutas: int, h_max: int = H_MAX) -> list[dict]:
    """
    Γ_H para H = 1..h_max con saltos de longitud U(10, radio_m).

    Como en el experimento del tutor, los saltos se simulan SIEMPRE con
    interferente: el escenario solo decide de dónde sale el radio que acota
    la longitud del salto.
    """
    clave = ("multi", rate, packet_bytes, radio_m, semilla, n_rutas, h_max)
    if clave not in _VIVO:
        cf = tutor()
        rng = np.random.default_rng(semilla)
        filas = []
        for h in range(1, h_max + 1):
            r = cf.simulate_multihop(h, radio_m, packet_bytes, rate, rng, n_rutas,
                                     min_hop_distance_m=MIN_SALTO_M,
                                     with_interference=True, **FISICA)
            filas.append({"n_hops": h, "max_hop_distance_m": float(radio_m),
                          **{k: _f(v) for k, v in r.items()}})
        _VIVO[clave] = filas
    return _VIVO[clave]


# ----------------------------------------------------------------------
# De la física a los parámetros del modelo
# ----------------------------------------------------------------------

def penalizaciones(filas_multisalto: list[dict], H: int, modo: str = "gamma") -> list[float]:
    """
    P[1..H] a partir de Γ_h.

    `gamma`: P[h] = Γ_h (un salto directo ya cuesta ~1,05).
    `extra`: P[h] = Γ_h − 1 (solo las retransmisiones adicionales).
    Cuál de las dos es la correcta es la pregunta 4 al tutor; se ofrecen ambas.
    """
    gam = {int(f["n_hops"]): f["penalty_factor"] for f in filas_multisalto}
    salida = []
    for h in range(1, H + 1):
        g = gam.get(h)
        if g is None:
            raise ValueError(f"no hay Γ para H={h}")
        salida.append(float(g) if modo == "gamma" else float(g) - 1.0)
    return salida


def opciones() -> dict:
    """Lo que el panel necesita para pintar sus selectores."""
    return {"tasas_mbps": TASAS_MBPS, "tamanos_bytes": TAMANOS_B,
            "criterios": list(CRITERIOS), "escenarios": ESCENARIOS,
            "alfa": ALFA, "por_defecto": POR_DEFECTO, "h_max": H_MAX,
            "tutor_csv": csv_disponibles(), "semilla_tutor": SEMILLA_TUTOR,
            "muestras_tutor": MUESTRAS_TUTOR, "fisica": FISICA}


def resumen(rate_mbps: float = POR_DEFECTO["rate_mbps"],
            packet_bytes: int = POR_DEFECTO["packet_bytes"],
            escenario: str = POR_DEFECTO["escenario"],
            criterio: str = POR_DEFECTO["criterio"],
            alfa: float = POR_DEFECTO["alfa"],
            carga_kbps: float = POR_DEFECTO["carga_kbps"],
            H: int = H_MAX, semilla: int | None = None,
            n_muestras: int | None = None) -> dict:
    """
    Todo lo que hace falta para una configuración física: curva, radios,
    Γ_H, capacidad y los parámetros ya traducidos para M2 y M3.

    Sin `semilla` ni `n_muestras` se usan los CSV oficiales del tutor (su
    semilla 20260914 y 5000 muestras); con cualquiera de los dos se recalcula
    en vivo con su mismo código.
    """
    rate = float(rate_mbps)
    packet_bytes = int(packet_bytes)
    if rate not in N_DBPS:
        raise ValueError(f"tasa PHY no soportada: {rate_mbps}")
    if packet_bytes not in TAMANOS_B:
        raise ValueError(f"tamaño de paquete no soportado: {packet_bytes}")
    if escenario not in ESCENARIOS:
        raise ValueError(f"escenario desconocido: {escenario}")
    if criterio not in CRITERIOS:
        raise ValueError(f"criterio desconocido: {criterio}")
    H = max(1, min(int(H), H_MAX))
    en_vivo = semilla is not None or n_muestras is not None
    semilla = SEMILLA_TUTOR if semilla is None else int(semilla)
    n = MUESTRAS_TUTOR if n_muestras is None else int(n_muestras)

    # ---- alcance ----
    fila = None if en_vivo else _fila_rango_tutor(rate, packet_bytes, escenario)
    if fila is not None:
        radios = {"sensitivity_radius_m": _f(fila["sensitivity_radius_m"]),
                  "r80_m": _f(fila["r80_m"]), "r90_m": _f(fila["r90_m"])}
        curva = _curva_tutor(rate, packet_bytes, escenario)
        fuente_alcance = f"CSV del tutor (semilla {SEMILLA_TUTOR}, {MUESTRAS_TUTOR} paquetes/distancia)"
    else:
        curva, radios = curva_alcance(rate, packet_bytes, escenario, semilla, n)
        fuente_alcance = f"Monte Carlo en vivo (semilla {semilla}, {n} paquetes/distancia)"
    radio = radios.get(f"{criterio}_m")
    if radio is None:
        raise ValueError(f"con {rate:g} Mb/s y {packet_bytes} B ninguna distancia alcanza "
                         f"P(éxito) ≥ {CRITERIOS[criterio]:.0%}: no hay radio {criterio}")

    # ---- multisalto ----
    # El CSV del tutor solo cubre saltos acotados por los radios CON
    # interferente; para los de "solo ruido" hay que simular.
    filas = ([] if en_vivo or escenario != "with_interference"
             else _multisalto_tutor(rate, packet_bytes, criterio))
    if filas and all(f["penalty_factor"] is not None for f in filas):
        fuente_multi = f"CSV del tutor (semilla {SEMILLA_TUTOR}, {MUESTRAS_TUTOR} rutas/H)"
    else:
        filas = multisalto(rate, packet_bytes, radio, semilla, n)
        fuente_multi = f"Monte Carlo en vivo (semilla {semilla}, {n} rutas/H)"

    cap = capacidad(rate, packet_bytes, alfa)
    p_gamma = penalizaciones(filas, H_MAX, "gamma")
    p_extra = penalizaciones(filas, H_MAX, "extra")
    etiqueta = (f"{rate:g} Mb/s · {packet_bytes} B · {criterio} "
                f"{'con interferente' if escenario == 'with_interference' else 'solo ruido'}")

    return {
        "rate_mbps": rate, "packet_bytes": packet_bytes, "escenario": escenario,
        "criterio": criterio, "alfa": float(alfa), "carga_kbps": float(carga_kbps), "H": H,
        "fuente": {"alcance": fuente_alcance, "multisalto": fuente_multi},
        "radios": radios, "radio_elegido_m": float(radio),
        "curva": curva, "multisalto": filas, "capacidad": cap,
        # Lo que consumen M2 y M3. Cap y L van en la MISMA unidad (kb/s):
        # construir_datos_opl compara Σ L contra Cap en la Ec. 4.
        "modelo": {"radio_obu_m": float(radio), "P_gamma": p_gamma, "P_extra": p_extra,
                   "cap_kbps": cap["c_agg_mbps"] * 1000.0, "carga_kbps": float(carga_kbps)},
        "etiqueta": etiqueta,
    }
