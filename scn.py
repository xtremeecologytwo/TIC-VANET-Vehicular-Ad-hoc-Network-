"""
scn.py — línea de comandos para campañas de simulación
=======================================================
Permite lanzar corridas sin pasar por la interfaz web, que es lo que hacía
inviables las pruebas por lotes: cada corrida obligaba a repetir los clics, y
no quedaba registro de con qué parámetros se hizo.

Cada corrida:
  * se ejecuta en **su propia carpeta**, así no se pisan entre ellas;
  * queda anotada en el **catálogo** (`datos/catalogo.sqlite`) con sus
    parámetros, su semilla, sus métricas y el entorno que la produjo;
  * deja un `manifest.json` en su carpeta, de modo que el catálogo se pueda
    reconstruir releyendo el disco.

Órdenes:
    python scn.py mapa      --nombre NOMBRE          elegir un área en el navegador
    python scn.py areas                              áreas guardadas
    python scn.py correr    --area NOMBRE [opciones] una corrida
    python scn.py campana   ARCHIVO.yaml [--plan]    un lote (experimento factorial)
    python scn.py listar    [--campana NOMBRE]
    python scn.py estado
    python scn.py exportar  --campana NOMBRE          CSV (Power BI / Excel)
    python scn.py reporte   --campana NOMBRE          figuras + tabla LaTeX
    python scn.py powerbi   [--abrir]                 proyecto de Power BI con las campañas
    python scn.py extracto                           mapa de Ecuador sin internet

Ejemplos:
    python scn.py mapa --nombre centro
    python scn.py correr --area centro --vehiculos 1000 --fisica 6:r90 --optimizar
    python scn.py campana campanas/fisica_v1.yaml --plan
    python scn.py campana campanas/fisica_v1.yaml
    python scn.py reporte --campana fisica_v1
"""

import argparse
import os
import sys
import time
from contextlib import contextmanager

RAIZ = os.path.dirname(os.path.abspath(__file__))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "optimizacion"))

from backend import flujo, almacen, descargar_osm             # noqa: E402
from backend import areas as areas_mod, campana as campana_mod  # noqa: E402
from backend.catalogo import Catalogo                         # noqa: E402
from backend.sumo_pipeline import SEMILLA_POR_DEFECTO          # noqa: E402

DATOS = os.path.join(RAIZ, "datos")


# ----------------------------------------------------------------------
# Registro de progreso: imprime y CRONOMETRA
# ----------------------------------------------------------------------

class RegistroCLI:
    """
    Muestra el avance por consola y guarda cuánto tardó cada sub-etapa.

    Cumple el mismo contrato que espera `backend.flujo` (etapa / subetapa /
    nota), de modo que el núcleo no distingue si lo llama el CLI o la API.
    """

    def __init__(self, silencioso: bool = False):
        self.tiempos: dict[str, float] = {}
        self.silencioso = silencioso

    @contextmanager
    def etapa(self, nombre: str):
        if not self.silencioso:
            print(f"\n  {nombre}")
        t0 = time.perf_counter()
        medida = type("M", (), {"segundos": 0.0})()
        try:
            yield medida
        finally:
            medida.segundos = time.perf_counter() - t0
            self.tiempos[nombre] = medida.segundos

    @contextmanager
    def subetapa(self, nombre: str):
        t0 = time.perf_counter()
        medida = type("M", (), {"segundos": 0.0})()
        try:
            yield medida
        finally:
            medida.segundos = time.perf_counter() - t0
            self.tiempos[nombre] = medida.segundos
            if not self.silencioso:
                print(f"     {nombre:.<46} {medida.segundos:8.2f} s")

    def nota(self, texto: str) -> None:
        if not self.silencioso:
            print(f"       · {texto}")


# ----------------------------------------------------------------------
# correr
# ----------------------------------------------------------------------

