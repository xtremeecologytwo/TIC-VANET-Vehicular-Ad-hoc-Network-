"""
semillas.py — campañas con varias semillas y su reporte agregado
================================================================
Comprueba, sin ejecutar SUMO ni CPLEX y sin escribir en el catálogo:

    1. `semillas` se valida (lista de enteros sin repetir; no junto a `semilla`)
    2. por_semilla desdobla la campaña en <nombre>_s<semilla> con los MISMOS
       puntos y una configuración fija que solo cambia en la semilla
    3. orden_por_semilla ejecuta semilla a semilla entre varias campañas
    4. resumir_semillas da la media, la desviación y el IC 95 % correctos
    5. las figuras y tablas del reporte agregado se generan, con datos
       sintéticos hechos a partir de las campañas reales del catálogo

Uso (desde la raíz del repo):
    python pruebas/semillas.py                # figuras en una carpeta temporal
    python pruebas/semillas.py <carpeta>      # figuras en <carpeta>, para mirarlas
"""

import math
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import numpy as np                      # noqa: E402
import pandas as pd                     # noqa: E402

from backend import campana, reporte    # noqa: E402

FALLOS: list[str] = []


def comprobar(cond: bool, texto: str) -> None:
    print(("  ok    " if cond else "  FALLA ") + texto)
    if not cond:
        FALLOS.append(texto)


def spec_base(**extra) -> dict:
    return {"nombre": "prueba_sem", "area": "centro",
            "factores": {"vehiculos": [2500], "fisica": ["6:r90"], "H": [1, 3], "filtrado": ["C"]},
            **extra}


def main() -> int:
    print("1. validación de `semillas`")
    s = campana.validar_spec(spec_base(semillas=[42, 1, 2]))
    comprobar("semilla" not in s, "con `semillas` no se añade la semilla por defecto")
    for malo, motivo in (({"semillas": [42, 42]}, "repetidas"), ({"semillas": []}, "vacía"),
                         ({"semillas": [1, "2"]}, "con texto"), ({"semillas": [True]}, "booleana"),
                         ({"semillas": [1], "semilla": 3}, "junto a `semilla`")):
        try:
            campana.validar_spec(spec_base(**malo))
            comprobar(False, f"rechaza una lista {motivo}")
        except campana.ErrorCampana:
            comprobar(True, f"rechaza una lista {motivo}")

    print("2. una campaña por semilla")
    unas = campana.por_semilla(s)
    comprobar([u["nombre"] for u in unas] == ["prueba_sem_s42", "prueba_sem_s1", "prueba_sem_s2"],
              "nombres <nombre>_s<semilla>")
    comprobar(all(u["familia"] == "prueba_sem" and "semillas" not in u for u in unas),
              "llevan `familia` y no la lista")
    puntos = [sorted(p["punto"] for p in campana.puntos(u)) for u in unas]
    comprobar(all(p == puntos[0] for p in puntos), "los mismos puntos en cada semilla")
    bbox = [-78.518, -0.2286, -78.5036, -0.2119]
    cfgs = [campana.config_fija(u, bbox) for u in unas]
    dif = {k for c in cfgs[1:] for k in c if c[k] != cfgs[0][k]}
    comprobar(dif == {"semilla"}, f"la configuración fija solo cambia en la semilla ({sorted(dif)})")
    try:
        campana.validar_spec(dict(unas[0]))      # el reporte lo hace con el spec guardado
        comprobar(True, "el spec de una semilla se puede volver a validar")
    except campana.ErrorCampana as e:
        comprobar(False, f"el spec de una semilla se puede volver a validar ({e})")
    sola = campana.validar_spec(spec_base())
    comprobar(campana.por_semilla(sola) == [sola], "sin `semillas`, la propia campaña")

    print("3. orden semilla a semilla")
    a = campana.validar_spec(spec_base(nombre="a", semillas=[42, 1]))
    b = campana.validar_spec(spec_base(nombre="b", semillas=[42, 1]))
    orden = [u["nombre"] for _, u in campana.orden_por_semilla([a, b])]
    comprobar(orden == ["a_s42", "b_s42", "a_s1", "b_s1"], f"orden {orden}")
    solo = [u["nombre"] for _, u in campana.orden_por_semilla([a, b], semilla=1)]
    comprobar(solo == ["a_s1", "b_s1"], f"--semilla 1 -> {solo}")

    print("4. medias e IC 95 %")
    df = pd.DataFrame({"punto": ["p"] * 3 + ["q"] * 3, "semilla": [42, 1, 2] * 2,
                       "n_rsu": [10, 12, 14, 5, 5, np.nan],
                       "cortado": [False, True, False, False, False, False],
                       "sin_solucion": [False] * 5 + [True],
                       "vehiculos": [2500] * 6, "fisica": ["6:r90"] * 6})
    r = reporte.resumir_semillas(df).set_index("punto")
    comprobar(abs(r.loc["p", "n_rsu"] - 12) < 1e-9, "media")
    comprobar(abs(r.loc["p", "n_rsu_sd"] - 2) < 1e-9, "desviación con n - 1")
    comprobar(abs(r.loc["p", "n_rsu_ic95"] - 4.303 * 2 / math.sqrt(3)) < 1e-9, "IC 95 % con t(2) = 4,303")
    comprobar(r.loc["q", "n_rsu_n"] == 2 and r.loc["q", "n_rsu"] == 5,
              "una semilla sin solución no entra en la media")
    comprobar(bool(r.loc["p", "cortado"]) and r.loc["p", "n_cortados"] == 1,
              "cortado si lo fue en alguna semilla")
    comprobar(reporte.t975(9) == 2.262 and reporte.t975(35) == 2.042 and reporte.t975(500) == 1.96,
              "tabla de la t de Student")

    print("5. reporte agregado (datos sintéticos a partir de campañas reales)")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    base_destino = sys.argv[1] if len(sys.argv) > 1 else None
    if base_destino:
        os.makedirs(base_destino, exist_ok=True)
    rng = np.random.default_rng(0)
    for camp in ("fisica_v1", "trafico_v1"):
        real = reporte.tabla(camp)
        if real.empty:
            print(f"  (no hay {camp} en el catálogo: se salta)")
            continue
        partes = []
        for semilla in (42, 1, 2):
            t = real.copy()
            t["semilla"], t["campana"] = semilla, f"{camp}_s{semilla}"
            for m in ("n_rsu", "cobertura_pct", "frac_multisalto", "uso_capacidad", "segundos_solver", "cvr"):
                t[m] = t[m] * (1 + rng.normal(0, 0.05, len(t)))
            partes.append(t)
        crudo = pd.concat(partes, ignore_index=True)
        destino = tempfile.mkdtemp(prefix=f"semillas_{camp}_", dir=base_destino)
        with plt.rc_context(reporte.ESTILO):
            escritos = reporte._generar(reporte.resumir_semillas(crudo), destino, reporte._spec(camp), plt,
                                        crudo=crudo)
        pngs = [e for e in escritos if e.endswith(".png")]
        texs = [e for e in escritos if e.endswith(".tex")]
        con_ic = all("pm$" in open(t, encoding="utf-8").read() for t in texs)
        comprobar(bool(pngs) and con_ic,
                  f"{camp}: {len(pngs)} figuras y {len(texs)} tablas con media ± IC -> {destino}")

    print()
    if FALLOS:
        print(f"{len(FALLOS)} comprobación(es) fallida(s)")
        return 1
    print("todo bien")
    return 0


if __name__ == "__main__":
    sys.exit(main())
