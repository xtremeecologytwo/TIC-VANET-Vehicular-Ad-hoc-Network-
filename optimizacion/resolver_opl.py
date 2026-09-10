"""
resolver_opl.py — Resuelve el modelo de RSU con `oplrun` (IBM OPL)
==================================================================
Camino ALTERNATIVO al de `optimizar_rsu.py`, que resuelve el mismo modelo con
`docplex` dentro de Python.

¿Para qué dos caminos?
----------------------
Para **validación cruzada**. Son dos implementaciones independientes de la misma
formulación (Urquiza-Aguiar et al., 2016): una en lenguaje OPL ejecutada por el
binario `oplrun`, otra construida en memoria con la librería `docplex`. Si ambas
dan el mismo despliegue y los mismos objetivos, el modelo está bien traducido.
Si difieren, una de las dos está mal — y más vale saberlo antes de defender los
números.

Este módulo devuelve un dict con **la misma forma** que `optimizar()`, así que es
intercambiable con él.

Requisitos
----------
- IBM ILOG CPLEX Optimization Studio instalado (trae `oplrun`).
- Se localiza solo en las rutas habituales de Windows; se puede forzar con la
  variable de entorno `OPLRUN`.

Uso rápido:
    python optimizacion/resolver_opl.py --micro
    python optimizacion/resolver_opl.py --dat optimizacion/rsu_backend.dat
"""

import glob
import os
import re
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

# Modelo lexicográfico de 3 niveles: el que replica lo que hace docplex hoy.
MODELO_LEX = os.path.join(AQUI, "rsu_model_lex.mod")
# Modelo original (suma ponderada, Ec. 1 tal cual).
MODELO_SUMA = os.path.join(AQUI, "rsu_model.mod")


def encontrar_oplrun() -> str | None:
    """
    Localiza el ejecutable `oplrun`.

    Orden: la variable de entorno `OPLRUN` (para instalaciones fuera de lo
    habitual) y luego las rutas típicas de CPLEX Studio en Windows. Se ordenan
    los candidatos al revés para preferir la versión más reciente.
    """
    env = os.environ.get("OPLRUN")
    if env and os.path.exists(env):
        return env

    patrones = [
        r"C:\Program Files\IBM\ILOG\CPLEX_Studio*\opl\bin\*\oplrun.exe",
        r"C:\Program Files (x86)\IBM\ILOG\CPLEX_Studio*\opl\bin\*\oplrun.exe",
    ]
    candidatos: list[str] = []
    for p in patrones:
        candidatos.extend(glob.glob(p))
    if candidatos:
        return sorted(candidatos)[-1]

    # Fuera de Windows, o si está en el PATH
    from shutil import which
    return which("oplrun")


def _leer_salida(texto: str) -> dict:
    """
    Extrae los pares CLAVE=valor que imprime el bloque `execute` del .mod.

    Se parsea así —y no el log de CPLEX— porque el formato del log cambia entre
    versiones de OPL, mientras que estas líneas las controlamos nosotros.
    """
    datos: dict[str, str] = {}
    for linea in texto.splitlines():
        m = re.match(r"^([A-Z_]+)=(.*)$", linea.strip())
        if m:
            datos[m.group(1)] = m.group(2).strip()
    return datos


def _num(datos: dict, clave: str, por_defecto=None):
    """Convierte un valor de la salida a float. OPL puede usar coma decimal."""
    v = datos.get(clave)
    if v is None or v == "":
        return por_defecto
    try:
        return float(v.replace(",", "."))
    except ValueError:
        return por_defecto