def _bbox_de(args):
    """bbox desde --area (nombre guardado) o --bbox (coordenadas)."""
    if getattr(args, "area", None):
        return tuple(areas_mod.obtener(args.area)), args.area
    if not args.bbox:
        raise ValueError("indica --area NOMBRE (crea una con `scn.py mapa`) o --bbox")
    bbox = tuple(float(x) for x in args.bbox.split(","))
    if len(bbox) != 4:
        raise ValueError("--bbox debe ser min_lon,min_lat,max_lon,max_lat")
    return bbox, args.nombre_area


def cmd_correr(args) -> int:
    try:
        bbox, nombre_area = _bbox_de(args)
        if args.fisica:
            fisica = campana_mod.fisica_de(args.fisica, campana_mod.FISICA_BASE, args.H)
        else:
            # Sin --fisica: radio a mano y el resto clásico (P = 1..H, Cap 300, L 10)
            fisica = {**campana_mod.fisica_de("clasica", {}, args.H), "radio_m": float(args.radio)}
    except (KeyError, ValueError, campana_mod.ErrorCampana) as e:
        print(f"  {e}")
        return 2
    if args.vehiculos > campana_mod.MAX_VEHICULOS:
        print(f"  --vehiculos {args.vehiculos} supera el máximo de {campana_mod.MAX_VEHICULOS}")
        return 2
    semilla = SEMILLA_POR_DEFECTO if args.semilla is None else args.semilla
    if args.sin_cache:
        os.environ["SCN_CACHE"] = "0"
    if args.campana:
        cat = Catalogo(os.path.join(DATOS, "catalogo.sqlite"))
        es_yaml = cat.spec_campana(args.campana) is not None
        cat.cerrar()
        if es_yaml:
            print(f"  '{args.campana}' es una campaña definida por YAML: una corrida suelta en ella"
                  " descuadraría su reporte. Usa otro --campana.")
            return 2
    filtrado = f"g{args.gmin}r{args.rho:g}"
    punto = campana_mod.clave_punto(args.vehiculos, filtrado, fisica["nivel"], args.H)

    print(f"corrida: {punto}")
    print(f"  area      : {nombre_area or '-'} {bbox}")
    print(f"  demanda   : {args.vehiculos} vehiculos · {args.duracion} min · semilla {semilla}")
    print(f"  filtrado  : grado>={args.gmin} · rho={args.rho:g} m")
    print(f"  fisica    : {fisica['nivel']} -> radio {fisica['radio_m']:g} m, "
          f"P[h] = {fisica['P'] or '1..H'}, Cap = {fisica['cap_kbps'] or 300:g}")
    print(f"  H={args.H} · muestreo {args.paso} min"
          + (f" · M3 con tope {args.tope_m3:g} s" if args.optimizar else " · sin M3"))

    cat = Catalogo(os.path.join(DATOS, "catalogo.sqlite"))
    reg = RegistroCLI(silencioso=args.silencioso)
    try:
        r = campana_mod.ejecutar_punto(
            cat, bbox=bbox, nombre_area=nombre_area, vehiculos=args.vehiculos,
            duracion_min=args.duracion, semilla=semilla, gmin=args.gmin, rho=args.rho,
            fisica=fisica, H=args.H, muestreo_min=args.paso, campana=args.campana,
            punto=punto, filtrado=filtrado, optimizar=args.optimizar,
            tope_m3_s=args.tope_m3, registro=reg)
    except flujo.ErrorFlujo as e:
        print(f"\n  FALLO en {e.etapa}: {e}")
        return 1
    finally:
        cat.cerrar()

    m = r["metricas"]
    print("\n  RESULTADO")
    print(f"     candidatas Y ...... {r['Y']}")
    if r["Y"] == 0:
        print(f"     AVISO: ninguna junction llega a grado {args.gmin}; el area se queda"
              " sin RSU y todo el trafico sin servicio. Baja --gmin.")
    print(f"     instantes ......... {m['n_instantes']}")
    print(f"     N (veh-instante) .. {m['N']}")
    print(f"     K (pares reales) .. {m['K']}   M1={m['m1']} M2={m['m2']} M3={m['m3']}")
    print(f"     |CVR| ............. {m['cvr']}")
    print(f"     Q_reach ........... {m['q_reach']:.2f} %")
    d = r["despliegue"]
    if d:
        estado = "óptimo demostrado" if d["optimo"] else (
            "CORTADO por tiempo: mejor solución hallada" if d["cortado"] else d["status"])
        print(f"     RSU desplegadas ... {d['n_rsu']}")
        if d["cobertura_pct"] is not None:
            print(f"     cobertura ......... {d['cobertura_pct']:.2f} %")
        print(f"     solver ............ {d['segundos_solver'] or 0:.1f} s, {estado}")
    print(f"\n  guardada como {r['uuid']} en {r['carpeta']}")
    return 0


