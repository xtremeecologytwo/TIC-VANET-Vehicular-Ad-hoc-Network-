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
  resumen: { n_escenarios: number; n_vehiculos: number; n_rsu_candidatos: number; n_tuplas_CVR: number };
  objetivo: number | null;
  n_desplegadas: number;
  status: string;
  desplegadas: Rsu[];
  candidatas: Rsu[];
}
export interface ConnFrame {
  t: number;
  vehiculos: { id: string; lat: number; lon: number }[];
  v2i: { v: string; rsu: string; a: LatLon; b: LatLon }[];
  v2v: { a: LatLon; b: LatLon }[];
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
  optimize: (body: { H: number; max_rsu: number | null }) =>
    req<OptResult>("/api/optimize", { method: "POST", body: JSON.stringify(body) }),
  timesteps: () => req<{ timesteps: number[] }>("/api/timesteps"),
  connectivity: (t: number) => req<ConnFrame>(`/api/connectivity?t=${t}`),
};