def resolver(dat_path: str, modelo: str = MODELO_LEX,
             limite_tiempo: float | None = None,
             mostrar_log: bool = False) -> dict:
    """
    Resuelve un `.dat` con `oplrun` y devuelve el resultado.

    Parámetros:
        dat_path: archivo de datos OPL (lo genera backend/exportar_dat.py).
        modelo: ruta al .mod. Por defecto el lexicográfico de 3 niveles, que es
                el que replica la ruta de docplex.
        limite_tiempo: segundos máximos para el proceso completo (None = sin
                límite). Es un tope del PROCESO, no del solver: oplrun no expone
                el límite de CPLEX por línea de comandos.
        mostrar_log: imprime la salida cruda de oplrun.

    Retorna:
        dict con la misma forma que `optimizar_rsu.optimizar()`:
          "objetivo", "objetivos", "seleccionados", "seleccionados_backend",
          "status", "n_rsu_elegidos", "segundos_solver", "reparto".
    """
    oplrun = encontrar_oplrun()
    if not oplrun:
        raise FileNotFoundError(
            "No se encontró 'oplrun'. Viene con IBM ILOG CPLEX Optimization "
            "Studio. Si está instalado en una ruta no habitual, indícala con la "
            "variable de entorno OPLRUN."
        )
    for f in (modelo, dat_path):
        if not os.path.exists(f):
            raise FileNotFoundError(f"No existe: {f}")

    t0 = time.perf_counter()
    proc = subprocess.run([oplrun, modelo, dat_path],
                          capture_output=True, text=True,
                          timeout=limite_tiempo)
    segundos = time.perf_counter() - t0
    salida = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if mostrar_log:
        print(salida)

    datos = _leer_salida(salida)

    if "SELECTED" not in datos:
        # Sin la línea de salida no hubo solución: puede ser infactible, un
        # error de sintaxis del .dat, o que oplrun muriera.
        cola = "\n".join(salida.strip().splitlines()[-12:])
        return {
            "objetivo": None,
            "objetivos": None,
            "seleccionados": [],
            "seleccionados_backend": [],
            "status": f"oplrun no devolvió solución (rc={proc.returncode})",
            "n_rsu_elegidos": 0,
            "segundos_solver": segundos,
            "reparto": None,
            "salida_cruda": cola,
        }

    seleccionados = [int(x) for x in datos["SELECTED"].split(",") if x.strip()]

    n_pares = _num(datos, "N_PARES", 0) or 0
    desconectados = _num(datos, "DESCONECTADOS", 0.0) or 0.0
    conectados = n_pares - desconectados
    reparto = {
        "n_pares": int(n_pares),
        "conectados": conectados,
        "desconectados": desconectados,
        "cobertura_pct": (100.0 * conectados / n_pares) if n_pares else 0.0,
        "directos": _num(datos, "DIRECTOS", 0.0),
        "multisalto": _num(datos, "MULTISALTO", 0.0),
    }

    objetivos = None
    if "OBJ_DESCONEXION" in datos:
        objetivos = [_num(datos, "OBJ_DESCONEXION"),
                     _num(datos, "OBJ_INSTALACION"),
                     _num(datos, "OBJ_TRAFICO")]

    # 301 = CPX_STAT_MULTIOBJ_OPTIMAL; 101/102 = optimo entero (suma ponderada)
    codigo = datos.get("ESTADO", "?")
    nombres = {"301": "multi-objective optimal",
               "101": "integer optimal solution",
               "102": "integer optimal, tolerance"}
    status = nombres.get(codigo, f"cplex status {codigo}")

    return {
        "objetivo": _num(datos, "OBJETIVO"),
        "objetivos": objetivos,
        "seleccionados": seleccionados,
        "seleccionados_backend": seleccionados,   # el .dat ya usa ids OPL
        "status": status,
        "n_rsu_elegidos": int(_num(datos, "N_RSU", len(seleccionados))),
        "segundos_solver": segundos,
        "reparto": reparto,
    }


def resolver_datos(datos: dict, dat_path: str | None = None, **kw) -> dict:
    """
    Igual que `resolver()` pero partiendo del dict de datos en memoria: escribe
    el `.dat` y lo resuelve. Así se puede alimentar exactamente los MISMOS datos
    a los dos motores, que es lo que hace válida la comparación.
    """
    from backend.exportar_dat import escribir_dat
    if dat_path is None:
        dat_path = os.path.join(AQUI, "rsu_opl_tmp.dat")
    escribir_dat(datos, dat_path)
    return resolver(dat_path, **kw)


def _imprimir(res: dict) -> None:
    print("=" * 60)
    print("  RESULTADO (oplrun / OPL)")
    print("=" * 60)
    print(f"  estado          : {res['status']}")
    print(f"  objetivo (Ec.1) : {res['objetivo']}")
    if res["objetivos"]:
        d, i, t = res["objetivos"]
        print(f"  objetivos       : desconexion={d:g}  instalacion={i:g}  trafico={t:g}")
    print(f"  RSU desplegadas : {res['n_rsu_elegidos']}")
    if res["n_rsu_elegidos"] <= 20:
        print(f"                    {res['seleccionados']}")
    r = res["reparto"]
    if r:
        print(f"  cobertura       : {r['cobertura_pct']:.2f} %  "
              f"({r['conectados']:.0f}/{r['n_pares']})")
        print(f"  directos        : {r['directos']:.0f}   "
              f"multisalto: {r['multisalto']:.0f}   "
              f"desconectados: {r['desconectados']:.0f}")
    print(f"  reloj           : {res['segundos_solver']:.1f} s")
    if res.get("salida_cruda"):
        print("\n  ultimas lineas de oplrun:")
        for l in res["salida_cruda"].splitlines():
            print("   ", l)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Resuelve el modelo de RSU con oplrun")
    ap.add_argument("--dat", default=None, help="archivo .dat a resolver")
    ap.add_argument("--micro", action="store_true",
                    help="usa el micro-ejemplo de validación (debe dar [1, 3])")
    ap.add_argument("--suma", action="store_true",
                    help="usa el modelo de suma ponderada en vez del lexicográfico")
    ap.add_argument("--log", action="store_true", help="muestra la salida de oplrun")
    args = ap.parse_args()

    dat = args.dat or os.path.join(
        AQUI, "rsu_micro.dat" if args.micro else "rsu_backend.dat")
    modelo = MODELO_SUMA if args.suma else MODELO_LEX

    print(f"oplrun  : {encontrar_oplrun()}")
    print(f"modelo  : {os.path.basename(modelo)}")
    print(f"datos   : {dat}\n")

    res = resolver(dat, modelo=modelo, mostrar_log=args.log)
    _imprimir(res)

    if args.micro:
        ok = sorted(res["seleccionados"]) == [1, 3]
        print(f"\n  Validación: esperado [1, 3], obtenido "
              f"{sorted(res['seleccionados'])} -> {'OK' if ok else 'FALLO'}")


if __name__ == "__main__":
    main()