# ----------------------------------------------------------------------
# mapa / areas
# ----------------------------------------------------------------------

def cmd_mapa(args) -> int:
    area = areas_mod.seleccionar_en_mapa(args.nombre, abrir=not args.no_abrir)
    if not area:
        return 1
    w, s_, e, n = area["bbox"]
    print(f"  guardada '{area['nombre']}': {w},{s_},{e},{n}  ({area['km2']:.2f} km²)")
    print(f"  úsala con:  scn.py correr --area {area['nombre']} ...   o   area: {area['nombre']}  en un YAML")
    return 0


def cmd_areas(args) -> int:
    if args.agregar:
        try:
            a = areas_mod.guardar(args.agregar, [float(x) for x in args.bbox.split(",")])
        except (AttributeError, ValueError) as e:
            print(f"  {e} (usa --agregar NOMBRE --bbox=min_lon,min_lat,max_lon,max_lat)")
            return 2
        print(f"  guardada '{args.agregar}' ({a['km2']:.2f} km²)")
        return 0
    todas = areas_mod.listar()
    if not todas:
        print("  no hay áreas guardadas: crea una con `scn.py mapa --nombre NOMBRE`")
        return 0
    for nombre, a in todas.items():
        w, s_, e, n = a["bbox"]
        print(f"  {nombre:<20} {a['km2']:6.2f} km²   --bbox={w},{s_},{e},{n}   ({a['creada'][:10]})")
    return 0


# ----------------------------------------------------------------------
# campana / exportar / reporte
# ----------------------------------------------------------------------

def _cabecera_campana(spec) -> None:
    """Lo que define una campaña (o una familia de semillas): factores, física y topes."""
    fac = spec["factores"]
    semillas = (f"semillas {', '.join(map(str, spec['semillas']))}" if "semillas" in spec
                else f"semilla {spec['semilla']}")
    print(f"campaña: {spec['nombre']}  —  {spec.get('descripcion', '').strip()[:90]}")
    print(f"  área {spec['area']} · {semillas} · {spec['duracion_min']} min, "
          f"muestreo {spec['muestreo_min']} min · tope M3 {float(spec['tope_m3_s']):g} s")
    for k in ("vehiculos", "fisica", "H", "filtrado", "carga", "presupuesto"):
        if k in fac:
            print(f"  {k:<11} {fac[k]}")
    if "carga" in fac:
        base = float(spec["fisica_base"]["carga_kbps"])
        print(f"    carga por vehículo: {', '.join(f'{base * m:g}' for m in fac['carga'])} kb/s")
    for nivel in fac.get("presupuesto", []):
        if nivel != campana_mod.LIBRE:
            print(f"    {nivel}: MaxR = " + ", ".join(
                f"{campana_mod.max_rsu_de(spec, nivel, v)} con {v} veh" for v in fac["vehiculos"]))
    topes_l = campana_mod.topes_de(spec, None)
    print(f"  tope por nivel: {' / '.join(f'{t:g}' for t in topes_l)} s"
          + (f"  (con MaxR: {' / '.join(f'{t:g}' for t in campana_mod.topes_de(spec, 1))} s)"
             if "presupuesto" in fac else ""))


