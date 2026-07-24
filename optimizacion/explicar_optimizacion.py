"""
explicar_optimizacion.py
========================
Versión DIDÁCTICA del optimizador de RSU: corre el micro-ejemplo y va
explicando por consola, paso a paso, TODO lo que se hace — desde las
tuplas de conectividad hasta la decisión final del solver CPLEX.

Lee los datos reales de 'rsu_micro.dat', los explica, llama a 'oplrun'
(CPLEX/OPL) y desglosa por qué salió ese resultado.

Uso:
    python optimizacion/explicar_optimizacion.py
    python optimizacion/explicar_optimizacion.py rsu_micro.dat
"""

import os
import re
import sys

# UTF-8 en consola de Windows (caracteres de caja y emojis)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from optimizar_rsu import optimizar   # reutiliza la llamada real a oplrun

AQUI = os.path.dirname(os.path.abspath(__file__))


# ============================================================
# Utilidades
# ============================================================

def titulo(txt):
    print("\n" + "═" * 68)
    print("  " + txt)
    print("═" * 68)


def pausa(msg="(pulsa ENTER para continuar)"):
    """Pausa opcional entre pasos. Se desactiva con la variable SIN_PAUSA=1."""
    if os.environ.get("SIN_PAUSA") == "1":
        return
    try:
        input(f"\n  …{msg}")
    except EOFError:
        pass


# ============================================================
# Parseo simple del archivo .dat (para narrar con datos reales)
# ============================================================

def leer_dat(ruta):
    txt = open(ruta, encoding="utf-8").read()
    # quitar comentarios /* ... */ y // ...
    txt = re.sub(r"/\*.*?\*/", "", txt, flags=re.S)
    txt = re.sub(r"//.*", "", txt)

    def escalar(nombre, defecto=None):
        m = re.search(rf"{nombre}\s*=\s*(\d+)", txt)
        return int(m.group(1)) if m else defecto

    datos = {
        "hmax": escalar("hmax"),
        "rInf": escalar("rInf"),
        "MaxR": escalar("MaxR"),
    }

    # CVR: todas las tuplas <s,h,v,r>
    datos["CVR"] = [tuple(map(int, m)) for m in
                    re.findall(r"<\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*>", txt)]

    # P = [a, b, c]
    mP = re.search(r"P\s*=\s*\[([^\]]*)\]", txt)
    datos["P"] = [float(x) for x in mP.group(1).split(",")] if mP else []

    # Cost = #[ 0:0, 1:1, ... ]#
    mC = re.search(r"Cost\s*=\s*#\[([^\]]*)\]#", txt)
    datos["Cost"] = {}
    if mC:
        for par in re.findall(r"(\d+)\s*:\s*([\d.]+)", mC.group(1)):
            datos["Cost"][int(par[0])] = float(par[1])

    return datos


# ============================================================
# Programa
# ============================================================

