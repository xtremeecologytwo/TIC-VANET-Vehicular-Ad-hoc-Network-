"""
Módulo de Automatización de SUMO
================================
Ejecuta secuencialmente las herramientas CLI de SUMO:
  1. netconvert  → genera la red vial (.net.xml)
  2. polyconvert → genera los polígonos (.poly.xml)
  3. randomTrips  → genera las rutas aleatorias (.rou.xml)
"""

import os
import sys
import subprocess
import time

# `correr` es subprocess.run + registro, para que 'Generar escenario'
# pueda cortar una corrida anterior que siguiera viva (ver procesos.py).
from .procesos import correr


# ============================================================
# PARALELISMO
# ============================================================
# `duarouter` (el que calcula las rutas dentro de randomTrips) es MONOHILO por
# defecto, y es la etapa mas cara de M1 con muchos vehiculos: es un camino
# minimo por vehiculo sobre toda la red. Medido con 50 000 vehiculos sobre una
# red de 379 MB, iba al 101 % de CPU -un solo nucleo de los 16- durante mas de
# una hora.
#
# Se le pasan dos cosas:
#   --routing-threads N   reparte las consultas entre N hilos.
#   --routing-algorithm   `astar` en vez del `dijkstra` por defecto. A* usa la
#                         distancia en linea recta como cota inferior, asi que
#                         explora muchisimos menos arcos. Es EXACTO: la
#                         heuristica es admisible, luego da los mismos caminos
#                         minimos que dijkstra, solo que antes.
#
# randomTrips reenvia a duarouter cualquier opcion con el prefijo `--duarouter-`
# (mecanismo `allowed_programs` de sumolib).
#
# Repartir tiene un COSTE FIJO: cada hilo monta su propia estructura de rutado
# sobre la red entera. Medido sobre una red real de 397 MB ajustando
# T(n) = fijo + n * coste_por_viaje con dos puntos (n = 200 y n = 2000):
#
#                     coste fijo    por viaje
#   dijkstra, 1 hilo      125 s      0,2074 s
#   astar,   16 hilos     220 s      0,0659 s     <- 3,15x mas rapido por viaje
#
# Los 16 hilos cuestan 95 s extra de arranque, asi que por debajo de
#   95 / (0,2074 - 0,0659) = ~670 viajes
# paralelizar SALE PEOR. Medido: con 200 vehiculos, 166,8 s -> 233,5 s.
# Por encima gana con holgura: extrapolado a 50 000, 175 min -> 59 min (3,0x).
#
# De ahi el umbral. No es un numero redondo elegido a ojo: es el punto de corte
# que sale de esas dos rectas, redondeado a la baja.
UMBRAL_HILOS = int(os.environ.get("SUMO_UMBRAL_HILOS", 700))

# Cada hilo de duarouter mantiene su propio estado de rutado sobre la red
# ENTERA, asi que la memoria crece casi linealmente con los hilos. Medido sobre
# una red de ~350 MB: ~1,0 GB con 1 hilo y ~6,9 GB con 16, o sea unos 0,4 GB por
# hilo adicional.
#
# Eso muerde: en una maquina de 13,7 GB, 16 hilos dejaron 0,3 GB libres y 3,6 GB
# de paginacion. Pasado ese punto el paralelismo NO acelera, frena: el sistema
# empieza a intercambiar con el disco. Por eso el numero de hilos se limita
# tambien por la memoria libre, no solo por los nucleos.
# Cuanta memoria hace falta es dificil de predecir: depende del tamano de la red,
# de cuantos hilos y de la fase. Medido sobre redes de ~360 MB: ~4,3 GB con 4
# hilos y ~6,9 GB con 16, o sea que el grueso lo pone la RED y no los hilos.
#
# Se intentaron dos formulas para recortar los hilos automaticamente y las dos
# salieron mal por falta de datos (una dio 4 hilos con 2,4 GB libres; la otra 1
# hilo con 6 GB). Un tope mal calibrado hace MAS dano que no tenerlo: estrangula
# el paralelismo a cambio de un ahorro sin demostrar. Asi que NO se recorta por
# memoria: se usan todos los nucleos —que es el comportamiento propio de SUMO— y
# se AVISA cuando la estimacion no cabe, para que se pueda decidir con criterio.
#
# Si la maquina va justa, la palanca es explicita: SUMO_HILOS=8, o cerrar
# aplicaciones antes de lanzar M1.
GB_ESTIMADOS_POR_MB_RED = 4.3 / 360.0   # solo para el aviso, no para recortar          # lo que anade cada hilo, escalado con la red