def _mantener_despierto() -> None:
    """
    Que Windows no entre en espera mientras corre la campaña: la inactividad
    cuenta solo el teclado y el ratón, no el trabajo de CPLEX, y una campaña
    dura días. En esta laptop (espera moderna) no basta con pedir que el
    sistema siga activo: al apagarse la pantalla por inactividad entra en
    espera igual (67 h en la tanda del 30-oct al 3-nov, y la última vez no
    despertó). Por eso también se pide la pantalla encendida; conviene bajar
    el brillo. Al terminar el proceso (bien, con error o con Ctrl+C) Windows
    vuelve a su configuración.
    """
    if sys.platform == "win32":
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x00000001, 0x00000002
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED
                                                       | ES_DISPLAY_REQUIRED)


def _sin_modo_seleccion() -> None:
    """
    Desactiva el "modo de edición rápida" de la consola de Windows. Con él, un
    clic dentro de la ventana la pone en modo selección ("Seleccionar ..." en el
    título) y el programa se congela en cuanto intenta escribir, hasta pulsar
    Esc: la noche del 30-oct una campaña quedó así 8 h. Copiar texto sigue
    siendo posible con el menú de la ventana (Editar > Marcar).
    """
    if sys.platform == "win32":
        import ctypes
        k32 = ctypes.windll.kernel32
        entrada = k32.GetStdHandle(-10)                    # STD_INPUT_HANDLE
        modo = ctypes.c_uint32()
        if k32.GetConsoleMode(entrada, ctypes.byref(modo)):
            ENABLE_QUICK_EDIT_MODE, ENABLE_EXTENDED_FLAGS = 0x0040, 0x0080
            k32.SetConsoleMode(entrada, (modo.value & ~ENABLE_QUICK_EDIT_MODE) | ENABLE_EXTENDED_FLAGS)


