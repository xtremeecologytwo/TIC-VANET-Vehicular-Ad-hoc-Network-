/*********************************************************************
 * rsu_model_lex.mod
 * Despliegue óptimo de RSU — MULTI-OBJETIVO LEXICOGRÁFICO (3 niveles)
 *
 * Basado en: Urquiza-Aguiar, Tripp-Barba, Aguilar Igartua (2016),
 *            "A Stochastic Optimization Model for the Placement of RSUs".
 *
 * ¿POR QUÉ ESTE ARCHIVO EXISTE?
 * -----------------------------
 * `rsu_model.mod` implementa la Ec. 1 tal cual: una SUMA de instalación y
 * tráfico. Este implementa la misma formulación pero resuelta por PRIORIDADES,
 * que es lo que hace hoy la ruta de docplex (`optimizar_rsu.py`).
 *
 * Su propósito es de VALIDACIÓN CRUZADA: dos implementaciones independientes
 * —OPL/oplrun por un lado, docplex por otro— del mismo modelo deben dar el
 * mismo resultado. Si difieren, una de las dos está mal, y conviene saberlo
 * antes de defender los números.
 *
 * LOS TRES NIVELES, en orden de prioridad:
 *   1. carga desconectada   -> maximiza la cobertura
 *   2. coste de instalación -> entre las de cobertura máxima, la de menos RSU
 *   3. coste de tráfico     -> entre esas, la de menos saltos
 *
 * La partición del término de tráfico en (1) y (3) es exacta porque en este
 * modelo `h == hmax` ocurre SI Y SOLO SI `r == rInf`: la única tupla con salto
 * hmax es la que va al RSU artificial (ver backend/exportar_dat.py).
 *
 * Consecuencia importante: con esta separación, `P[hmax]` (la penalización de
 * desconexión) NO aparece en ningún objetivo, ni en la Ec. 4 —que excluye a
 * rInf—. El parámetro se vuelve inerte, igual que en la ruta de docplex.
 *********************************************************************/

// ===================== CONJUNTOS Y PARÁMETROS =====================

int hmax = ...;            // nº máximo de saltos (incluye el salto al RSU artificial)
int rInf = ...;            // id del RSU artificial r_inf (representa "desconectado")
int MaxR = ...;            // nº máximo de RSU reales que se pueden desplegar

{int} R = ...;             // ids de RSU candidatos (INCLUYE rInf)
{int} S = ...;             // ids de escenarios (snapshots)
{int} V = ...;             // ids de todos los vehículos

{int} Vs[S] = ...;         // vehículos presentes en cada escenario s

float Cost[R] = ...;       // costo de instalación de cada RSU (Cost[rInf] = 0)
float Cap[R]  = ...;       // capacidad de carga de cada RSU (Cap[rInf] = grande)
float P[1..hmax] = ...;    // penalización por nº de saltos (P[hmax] = grande: desconexión)
float L[S][V] = ...;       // carga de tráfico de cada vehículo en cada escenario

// CVR: tuplas de conectividad <escenario, saltos, vehículo, rsu>
tuple Cvr { int s; int h; int v; int r; }
{Cvr} CVR = ...;

// ===================== VARIABLES =====================

// Sel[r] : 1 si se despliega el RSU r  (1ª etapa)
dvar boolean Sel[R];

// Rts_{s,h,v,r} : fracción [0,1] de la carga de v servida por r a h saltos (2ª etapa)
dvar float Rts[CVR] in 0..1;

// ===================== EXPRESIONES OBJETIVO =====================
// Se declaran como `dexpr` para poder leerlas luego en el bloque execute.

// (1) Carga que se queda sin servicio: la que cae en el RSU artificial.
//     Se pesa solo por L, NO por P[hmax]: la prioridad sustituye al peso.
dexpr float ObjDesconexion =
    sum(t in CVR : t.h == hmax) Rts[t] * L[t.s][t.v];

// (2) Coste de desplegar antenas.
dexpr float ObjInstalacion =
    sum(r in R) Sel[r] * Cost[r];