def _ram_disponible_gb() -> float | None:
    """
    Memoria fisica libre, en GB. None si no se puede averiguar.

    Se usa ctypes en vez de psutil para no anadir una dependencia por algo tan
    puntual. Fuera de Windows se devuelve None y no se aplica el limite.
    """
    try:
        import ctypes

        class _Mem(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        m = _Mem()
        m.dwLength = ctypes.sizeof(_Mem)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return None
        return m.ullAvailPhys / (1024.0 ** 3)
    except Exception:
        return None


# SUMO_HILOS=0 (o sin definir) usa todos los nucleos; un numero los fija.
def _hilos(n_trabajos: int | None = None, red_mb: float | None = None) -> int:
    """
    Nucleos a usar en las etapas paralelizables. Nunca menos de 1.

    n_trabajos: cuantas unidades de trabajo hay (viajes a rutar). Si se da y
        queda por debajo de UMBRAL_HILOS, devuelve 1: el arranque de los hilos
        costaria mas que el trabajo que reparten.
    red_mb: tamano del .net.xml en MB. Si se da, se comprueba si la memoria
        estimada cabe en la RAM libre y se AVISA si no; no se recorta nada
        (ver el comentario de GB_ESTIMADOS_POR_MB_RED).

    Un SUMO_HILOS explicito manda sobre el calculo automatico, pero NO sobre el
    umbral de trabajo: pedir 16 hilos para 50 viajes sigue sin tener sentido.
    """
    try:
        pedidos = int(os.environ.get("SUMO_HILOS", 0))
    except ValueError:
        pedidos = 0
    if n_trabajos is not None and n_trabajos < UMBRAL_HILOS:
        return 1
    hilos = max(1, pedidos or (os.cpu_count() or 1))
    if pedidos:
        return hilos          # eleccion explicita del usuario: se respeta

    libre = _ram_disponible_gb()
    if libre and red_mb:
        estimado = GB_ESTIMADOS_POR_MB_RED * red_mb
        if estimado > libre:
            print(f"  AVISO: duarouter necesitara ~{estimado:.1f} GB para una red "
                  f"de {red_mb:.0f} MB y hay {libre:.1f} GB libres. Windows "
                  f"paginara a disco y esto ira lento. Cierra aplicaciones, "
                  f"reduce el area, o fija SUMO_HILOS para usar menos memoria.")
    return hilos




def _contar_vehiculos(rou_path: str) -> int:
    """
    Cuantos vehiculos hay realmente en el .rou.xml.

    Con `--no-validate`, duarouter descarta en silencio los viajes que no puede
    rutar (calles sin salida, zonas desconectadas), asi que el numero pedido y
    el obtenido no tienen por que coincidir. Se cuenta el real para reportarlo
    en vez de repetir el pedido.
    """
    try:
        n = 0
        with open(rou_path, encoding="utf-8", errors="ignore") as f:
            for linea in f:
                n += linea.count("<vehicle ")
        return n
    except OSError:
        return 0


# ============================================================
# TIEMPOS MÁXIMOS DE CADA HERRAMIENTA
# ============================================================
# Son una red de seguridad para que la petición HTTP no se quede colgada para
# siempre si una herramienta de SUMO se atasca. NO son un límite de tamaño del
# área: con áreas grandes (una ciudad entera) hay que subirlos, porque el
# trabajo real crece con el nº de calles de la red.
#
# Se pueden ajustar sin tocar el código con la variable de entorno
# SUMO_TIMEOUT_S (segundos); vale para las tres herramientas.
#
#   Windows PowerShell:  $env:SUMO_TIMEOUT_S = "3600"
#   Linux / Mac:         export SUMO_TIMEOUT_S=3600
#
# Con 0 (o un valor negativo) se desactiva el límite: la herramienta corre
# hasta terminar, tarde lo que tarde.
TIMEOUT_POR_DEFECTO = 0.0   # 30 min por herramienta


def _timeout() -> float | None:
    """Lee SUMO_TIMEOUT_S del entorno. Devuelve None si se desactivó (<= 0)."""
    try:
        v = float(os.environ.get("SUMO_TIMEOUT_S", TIMEOUT_POR_DEFECTO))
    except ValueError:
        v = TIMEOUT_POR_DEFECTO
    return None if v <= 0 else v


def _msg_timeout(herramienta: str, limite: float | None) -> str:
    """Mensaje de error con el límite REAL que se aplicó y cómo subirlo."""
    cuanto = f"{limite:g}s" if limite else "sin límite"
    return (
        f"{herramienta} excedió el tiempo de espera ({cuanto}). El área "
        f"seleccionada es grande: sube el límite con la variable de entorno "
        f"SUMO_TIMEOUT_S (p. ej. 3600, o 0 para quitarlo) y reinicia la API, "
        f"o selecciona un área menor."
    )


def _buscar_random_trips() -> str:
    """
    Busca la ruta del script randomTrips.py.
    Primero intenta con SUMO_HOME, luego asume que está en el PATH.
    """
    sumo_home = os.environ.get("SUMO_HOME", "")
    if sumo_home:
        ruta = os.path.join(sumo_home, "tools", "randomTrips.py")
        if os.path.isfile(ruta):
            return ruta
    # Fallback: asumir que está accesible directamente
    return "randomTrips.py"


def ejecutar_pipeline_sumo(osm_path: str, output_dir: str = "output",
                           num_vehiculos: int = 20,
                           periodo_salida: float = 1.0) -> list[dict]:
    """
    Ejecuta el pipeline completo de SUMO de forma secuencial.
    
    Parámetros:
        osm_path: Ruta al archivo .osm descargado.
        output_dir: Directorio donde se generarán los archivos de salida.
        num_vehiculos: Número de vehículos a generar en las rutas aleatorias.
                      Cada vehículo se crea con una ruta aleatoria origen→destino.
        periodo_salida: Intervalo en segundos entre la salida de cada vehículo.
                       Con periodo=1.0 y num_vehiculos=20, los vehículos salen
                       en t=0, t=1, t=2, ..., t=19. Con periodo=2.0, salen en
                       t=0, t=2, t=4, ..., t=38.
    
    Retorna:
        Lista de diccionarios con el resultado de cada paso:
        [{"paso": str, "exito": bool, "mensaje": str,
          "segundos": float}, ...]   # "segundos" solo en los pasos con exito
    """
    resultados = []

    # Tiempo máximo por herramienta (None = sin límite). Ver SUMO_TIMEOUT_S.
    lim = _timeout()

    net_path = os.path.join(output_dir, "mapa.net.xml")
    poly_path = os.path.join(output_dir, "mapa.poly.xml")
    rou_path = os.path.join(output_dir, "mapa.rou.xml")
    
    # ---- Paso 1: NETCONVERT ----
    # ---- FILTRO DE VIAS ----
    # La consulta a Overpass pide `highway=*`, que en OSM incluye aceras, sendas,
    # escaleras y ciclovias. Un coche no pisa nada de eso, pero filtrarlo NO es
    # gratis: las junctions de la red son las candidatas a RSU, asi que quitar
    # vias quita candidatas. Medido sobre un area de Quito (map.osm de 57 MB):
    #
    #                                red      junctions    netconvert
    #   sin filtro                522,4 MB      89 877         56,6 s
    #   peatonal puro (ESTE)      463,5 MB      75 646         48,3 s   -15,8 %
    #   peatonal + ciclovias      459,2 MB      74 982         47,6 s   -16,6 %
    #   vclass pedestrian,bicycle 458,7 MB      74 877         47,8 s   -16,7 %
    #   keep passenger            366,8 MB      55 354            -     -40 %  (!)
    #
    # NO EXISTE UN INTERMEDIO REAL: el escalon entero ocurre al quitar las
    # aceras (`highway.footway` son 38 189 aristas, el 90 % de lo peatonal), asi
    # que las tres primeras variantes valen practicamente lo mismo. Se elige la
    # mas suave y la mas facil de justificar: se excluye por TIPO lo que es
    # inequivocamente peatonal, y se conservan ciclovias y caminos de tierra
    # (`track`), por los que si puede circular un vehiculo.
    #
    # `--keep-edges.by-vclass passenger` NO se debe usar: SUMO asigna por defecto
    # a `highway.service` un vclass que no incluye `passenger`, asi que borra
    # 33 934 aristas de callejones y accesos -calles reales- y el 40 % de las
    # candidatas. Se llego a activar y hubo que revertirlo.
    #
    # Ojo: las perdidas se propagan. `residential` baja de 122 308 a 110 614
    # aristas incluso con este filtro suave, no porque se borren calles sino
    # porque al quitar las aceras algunos tramos quedan aislados y los poda
    # despues `--remove-edges.isolated`.
    #
    # Vacio ("") desactiva el filtro y deja la red completa.
    FILTRO_VIAS_POR_DEFECTO = ("highway.footway,highway.steps,highway.path,"
                               "highway.pedestrian,highway.bridleway")
    filtro_vias = os.environ.get("SUMO_FILTRO_VIAS", FILTRO_VIAS_POR_DEFECTO).strip()

    cmd_netconvert = [
        "netconvert",
        "--ramps.guess",
        "--remove-edges.isolated",
        "--edges.join",
        "--geometry.remove",
        "--osm-files", osm_path,
        "-o", net_path
    ]
    if filtro_vias:
        cmd_netconvert[-4:-4] = ["--remove-edges.by-type", filtro_vias]

    _t0 = time.perf_counter()
    try:
        resultado = correr(cmd_netconvert, timeout=lim, etiqueta="netconvert")
        resultados.append({
            "paso": "netconvert",
            "exito": True,
            "segundos": time.perf_counter() - _t0,
            "mensaje": f"Red vial generada: {net_path}",
            "archivo": net_path
        })
    except FileNotFoundError:
        resultados.append({
            "paso": "netconvert",
            "exito": False,
            "mensaje": "No se encontró 'netconvert'. ¿Está SUMO instalado y en el PATH del sistema?"
        })
        return resultados  # No tiene sentido continuar
    except subprocess.CalledProcessError as e:
        resultados.append({
            "paso": "netconvert",
            "exito": False,
            "mensaje": f"Error en netconvert:\n{e.stderr[:500]}"
        })
        return resultados
    except subprocess.TimeoutExpired:
        resultados.append({
            "paso": "netconvert",
            "exito": False,
            "mensaje": _msg_timeout("netconvert", lim)
        })
        return resultados

    # ---- Paso 2: POLYCONVERT ----
    cmd_polyconvert = [
        "polyconvert",
        "--net-file", net_path,
        "--osm-files", osm_path,
        "-o", poly_path
    ]
    
    _t0 = time.perf_counter()
    try:
        correr(cmd_polyconvert, timeout=lim, etiqueta="polyconvert")
        resultados.append({
            "paso": "polyconvert",
            "exito": True,
            "segundos": time.perf_counter() - _t0,
            "mensaje": f"Polígonos generados: {poly_path}",
            "archivo": poly_path
        })
    except FileNotFoundError:
        resultados.append({
            "paso": "polyconvert",
            "exito": False,
            "mensaje": "No se encontró 'polyconvert'. ¿Está SUMO instalado y en el PATH del sistema?"
        })
        return resultados
    except subprocess.CalledProcessError as e:
        resultados.append({
            "paso": "polyconvert",
            "exito": False,
            "mensaje": f"Error en polyconvert:\n{e.stderr[:500]}"
        })
        return resultados
    except subprocess.TimeoutExpired:
        resultados.append({
            "paso": "polyconvert",
            "exito": False,
            "mensaje": _msg_timeout("polyconvert", lim)
        })
        return resultados

    # ---- Paso 3: RANDOM TRIPS ----
    random_trips_path = _buscar_random_trips()

    # Calcular el tiempo final de generación de vehículos:
    # Si queremos 20 vehículos con periodo 1.0s, el último vehículo sale en t=19
    # Fórmula: end_time = num_vehiculos * periodo_salida
    end_time = num_vehiculos * periodo_salida

    # El umbral decide si repartir compensa para ESTE numero de vehiculos, y el
    # tamano de la red cuanta memoria costaria cada hilo.
    try:
        red_mb = os.path.getsize(net_path) / 1e6
    except OSError:
        red_mb = None
    hilos = _hilos(num_vehiculos, red_mb)
    cmd_random_trips = [
        sys.executable, random_trips_path,
        "-n", net_path,
        "-r", rou_path,
        "-e", str(end_time),
        "-p", str(periodo_salida),
        # Ver `_hilos()`: sin esto duarouter usa un solo nucleo y dijkstra.
        "--duarouter-routing-threads", str(hilos),
        # CH = jerarquias de contraccion. Dijkstra y A* buscan el camino en cada
        # consulta; CH PREPROCESA la red una vez y luego responde cada camino
        # minimo casi gratis. Es el caso para el que se invento: decenas de miles
        # de consultas sobre un grafo fijo. Y es EXACTO, como A*: mismos caminos
        # minimos que dijkstra, no una aproximacion.
        #
        # Medido sobre una red real de 442 MB con 16 hilos, comprobando que las
        # rutas escritas coinciden exactamente:
        #
        #     viajes    astar      CH
        #        500    93,5 s    90,0 s
        #      2 000   115,8 s    98,3 s
        #     10 000   198,1 s   101,4 s    <- 1,95x
        #
        # Ajustando T(n) = fijo + n * coste_por_viaje:
        #     astar -> 95,2 s fijos + 0,0103 s por viaje
        #     CH    -> 97,5 s fijos + 0,00039 s por viaje   (26x mas barato)
        # El preproceso cuesta ~2 s y a partir de ahi cada ruta es casi gratis.
        # Extrapolado a 50 000 viajes: 610 s -> 117 s (5,2x).
        #
        # CH gana en TODOS los tamanos medidos, asi que no hace falta un umbral
        # como el de los hilos. Los ~95 s fijos son cargar la red, no el
        # algoritmo.
        "--duarouter-routing-algorithm",
        os.environ.get("SUMO_ALGORITMO_RUTA", "CH"),
        # randomTrips trae `validate=True` por defecto, y eso ejecuta duarouter
        # DOS VECES sobre los mismos viajes: una para producir las rutas y otra
        # con `--write-trips` para comprobar cuales son validas. Es rutar todo
        # dos veces. Confirmado viendo ambos procesos vivos a la vez:
        #   [29840] RUTADO (-o rou)             3 081 MB
        #   [16496] VALIDACION (--write-trips)  1 904 MB
        #
        # Lo que aporta validar es garantizar EXACTAMENTE el numero de viajes
        # pedido: descarta los irrutables y, si fallan muchos, genera mas. Sin
        # ella, duarouter con `--ignore-errors` simplemente omite los que no
        # puede rutar y salen algunos vehiculos menos de los pedidos.
        #
        # Para este proyecto no importa: el trafico es aleatorio y la cobertura
        # se mide como PORCENTAJE de pares (instante, vehiculo), asi que da igual
        # que sean 49 800 en vez de 50 000. Lo que si se hace es contar los que
        # salieron de verdad y decirlo, para que la cifra no se de por supuesta.
        "--no-validate",
    ]
    
    _t0 = time.perf_counter()
    try:
        correr(cmd_random_trips, timeout=lim, etiqueta="randomTrips")
        resultados.append({
            "paso": "randomTrips",
            "exito": True,
            "segundos": time.perf_counter() - _t0,
            "mensaje": (
                f"Rutas generadas: {rou_path} "
                f"({_contar_vehiculos(rou_path)} de {num_vehiculos} vehículos, "
                f"periodo {periodo_salida}s, {hilos} hilos, A*)"
            ),
            "archivo": rou_path
        })
    except FileNotFoundError:
        resultados.append({
            "paso": "randomTrips",
            "exito": False,
            "mensaje": f"No se encontró randomTrips.py en: {random_trips_path}. Configura la variable SUMO_HOME."
        })
    except subprocess.CalledProcessError as e:
        resultados.append({
            "paso": "randomTrips",
            "exito": False,
            "mensaje": f"Error en randomTrips:\n{e.stderr[:500]}"
        })
    except subprocess.TimeoutExpired:
        resultados.append({
            "paso": "randomTrips",
            "exito": False,
            "mensaje": _msg_timeout("randomTrips", lim)
        })
    
    return resultados