def cmd_campana(args) -> int:
    familias = []                      # (archivo, spec, bbox) de cada YAML, en el orden dado
    try:
        for archivo in args.archivos:
            spec = campana_mod.cargar_spec(archivo)
            familias.append((archivo, spec, areas_mod.obtener(spec["area"])))
    except (OSError, KeyError, campana_mod.ErrorCampana) as e:
        print(f"  {e}")
        return 2
    try:
        paralelo = (campana_mod.procesos_auto() if args.paralelo == "auto"
                    else max(1, int(args.paralelo)))
    except ValueError:
        print(f"  --paralelo {args.paralelo}: se espera un número o 'auto'")
        return 2
    unidades = campana_mod.orden_por_semilla([s for _, s, _ in familias], args.semilla)
    if not unidades:
        print(f"  ninguna de las campañas usa la semilla {args.semilla}")
        return 2

    # Plan de cada campaña y semilla; la huella se comprueba ANTES de ejecutar nada
    cat = Catalogo(os.path.join(DATOS, "catalogo.sqlite"))
    planes = []                        # (índice de la familia, spec de una semilla, plan)
    try:
        for i, una in unidades:
            for a in campana_mod.comprobar_huella(cat, una, familias[i][2]):
                print(f"  aviso ({una['nombre']}): {a}")
            planes.append((i, una, campana_mod.plan(una, cat, optimizar=not args.sin_m3)))
    except campana_mod.ErrorCampana as e:
        print(f"  {e}")
        return 2
    finally:
        cat.cerrar()

    for i, (_, spec, _) in enumerate(familias):
        if i:
            print()
        _cabecera_campana(spec)
        suyos = [(una, p) for j, una, p in planes if j == i]
        for una, p in suyos:
            if "familia" in una:
                print(f"  semilla {una['semilla']:>4} ({una['nombre']}): {p['n']} puntos, "
                      f"{p['hechos']} ya hechos, {len(p['pendientes'])} pendientes")
            else:
                print(f"  -> {p['n']} puntos: {p['hechos']} ya hechos, {len(p['pendientes'])} pendientes")
        p0 = suyos[0][1]
        print(f"  -> {'por semilla ' if 'semillas' in spec else ''}se simula M1 {p0['simulaciones_M1']} "
              f"veces y M2 {p0['simulaciones_M2']} veces; CVR + CPLEX en cada punto")
    print()
    if len(planes) > 1:
        print(f"en total: {len(planes)} tandas (campaña x semilla), "
              f"{sum(len(p['pendientes']) for _, _, p in planes)} puntos pendientes; "
              f"se ejecutan semilla a semilla")
    if not args.sin_m3:
        nucleos = os.cpu_count() or 1
        print(f"  -> {paralelo} optimización(es) a la vez"
              + (f", {max(1, nucleos // paralelo)} hilos cada una ({nucleos} núcleos lógicos)"
                 if paralelo > 1 else " (con todos los núcleos)"))

    if args.plan:
        for i, (_, spec, _) in enumerate(familias):
            p0 = next(p for j, _, p in planes if j == i)
            print(f"\n  configuración física de cada nivel en {spec['nombre']} (modelo del tutor):")
            vistos = set()
            for pt in p0["puntos"]:
                f = pt["fisica"]
                if f["nivel"] in vistos:
                    continue
                vistos.add(f["nivel"])
                print(f"    {f['nivel']:<8} radio {f['radio_m']:6g} m · Cap {f['cap_kbps'] or 300:7.0f} · "
                      f"L {f['carga_kbps'] or 10:g}{' (x carga)' if 'carga' in spec['factores'] else ''}"
                      f" · {f['fuente']}")
        if len(planes) == 1:            # con varias tandas la lista sería de miles de líneas
            orden = planes[0][2]["pendientes"]
            if paralelo > 1 and not args.sin_m3:
                orden = campana_mod.orden_pesados_primero(orden)
                print("\n  puntos pendientes (en paralelo, los más pesados primero):")
            else:
                print("\n  puntos pendientes:")
            for pt in orden[:args.solo or None]:
                print(f"    {pt['punto']}")
        return 0

    _mantener_despierto()
    _sin_modo_seleccion()
    codigo = 0
    for i, una, p in planes:
        if not p["pendientes"]:
            continue
        archivo, _, bbox = familias[i]
        if len(planes) > 1:
            print(f"\n=== {una['nombre']} ===")
        try:
            r = campana_mod.ejecutar(una, bbox=bbox, archivo=os.path.abspath(archivo),
                                     optimizar=not args.sin_m3, solo=args.solo, paralelo=paralelo,
                                     registro_factory=(lambda: RegistroCLI(silencioso=not args.detalle)))
        except campana_mod.ErrorCampana as e:
            print(f"  {e}")
            return 2
        if r["fallidos"]:
            codigo = 1
        if r.get("interrumpida"):
            return 1                    # Ctrl+C: no pasar a la siguiente semilla
    for _, spec, _ in familias:
        if "semillas" in spec:
            print(f"  reporte con todas las semillas: python scn.py reporte --campana {spec['nombre']} --semillas")
    return codigo


def cmd_exportar(args) -> int:
    from backend import reporte
    try:
        if args.semillas:
            rutas = reporte.exportar_semillas(args.campana, args.salida)
        else:
            rutas = (reporte.exportar(args.campana, args.salida),)
    except (ValueError, OSError) as e:
        print(f"  {e}")
        return 1
    for ruta in rutas:
        print(f"  {ruta}")
    print("  (formato de Excel en español: separador ';' y decimales con coma)")
    return 0


def cmd_powerbi(args) -> int:
    from backend import powerbi
    try:
        ruta = powerbi.generar(args.campana or None)
    except (ValueError, OSError) as e:
        print(f"  {e}")
        return 1
    print(f"  proyecto de Power BI: {ruta}")
    print("  al abrirlo, pulsa 'Actualizar ahora' para cargar los datos del CSV")
    if args.abrir:
        os.startfile(ruta)
    return 0


