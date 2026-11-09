"""
determinismo.py — ¿se puede repetir un escenario?
==================================================
Comprueba que, fijada la semilla, el escenario es **reproducible**: los mismos
parámetros producen las mismas rutas y la misma traza de movilidad.

Es la base sobre la que se apoya todo lo demás —catálogo de corridas, caché por
hash, campañas por lotes y el suplemento del artículo—: si dos corridas iguales
no dan lo mismo, nada de eso tiene sentido.

Se comprueban tres cosas, **con el paralelismo activado**, que es como se
ejecuta de verdad:

    1. Misma semilla dos veces  →  rutas y traza IDÉNTICAS
    2. Semilla distinta         →  escenario DISTINTO (la semilla hace algo)
    3. 1 hilo frente a N hilos  →  el paralelismo NO altera el resultado

La tercera importa especialmente porque el proyecto usa `duarouter` con varios
hilos y jerarquías de contracción (CH), y `sumo --threads`. Convenía verificar
que nada de eso introduce variación entre corridas.

Uso (desde la raíz del repo):
    python pruebas/determinismo.py                 # usa output/map.osm
    python pruebas/determinismo.py --osm otro.osm
    python pruebas/determinismo.py --vehiculos 500 --duracion 1200
"""

import argparse
import hashlib
import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

# Sin el almacen de etapas: si la segunda corrida saliera de el, la prueba
# compararia un archivo consigo mismo y no demostraria nada.
os.environ["SCN_CACHE"] = "0"

from backend.sumo_pipeline import ejecutar_pipeline_sumo          # noqa: E402
from backend.simulacion_sumo import ejecutar_simulacion_sumo      # noqa: E402


def huella(ruta: str) -> str:
    """
    Hash del CONTENIDO de un XML de SUMO, ignorando las cabeceras.

    No sirve comparar los archivos byte a byte: SUMO escribe en la cabecera la
    marca de tiempo de generación y un bloque `<configuration>` con las RUTAS
    de los archivos. Las dos cosas cambian entre corridas hechas en carpetas
    distintas sin que el escenario sea distinto.

    Aquí se descarta ese bloque (los comentarios los descarta ya ElementTree) y
    se serializa el resto: quedan los `<vehicle>`/`<route>` del `.rou.xml` y los
    `<timestep>` del FCD, que es lo que de verdad define el escenario.
    """
    raiz = ET.parse(ruta).getroot()
    for hijo in list(raiz):
        if hijo.tag == "configuration":
            raiz.remove(hijo)
    return hashlib.sha256(ET.tostring(raiz)).hexdigest()[:16]


def una_corrida(base: str, etiqueta: str, osm: str, semilla: int,
                vehiculos: int, duracion: float, muestreo: float,
                hilos: int | None = None) -> tuple:
    """
    Genera rutas y simula una vez. Devuelve (huella_rutas, huella_traza), o
    (None, None) si algún paso falló.
    """
    carpeta = os.path.join(base, etiqueta)
    shutil.rmtree(carpeta, ignore_errors=True)
    os.makedirs(carpeta)

    anterior = os.environ.get("SUMO_HILOS")
    if hilos is not None:
        os.environ["SUMO_HILOS"] = str(hilos)
    try:
        pasos = ejecutar_pipeline_sumo(osm, carpeta, num_vehiculos=vehiculos,
                                       periodo_salida=duracion / vehiculos,
                                       semilla=semilla)
        fallidos = [p for p in pasos if not p["exito"]]
        if fallidos:
            print("   FALLO en %s: %s" % (fallidos[0]["paso"],
                                          fallidos[0]["mensaje"][:160]))
            return None, None
        fcd, err = ejecutar_simulacion_sumo(carpeta, duracion,
                                            periodo_fcd=muestreo,
                                            semilla=semilla)
        if err:
            print("   FALLO en sumo: %s" % err[:160])
            return None, None
    finally:
        if hilos is not None:
            if anterior is None:
                os.environ.pop("SUMO_HILOS", None)
            else:
                os.environ["SUMO_HILOS"] = anterior

    return huella(os.path.join(carpeta, "mapa.rou.xml")), huella(fcd)


def main() -> int:
    ap = argparse.ArgumentParser(description="Comprueba que el escenario es reproducible")
    ap.add_argument("--osm", default=os.path.join(RAIZ, "output", "map.osm"),
                    help="archivo .osm de entrada")
    ap.add_argument("--vehiculos", type=int, default=200)
    ap.add_argument("--duracion", type=float, default=600.0, help="segundos simulados")
    ap.add_argument("--muestreo", type=float, default=120.0, help="segundos entre snapshots")
    args = ap.parse_args()

    if not os.path.exists(args.osm):
        print("No existe %s.\nGenera un escenario desde la aplicación, o pasa"
              " otro archivo con --osm." % args.osm)
        return 2

    # Ruta de trabajo SIN doble guion: `randomTrips` escribe su línea de
    # comandos dentro de un comentario XML, y `--` es ilegal ahí. Un directorio
    # con `--` hace que duarouter falle con un error poco evidente.
    base = tempfile.mkdtemp(prefix="determinismo_")
    assert "--" not in base, "la carpeta temporal no puede contener '--'"

    print("mapa      : %s (%.1f MB)" % (os.path.basename(args.osm),
                                        os.path.getsize(args.osm) / 1e6))
    print("escenario : %d vehiculos · %.0f s · muestreo %.0f s · %d nucleos\n"
          % (args.vehiculos, args.duracion, args.muestreo, os.cpu_count() or 1))

    casos = (("semilla 42 (a)", 42, None),
             ("semilla 42 (b)", 42, None),
             ("semilla 7", 7, None),
             ("semilla 42, 1 hilo", 42, 1))

    print("=" * 66)
    print("  %-22s %-18s %-18s" % ("corrida", "rutas", "traza (FCD)"))
    print("=" * 66)
    res = {}
    try:
        for etiqueta, semilla, hilos in casos:
            slug = "".join(c if c.isalnum() else "_" for c in etiqueta)
            res[etiqueta] = una_corrida(base, slug, args.osm, semilla,
                                        args.vehiculos, args.duracion,
                                        args.muestreo, hilos)
            print("  %-22s %-18s %-18s" % (etiqueta, res[etiqueta][0], res[etiqueta][1]))
            sys.stdout.flush()
    finally:
        shutil.rmtree(base, ignore_errors=True)

    a, b = res["semilla 42 (a)"], res["semilla 42 (b)"]
    c, d = res["semilla 7"], res["semilla 42, 1 hilo"]
    if a[0] is None:
        print("\nNo se pudo completar la comprobación.")
        return 2

    ok1, ok2, ok3 = (a == b), (c != a), (d == a)
    print()
    print("=" * 66)
    print("  VEREDICTO")
    print("=" * 66)
    print("  1. misma semilla -> mismo escenario   :", ok1)
    print("  2. otra semilla  -> otro escenario    :", ok2)
    print("  3. los hilos no alteran el resultado  :", ok3)
    if not ok3 and d[0] is not None:
        print("     rutas iguales: %s | traza igual: %s" % (d[0] == a[0], d[1] == a[1]))
    print()
    if ok1 and ok2 and ok3:
        print("  REPRODUCIBLE")
        return 0
    print("  NO reproducible: revisar antes de lanzar campañas")
    return 1


if __name__ == "__main__":
    sys.exit(main())
