/*********************************************************************
 * rsu_model.mod
 * Modelo de despliegue ÓPTIMO de RSU (Road Side Units)
 * Basado en: Urquiza-Aguiar, Tripp-Barba, Aguilar Igartua (2016),
 *            "A Stochastic Optimization Model for the Placement of RSUs".
 *
 * Elige el subconjunto MÍNIMO de RSU candidatos de modo que los
 * vehículos (en varios escenarios/snapshots) lleguen a alguna RSU
 * por multisalto, penalizando los caminos largos y la desconexión.
 *
 * La entrada CVR = {<s,h,v,r>} se construye desde las matrices S_h
 * del proyecto (multisalto): un 1 en S_h[v][r] del escenario s -> <s,h,v,r>.
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

// S_r : 1 si se despliega el RSU r  (1ª etapa)
dvar boolean Sel[R];

// Rts_{s,h,v,r} : fracción [0,1] de la carga de v servida por r a h saltos (2ª etapa)
dvar float Rts[CVR] in 0..1;

// ===================== OBJETIVO =====================
// (Ec. 1)  minimizar:  costos de instalación  +  tráfico penalizado por saltos
minimize
    sum(r in R) Sel[r] * Cost[r]
  + sum(t in CVR) Rts[t] * P[t.h] * L[t.s][t.v];

// ===================== RESTRICCIONES =====================
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
execute IMPRIMIR {
  writeln("OBJETIVO=", cplex.getObjValue());
  var seleccionados = "";
  for (var r in R) {
    if (r != rInf && Sel[r] > 0.5) {
      seleccionados = seleccionados + r + ",";
    }
  }
  writeln("SELECTED=", seleccionados);
}