def cmd_reporte(args) -> int:
    from backend import reporte
    try:
        if args.semillas:
            csvs = reporte.exportar_semillas(args.campana)
            rutas = reporte.generar_semillas(args.campana)
            semillas = [s for _, s in reporte.campanas_familia(args.campana)]
            print(f"  {args.campana}: {len(semillas)} semillas ({', '.join(map(str, semillas))})")
            avisos = reporte.avisos_semillas(reporte.tabla_semillas(args.campana))
        else:
            csvs = (reporte.exportar(args.campana),)
            rutas = reporte.generar(args.campana)
            avisos = reporte.avisos_homogeneidad(reporte.tabla(args.campana))
        for aviso in avisos:
            print(f"  AVISO: {aviso}")
    except (ValueError, OSError) as e:
        print(f"  {e}")
        return 1
    for csv in csvs:
        print(f"  datos  : {csv}")
    for r in rutas:
        if not r.endswith(".png"):
            print(f"  figura : {r}")
    return 0


# ----------------------------------------------------------------------
# listar / estado
# ----------------------------------------------------------------------

def cmd_listar(args) -> int:
    cat = Catalogo(os.path.join(DATOS, "catalogo.sqlite"))
    filas = cat.corridas(args.campana)
    if not filas:
        print("no hay corridas registradas" +
              (f" en la campana '{args.campana}'" if args.campana else ""))
        cat.cerrar()
        return 0
    print("%-13s %-10s %-8s %5s %4s %6s %5s %6s %7s %8s"
          % ("uuid", "campana", "estado", "veh", "sem", "cand", "N", "K", "|CVR|", "Q_reach"))
    print("-" * 82)
    for f in filas:
        print("%-13s %-10s %-8s %5s %4s %6s %5s %6s %7s %7s"
              % (f["uuid"], (f["campana"] or "-")[:10], f["estado"],
                 f["n_vehiculos"], f["semilla"], f["candidatas"],
                 f["N"] if f["N"] is not None else "-",
                 f["K"] if f["K"] is not None else "-",
                 f["cvr"] if f["cvr"] is not None else "-",
                 f"{f['q_reach']:.2f}%" if f["q_reach"] is not None else "-"))
    cat.cerrar()
    return 0


def cmd_estado(args) -> int:
    ruta = os.path.join(DATOS, "catalogo.sqlite")
    if not os.path.exists(ruta):
        print("todavia no hay catalogo: lanza una corrida con `scn.py correr`")
        return 0
    cat = Catalogo(ruta)
    print("catalogo: %s (%.1f KB)" % (ruta, os.path.getsize(ruta) / 1024))
    for tabla, n in cat.resumen().items():
        print("   %-12s %5d" % (tabla, n))
    cat.cerrar()
    alm = almacen.resumen()
    if alm:
        print("almacen de etapas: %s" % almacen.dir_cache())
        for etapa, d in alm.items():
            print("   %-8s %4d entrada(s) %9.1f MB" % (etapa, d["entradas"], d["mb"]))
    return 0


# ----------------------------------------------------------------------
# extracto
# ----------------------------------------------------------------------

URL_EXTRACTO_POR_DEFECTO = "https://download.geofabrik.de/south-america/ecuador-latest.osm.pbf"