// (3) Coste por saltos del tráfico que SÍ se sirve.
dexpr float ObjTrafico =
    sum(t in CVR : t.h != hmax) Rts[t] * P[t.h] * L[t.s][t.v];

// Ec. 1 original (los tres términos fundidos con sus pesos). No se optimiza:
// se reporta para poder comparar contra corridas de suma ponderada.
dexpr float ObjEc1 =
    sum(r in R) Sel[r] * Cost[r]
  + sum(t in CVR) Rts[t] * P[t.h] * L[t.s][t.v];

// ===================== OBJETIVO =====================
// `staticLex` es el equivalente en OPL de `minimize_static_lex` de docplex:
// optimiza el primero, lo fija, optimiza el segundo, y así sucesivamente.
minimize staticLex(ObjDesconexion, ObjInstalacion, ObjTrafico);

// ===================== RESTRICCIONES =====================
// Idénticas a rsu_model.mod: lo único que cambia es CÓMO se optimiza.
subject to {

  // (Ec. 2) toda la carga de cada vehículo de cada escenario debe servirse
  forall(s in S, v in Vs[s])
    sum(t in CVR : t.s == s && t.v == v) Rts[t] == 1;

  // (Ec. 3) solo se puede usar una RSU si está seleccionada
  forall(t in CVR)
    Rts[t] <= Sel[t.r];

  // (Ec. 4) no exceder la capacidad de cada RSU real (no aplica a rInf)
  forall(s in S, r in R : r != rInf)
    sum(t in CVR : t.s == s && t.r == r) Rts[t] * P[t.h] * L[t.s][t.v] <= Cap[r];

  // (Ec. 5) nº máximo de RSU reales desplegados
  sum(r in R : r != rInf) Sel[r] <= MaxR;

  // el RSU artificial siempre está "disponible" (todos pueden caer en él)
  Sel[rInf] == 1;
}

// ===================== SALIDA (parseable por Python) =====================
// Formato CLAVE=valor, una por línea, para que resolver_opl.py lo lea sin
// depender del formato de log de oplrun (que cambia entre versiones).
execute IMPRIMIR {
  writeln("OBJETIVO=", ObjEc1);
  writeln("OBJ_DESCONEXION=", ObjDesconexion);
  writeln("OBJ_INSTALACION=", ObjInstalacion);
  writeln("OBJ_TRAFICO=", ObjTrafico);

  var seleccionados = "";
  var nSel = 0;
  for (var r in R) {
    if (r != rInf && Sel[r] > 0.5) {
      seleccionados = seleccionados + r + ",";
      nSel = nSel + 1;
    }
  }
  writeln("SELECTED=", seleccionados);
  writeln("N_RSU=", nSel);

  // Reparto de la carga por número de saltos: sirve para comprobar que la
  // cobertura y el multisalto coinciden con los de docplex, no solo el
  // valor objetivo.
  var pares = 0;
  for (var s in S) pares = pares + Vs[s].size;
  writeln("N_PARES=", pares);

  var desconectados = 0.0;
  var multisalto = 0.0;
  var directos = 0.0;
  for (var t in CVR) {
    var v = Rts[t];
    if (v > 1e-9) {
      if (t.h == hmax)      desconectados = desconectados + v;
      else if (t.h == 1)    directos = directos + v;
      else                  multisalto = multisalto + v;
    }
  }
  writeln("DESCONECTADOS=", desconectados);
  writeln("DIRECTOS=", directos);
  writeln("MULTISALTO=", multisalto);
  // El tiempo NO se pide aqui: cplex.getSolvedTime() solo funciona si el solve
  // se lanzo desde JavaScript, y aqui lo lanza OPL. Lo cronometra Python, que
  // ademas es el que interesa comparar (reloj de pared de punta a punta).
  // 301 = CPX_STAT_MULTIOBJ_OPTIMAL (optimo multi-objetivo demostrado).
  writeln("ESTADO=", cplex.getCplexStatus());
}