def main():
    dat = sys.argv[1] if len(sys.argv) >= 2 else os.path.join(AQUI, "rsu_micro.dat")
    if not os.path.isabs(dat):
        dat = os.path.join(AQUI, dat)

    d = leer_dat(dat)
    CVR = d["CVR"]
    rInf = d["rInf"]
    hmax = d["hmax"]
    P = d["P"]
    Cost = d["Cost"]

    # Derivar conjuntos desde las tuplas
    escenarios = sorted(set(t[0] for t in CVR))
    rsus = sorted(set(t[3] for t in CVR))
    rsus_reales = [r for r in rsus if r != rInf]
    # vehículos por escenario
    Vs = {s: sorted(set(t[2] for t in CVR if t[0] == s)) for s in escenarios}

    print("\n" + "#" * 68)
    print("#  OPTIMIZACIÓN DE RSU  —  explicación paso a paso")
    print("#  (modelo de Urquiza-Aguiar et al. 2016, resuelto con CPLEX/OPL)")
    print("#" * 68)

    # ---------- PASO 1: el objetivo ----------
    titulo("PASO 1 — ¿Qué queremos lograr?")
    print(f"""
  Tenemos {len(rsus_reales)} RSU candidatos: {rsus_reales}
  (más un RSU 'fantasma' r_inf = {rInf}, que representa estar DESCONECTADO).

  Tenemos {len(escenarios)} escenarios (fotos del tráfico en distintos momentos):""")
    for s in escenarios:
        print(f"     · Escenario {s}: vehículos {Vs[s]}")
    print(f"""
  OBJETIVO: elegir el MÍNIMO número de RSU (máximo {d['MaxR']}) de modo que
  todos los vehículos, en todos los escenarios, lleguen a algún RSU —
  prefiriendo caminos cortos (pocos saltos) y evitando desconexiones.""")
    pausa()

    # ---------- PASO 2: las tuplas CVR ----------
    titulo("PASO 2 — La conectividad de entrada (tuplas CVR)")
    print("""
  Cada tupla <s, h, v, r> dice: "en el escenario s, el vehículo v puede
  alcanzar el RSU r usando h saltos". Esto viene del MULTISALTO.""")
    for s in escenarios:
        print(f"\n  Escenario {s}:")
        for (ss, h, v, r) in sorted(t for t in CVR if t[0] == s):
            if r == rInf:
                print(f"     v{v} → r_inf  ({h} saltos)   ← opción de 'desconexión' (penalización enorme)")
            else:
                print(f"     v{v} → R{r}     ({h} salto/s)")
    pausa()

    # ---------- PASO 3: de dónde salen las CVR (fórmulas del multisalto) ----------
    titulo("PASO 3 — De dónde salen las tuplas CVR (fórmulas)")
    print("""
  Las tuplas CVR no son inventadas: salen del MULTISALTO de cada escenario.
  Con  Ã = A ∨ I  (matriz V2V con la identidad)  y  B (matriz V2I):

     B(s,h) = β( Ã^(h-1) · B(s) )     ← conectividad acumulada hasta h saltos   (tu R_h)
     C(s,h) = B(s,h) − B(s,h-1)       ← primera aparición a EXACTAMENTE h saltos (tu S_h)

     CVR = { <s, h, v, r>  :  C(s,h)[v][r] = 1 }

  Es decir: cada 1 en la matriz S_h del escenario s genera una tupla <s,h,v,r>.
  (β = binarizar: todo valor > 0 se vuelve 1.)""")
    pausa()

    # ---------- PASO 4: el modelo de optimización (fórmulas) ----------
    titulo("PASO 4 — El modelo de optimización (fórmulas)")
    print("""
  VARIABLES de decisión:
     S_r           ∈ {0,1}    → 1 si se instala el RSU r
     Rts_{s,h,v,r} ∈ [0,1]    → fracción de la carga de v servida por r a h saltos

  FUNCIÓN OBJETIVO (Ec. 1):

      min     Σ  S_r·Cost_r    +       Σ        Rts_{s,h,v,r} · P_h · L_{s,v}
     S,Rts   r∈R                  (s,h,v,r)∈CVR
             └─ costo instalar ─┘     └──── tráfico penalizado por nº de saltos ────┘

  RESTRICCIONES:

   (Ec.2)      Σ         Rts_{s,h,v,r} = 1     ∀v∈Vs, ∀s   → servir TODO el tráfico de v
           h,r:(s,h,v,r)∈CVR

   (Ec.3)   Rts_{s,h,v,r} ≤ S_r                ∀(s,h,v,r)  → solo usar RSU instalados

   (Ec.4)      Σ      Rts·P_h·L_{s,v} ≤ C_r    ∀s, ∀r≠r∞   → no exceder la capacidad del RSU
            v,h

   (Ec.5)      Σ      S_r ≤ MaxR                           → no instalar más de MaxR RSU
            r≠r∞
""")
    print(f"  En este ejemplo:")
    print(f"     · Penalización por saltos  P_h = {dict(enumerate(P, start=1))}")
    print(f"     · P_{hmax} = {P[hmax-1]:.0f}  es la DESCONEXIÓN (r_inf): enorme a propósito.")
    print(f"     · Carga de tráfico  L_(s,v) = 1  para todos los vehículos.")
    print(f"     · Límite  MaxR = {d['MaxR']}  RSU reales.")
    pausa()

    # ---------- PASO 5: resolver con CPLEX ----------
    titulo("PASO 5 — Resolvemos con CPLEX (oplrun)")
    print("\n  Python lanza el solver con el modelo OPL y estos datos...\n")
    res = optimizar(dat)

    if res["objetivo"] is None:
        print("\n⚠️ El solver no devolvió solución. Salida:\n")
        print(res["salida"])
        return

    seleccionados = res["seleccionados"]

    # ---------- PASO 6: el resultado y cómo se calcula el objetivo ----------
    titulo("PASO 6 — El resultado y cómo se calcula el objetivo")
    print(f"\n  ✅ RSU a desplegar (S_r = 1): {['R'+str(r) for r in seleccionados]}")
    print(f"  Valor objetivo total: {res['objetivo']:.2f}")

    print("\n  Aplicamos la fórmula del objetivo, término a término:")
    print("     Objetivo  =   Σ S_r·Cost_r   +   Σ Rts_{s,h,v,r}·P_h·L_{s,v}")
    print("  (para cada vehículo, el solver toma su mejor ruta entre los RSU elegidos)")

    permitidos = set(seleccionados) | {rInf}
    total_pen = 0.0
    for s in escenarios:
        print(f"\n    Escenario {s}:")
        for v in Vs[s]:
            opciones = [(h, r) for (ss, h, vv, r) in CVR
                        if ss == s and vv == v and r in permitidos]
            # elegir la de menor penalización P[h]
            h_mejor, r_mejor = min(opciones, key=lambda x: P[x[0]-1])
            pen = P[h_mejor - 1]
            total_pen += pen
            destino = "r_inf (DESCONECTADO)" if r_mejor == rInf else f"R{r_mejor}"
            print(f"       v{v}:  Rts·P_h·L = 1 · P_{h_mejor}={P[h_mejor-1]:.0f} · 1 = {pen:.0f}"
                  f"   → vía {destino} ({h_mejor} salto/s)")

    costo = sum(Cost.get(r, 0) for r in seleccionados)
    costos_str = " + ".join(f"Cost_R{r}({int(Cost.get(r,0))})" for r in seleccionados)
    print(f"\n     Σ S_r·Cost_r        = {costos_str} = {costo:.0f}")
    print(f"     Σ Rts·P_h·L_(s,v)   = {total_pen:.0f}")
    print(f"     ──────────────────────────────────────────")
    print(f"     OBJETIVO = {costo:.0f} + {total_pen:.0f} = {costo + total_pen:.0f}"
          f"   (= {res['objetivo']:.0f} que dio el solver ✓)")

    no_elegidos = [r for r in rsus_reales if r not in seleccionados]
    titulo("CONCLUSIÓN")
    print(f"""
  · Se instalan: {['R'+str(r) for r in seleccionados]}
  · NO se instalan: {['R'+str(r) for r in no_elegidos] if no_elegidos else '(ninguno; se usaron todos)'}
  · El modelo eligió ese conjunto porque es el que conecta a más vehículos
    con el menor costo + penalización por saltos.

  💡 Prueba: cambia 'MaxR = 1' en {os.path.basename(dat)} y vuelve a correr.
     Verás que el modelo se ve forzado a desconectar a alguien y el objetivo
     se dispara (por la penalización de r_inf).
""")


if __name__ == "__main__":
    main()