def cmd_extracto(args) -> int:
    """
    Descarga (o registra) un extracto de Geofabrik para recortar mapas sin red.

    Deja `datos/osm/<archivo>` y su `.meta.json` con el bbox que cubre y la
    fecha de los datos, que es lo que se cita luego en el manifest de cada
    corrida. Si el archivo ya existe no se vuelve a bajar.
    """
    import hashlib
    import urllib.request

    os.makedirs(descargar_osm.DIR_EXTRACTOS, exist_ok=True)
    herr = descargar_osm.herramientas_extracto()
    for nombre, ruta in herr.items():
        print(f"  {nombre:<11} {ruta or 'NO ENCONTRADO (ver herramientas/README.md)'}")
    if not all(herr.values()):
        return 2

    if args.listar:
        exts = descargar_osm.extractos()
        if not exts:
            print("  no hay extractos registrados en", descargar_osm.DIR_EXTRACTOS)
        for e in exts:
            w, s, e_, n = e["bbox"]
            print(f"  {e['archivo']:<30} datos del {str(e.get('fecha_datos'))[:10]}  "
                  f"bbox {w:.3f},{s:.3f},{e_:.3f},{n:.3f}  {e['bytes'] / 1e6:.0f} MB")
        return 0

    url = args.url
    nombre = os.path.basename(url)
    ruta = os.path.join(descargar_osm.DIR_EXTRACTOS, nombre)
    if os.path.isfile(ruta):
        print(f"  ya existe {ruta} ({os.path.getsize(ruta) / 1e6:.0f} MB); no se descarga")
    else:
        print(f"  descargando {url} ...")
        t0 = time.perf_counter()
        urllib.request.urlretrieve(url, ruta)
        print(f"  {os.path.getsize(ruta) / 1e6:.0f} MB en {time.perf_counter() - t0:.0f} s")

    md5 = None
    try:
        with urllib.request.urlopen(url + ".md5", timeout=60) as r:
            esperado = r.read().decode().split()[0]
        h = hashlib.md5()
        with open(ruta, "rb") as f:
            for trozo in iter(lambda: f.read(1 << 20), b""):
                h.update(trozo)
        md5 = h.hexdigest()
        print("  md5:", "coincide con Geofabrik" if md5 == esperado else f"NO COINCIDE ({md5} != {esperado})")
        if md5 != esperado:
            return 1
    except Exception as e:  # noqa: BLE001 - la comprobacion es opcional
        print(f"  md5: no se pudo comprobar ({type(e).__name__})")

    meta = descargar_osm.registrar_extracto(ruta, url=url, md5=md5)
    w, s, e_, n = meta["bbox"]
    print(f"  registrado: datos del {meta['fecha_datos']}, {meta['nodos']:,} nodos, "
          f"{meta['vias']:,} vias, bbox {w:.3f},{s:.3f},{e_:.3f},{n:.3f}")
    return 0


