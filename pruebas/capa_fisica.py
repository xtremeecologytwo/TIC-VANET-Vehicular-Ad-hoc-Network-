"""
capa_fisica.py — comprueba la capa física contra las cifras del tutor
=====================================================================
1. C₀ y C₁ de `backend/capa_fisica.capacidad` frente a las dos tablas de
   `ieee80211p_unicast_capacity.pdf` (32 valores, tolerancia 0,001 Mb/s).
2. Que el código del tutor se importa y reproduce su ejemplo del documento:
   6 Mb/s, 1000 B → r80 = 200 m, r90 = 100 m (CSV) y Γ_6 ≈ 1,37 con r90.

    python pruebas/capa_fisica.py
"""

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from backend import capa_fisica as cf  # noqa: E402

# (tasa, bytes) -> (C0, C1) tal como aparecen en las tablas de la nota técnica.
TABLA = {
    (3.0, 500): (2.367, 2.238), (4.5, 500): (3.284, 3.041), (6.0, 500): (4.158, 3.775),
    (9.0, 500): (5.540, 4.881), (12.0, 500): (6.645, 5.718), (18.0, 500): (8.299, 6.903),
    (24.0, 500): (9.390, 7.641), (27.0, 500): (9.950, 8.008),
    (3.0, 1000): (2.644, 2.561), (4.5, 1000): (3.784, 3.617), (6.0, 1000): (4.920, 4.642),
    (9.0, 1000): (6.838, 6.312), (12.0, 1000): (8.602, 7.786), (18.0, 1000): (11.331, 9.956),
    (24.0, 1000): (13.652, 11.704), (27.0, 1000): (14.440, 12.279),
}


def main() -> int:
    fallos = 0
    print("  tasa  bytes      C0 nota   C0 calc      C1 nota   C1 calc")
    for (rate, nbytes), (c0, c1) in TABLA.items():
        c = cf.capacidad(rate, nbytes)
        ok = abs(c["c0_mbps"] - c0) < 1e-3 and abs(c["c1_mbps"] - c1) < 1e-3
        fallos += not ok
        print(f"  {rate:4g}  {nbytes:5d}   {c0:9.3f} {c['c0_mbps']:9.3f}    "
              f"{c1:9.3f} {c['c1_mbps']:9.3f}   {'ok' if ok else 'FALLA'}")
    print(f"\n  capacidad: {32 - fallos}/32 valores coinciden")

    r = cf.resumen(6.0, 1000, "with_interference", "r90")
    radios = r["radios"]
    g6 = next(f["penalty_factor"] for f in r["multisalto"] if f["n_hops"] == 6)
    # Sin caracteres fuera de ASCII en los print: la consola de Windows (cp1252)
    # no puede escribir la letra griega y el script reventaria al final.
    print(f"\n  6 Mb/s, 1000 B: r80 = {radios['r80_m']:g} m, r90 = {radios['r90_m']:g} m, "
          f"Gamma_6(r90) = {g6:.4f}   [{r['fuente']['alcance']}]")
    ok2 = radios["r80_m"] == 200.0 and radios["r90_m"] == 100.0 and abs(g6 - 1.3725) < 1e-3
    print("  ejemplo del documento:", "ok" if ok2 else "FALLA")

    # Un cálculo en vivo con el código del tutor, para verificar que se importa
    # y corre (misma estadística, no las mismas cifras: otra corriente aleatoria).
    v = cf.resumen(6.0, 1000, "with_interference", "r90", semilla=1, n_muestras=1000)
    print(f"  en vivo (semilla 1, 1000 muestras): r90 = {v['radios']['r90_m']} m, "
          f"Gamma_6 = {v['multisalto'][5]['penalty_factor']:.3f}")

    return 0 if (fallos == 0 and ok2) else 1


if __name__ == "__main__":
    sys.exit(main())
