/* Cliente de la API SmartCityNet (FastAPI). En dev, Vite proxya /api → :8000
   (ver vite.config.ts), así que basta con rutas relativas. */

export type LatLon = [number, number];

export interface Rsu { id: string; lat: number; lon: number; grado: number | null; }
export interface BBox { min_lon: number; min_lat: number; max_lon: number; max_lat: number; }

export interface ScenarioResult {
  n_junctions: number;
  n_edificios: number;
  edificios: LatLon[][];
  bounds: [LatLon, LatLon];
  pasos: { paso: string; exito: boolean; mensaje: string }[];
}
export interface RsuResult {
  rsus: Rsu[]; n_candidatas: number; n_junctions: number; reduccion_pct: number;
}
export interface SimResult {
  v2i: { total_tuplas: number; total_timesteps: number; n_rsus: number };
  v2v: { total_tuplas: number; pares_en_rango: number; n_vehiculos: number; bidireccional: boolean };
  timesteps: number[];
}
export interface OptResult {
  resumen: {
    n_escenarios: number; n_vehiculos: number; n_rsu_candidatos: number;
    n_tuplas_CVR: number;
    /** MaxR con el que se resolvió. Sin límite = nº de RSU candidatas. */
    max_rsu: number;
  };
  objetivo: number | null;
  n_desplegadas: number;
  status: string;
  /** Cómo quedó servida la demanda. Un "par" es un (instante, vehículo). */
  cobertura: {
    n_pares: number;        // total de pares (instante, vehículo)
    conectados: number;     // los que quedan comunicados
    desconectados: number;  // los que caen en el RSU artificial r_inf
    cobertura_pct: number;  // 100 * conectados / n_pares
    directos: number;       // conectados a 1 salto (V2I directo)
    multisalto: number;     // conectados a 2..H saltos (puenteados por V2V)
    por_salto: Record<string, number>;
  } | null;
  /** Cómo terminó el solver y cuánto tardó (para saber si topó el límite). */
  solver: {
    status: string;          // frase cruda de CPLEX
    etiqueta: string;        // legible: "Óptimo demostrado" / "Cortado por tiempo"
    detalle: string;         // qué significa, en una frase
    optimo: boolean;         // terminó solo: no existe mejor solución
    corto_por_tiempo: boolean; // se quedó sin tiempo y devolvió la mejor hallada
    segundos: number;        // tiempo del motor CPLEX (lo que se compara con el tope)
    segundos_total: number;  // armado del modelo + motor
    limite_tiempo: number | null; // el tope que se le dio (null = sin límite)
  };
  desplegadas: Rsu[];
  candidatas: Rsu[];
}
export interface ConnFrame {
  t: number;
  vehiculos: { id: string; lat: number; lon: number }[];
  v2i: { v: string; rsu: string; a: LatLon; b: LatLon }[];
  v2v: { a: LatLon; b: LatLon }[];
}
export interface V2iTuple { t: number; vehiculo: string; rsu: string; distancia: number; }
export interface V2vTuple { t: number; vehiculo_i: string; vehiculo_j: string; distancia: number; }
export interface PorSalto { h: number; pares_acumulados: number; vehiculos_conectados: number; pares_nuevos: number; }
export interface Multihop {
  t: number; H: number; vehiculos: string[]; rsu_ids: string[];
  A: number[][]; B: number[][]; R: number[][][]; S: number[][][]; D: number[][]; d: number[];
  resumen: {
    n_vehiculos: number; m_rsus: number; por_salto: PorSalto[];
    vehiculos_desconectados: number; ids_desconectados: string[];
  };
}
export interface AppState {
  tiene_escenario: boolean; tiene_rsus: boolean; tiene_simulacion: boolean;
  n_junctions: number; n_edificios: number; n_rsus: number;
  bounds: [LatLon, LatLon] | null;
}

async function req<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail ?? msg; } catch { /* noop */ }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => req<{ status: string }>("/api/health"),
  state: () => req<AppState>("/api/state"),
  buildings: () => req<{ edificios: LatLon[][]; bounds: [LatLon, LatLon] }>("/api/scenario/buildings"),
  generate: (body: { bbox: BBox; num_vehiculos: number; tiempo_min: number }) =>
    req<ScenarioResult>("/api/scenario/generate", { method: "POST", body: JSON.stringify(body) }),
  filterRsu: (body: { min_grado: number; radio_cluster: number }) =>
    req<RsuResult>("/api/rsu/filter", { method: "POST", body: JSON.stringify(body) }),
  simulate: (body: { radio_obu: number; step_min: number; bidireccional: boolean }) =>
    req<SimResult>("/api/simulate", { method: "POST", body: JSON.stringify(body) }),
  optimize: (body: {
    H: number; max_rsu: number | null; limite_tiempo: number | null;
  }) =>
    req<OptResult>("/api/optimize", { method: "POST", body: JSON.stringify(body) }),
  timesteps: () => req<{ timesteps: number[] }>("/api/timesteps"),
  connectivity: (t: number) => req<ConnFrame>(`/api/connectivity?t=${t}`),
  tuplesV2i: (limit = 500) => req<{ total: number; tuplas: V2iTuple[] }>(`/api/tuples/v2i?limit=${limit}`),
  tuplesV2v: (limit = 500) => req<{ total: number; tuplas: V2vTuple[] }>(`/api/tuples/v2v?limit=${limit}`),
  multihop: (t: number, H: number) => req<Multihop>(`/api/multihop?t=${t}&H=${H}`),
};