# ----------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Campañas de simulación VANET",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="orden", required=True)

    m = sub.add_parser("mapa", help="elegir un área en el navegador y guardarla con un nombre")
    m.add_argument("--nombre", required=True)
    m.add_argument("--no-abrir", action="store_true", help="no abrir el navegador (solo dar la URL)")
    m.set_defaults(func=cmd_mapa)

    a = sub.add_parser("areas", help="áreas guardadas (o --agregar una sin mapa)")
    a.add_argument("--agregar", metavar="NOMBRE", default=None)
    a.add_argument("--bbox", default=None)
    a.set_defaults(func=cmd_areas)

    c = sub.add_parser("correr", help="ejecuta una corrida y la registra")
    c.add_argument("--area", default=None, help="nombre de un área guardada (scn.py mapa)")
    c.add_argument("--bbox", default=None,
                   help="min_lon,min_lat,max_lon,max_lat (si no se usa --area)")
    c.add_argument("--nombre-area", default=None, help="nombre del area en el catalogo")
    c.add_argument("--vehiculos", type=int, default=100)
    c.add_argument("--duracion", type=int, default=10, help="minutos simulados")
    c.add_argument("--semilla", type=int, default=None)
    c.add_argument("--gmin", type=int, default=4, help="grado minimo de la junction")
    c.add_argument("--rho", type=float, default=20.0, help="radio de clustering (m)")
    c.add_argument("--radio", type=float, default=300.0, help="alcance V2V/V2I (m)")
    c.add_argument("--paso", type=int, default=2, help="muestreo en minutos")
    c.add_argument("--H", type=int, default=3, help="saltos maximos")
    c.add_argument("--campana", default=None)
    c.add_argument("--silencioso", action="store_true")
    c.add_argument("--sin-cache", action="store_true",
                   help="recalcula todas las etapas aunque ya esten en datos/cache")
    c.add_argument("--fisica", default=None,
                   help="TASA:CRITERIO (p. ej. 6:r90) o 'clasica': radio, P[h] y Cap del modelo del tutor")
    c.add_argument("--optimizar", action="store_true", help="resolver M3 y guardar el despliegue")
    c.add_argument("--tope-m3", type=float, default=campana_mod.TOPE_M3_S,
                   help="segundos totales de M3, repartidos por nivel (por defecto 5400 = 1 h 30)")
    c.set_defaults(func=cmd_correr)

    k = sub.add_parser("campana", help="ejecuta (o planifica) uno o varios lotes descritos en YAML")
    k.add_argument("archivos", nargs="+", metavar="archivo",
                   help="YAML de la campaña; con varios (o con `semillas`) se ejecuta semilla a semilla")
    k.add_argument("--plan", action="store_true", help="solo mostrar qué se haría")
    k.add_argument("--semilla", type=int, default=None,
                   help="de las campañas con `semillas`, ejecutar solo esta")
    k.add_argument("--solo", type=int, default=None,
                   help="ejecutar solo los N primeros pendientes (de cada campaña y semilla)")
    k.add_argument("--sin-m3", action="store_true", help="no optimizar (solo M1+M2+CVR)")
    k.add_argument("--detalle", action="store_true", help="mostrar el avance de cada etapa")
    k.add_argument("--paralelo", default="1", metavar="N|auto",
                   help="optimizaciones a la vez, cada una con núcleos/N hilos "
                        "('auto' = según núcleos y RAM libre; por defecto 1)")
    k.set_defaults(func=cmd_campana)

    ex = sub.add_parser("exportar", help="CSV de una campaña (Power BI / Excel)")
    ex.add_argument("--campana", required=True)
    ex.add_argument("--salida", default=None,
                    help="archivo .csv (con --semillas, la carpeta de los dos CSV)")
    ex.add_argument("--semillas", action="store_true",
                    help="--campana es una familia con `semillas`: todas sus corridas y el resumen por punto")
    ex.set_defaults(func=cmd_exportar)

    pb = sub.add_parser("powerbi", help="proyecto de Power BI (.pbip) con las campañas, listo para abrir")
    pb.add_argument("--campana", nargs="*", default=None,
                    help="campañas a incluir (por defecto las de la tesis con corridas hechas)")
    pb.add_argument("--abrir", action="store_true", help="abrirlo en Power BI Desktop al terminar")
    pb.set_defaults(func=cmd_powerbi)

    rp = sub.add_parser("reporte", help="figuras y tabla LaTeX de una campaña")
    rp.add_argument("--campana", required=True)
    rp.add_argument("--semillas", action="store_true",
                    help="--campana es una familia con `semillas`: medias e IC 95 % de todas sus semillas")
    rp.set_defaults(func=cmd_reporte)

    l = sub.add_parser("listar", help="muestra las corridas registradas")
    l.add_argument("--campana", default=None)
    l.set_defaults(func=cmd_listar)

    e = sub.add_parser("estado", help="resumen del catalogo")
    e.set_defaults(func=cmd_estado)

    x = sub.add_parser("extracto", help="descarga/registra un extracto de Geofabrik (mapas sin red)")
    x.add_argument("--url", default=URL_EXTRACTO_POR_DEFECTO,
                   help="archivo .osm.pbf de Geofabrik (por defecto, Ecuador)")
    x.add_argument("--listar", action="store_true", help="solo mostrar los registrados")
    x.set_defaults(func=cmd_extracto)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
