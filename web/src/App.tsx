import { useEffect, useState, useCallback } from "react";
import ScenarioMap from "./components/ScenarioMap";
import { api } from "./api/client";
import type { BBox, LatLon, Rsu, ConnFrame } from "./api/client";
import "./App.css";

/* ---------- componentes de UI ---------- */

function Stepper({ activo }: { activo: number }) {
  const pasos = [
    ["M1", "Escenario", "OSM → SUMO"],
    ["M2", "Conectividad", "V2V · V2I · multisalto"],
    ["M3", "Optimización", "despliegue de RSU"],
  ];
  return (
    <div className="stepper">
      {pasos.map(([n, t, s], i) => {
        const cls = i + 1 < activo ? "done" : i + 1 === activo ? "active" : "";
        return (
          <div className={`step ${cls}`} key={n}>
            <span className="n">{n}</span>
            <div><div className="t">{t}</div><div className="s">{s}</div></div>
          </div>
        );
      })}
    </div>
  );
}

function Slider({ label, value, min, max, step = 1, unit = "", onChange }: {
  label: string; value: number; min: number; max: number; step?: number; unit?: string;
  onChange: (v: number) => void;
}) {
  return (
    <div className="field">
      <label>{label}<span className="v mono">{value}{unit}</span></label>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  );
}

function Tile({ label, value, sub, tone }: { label: string; value: string | number; sub?: string; tone?: "ok" | "warn" }) {
  return (
    <div className={`tile ${tone ?? ""}`}>
      <div className="lab">{label}</div>
      <div className="num mono">{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

/* ---------- app ---------- */

const DEF = { num_vehiculos: 100, tiempo_min: 120, min_grado: 4, radio_cluster: 20, radio_obu: 300, step_min: 2, H: 3 };

export default function App() {
  const [p, setP] = useState(DEF);
  const [bbox, setBbox] = useState<BBox | null>(null);
  const [edificios, setEdificios] = useState<LatLon[][] | null>(null);
  const [candidatas, setCandidatas] = useState<Rsu[] | null>(null);
  const [desplegadas, setDesplegadas] = useState<Rsu[] | null>(null);
  const [bounds, setBounds] = useState<[LatLon, LatLon] | null>(null);
  const [kpis, setKpis] = useState<Record<string, string | number>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activo, setActivo] = useState(1);
  // Animación de conectividad
  const [timesteps, setTimesteps] = useState<number[]>([]);
  const [tIdx, setTIdx] = useState(0);
  const [frame, setFrame] = useState<ConnFrame | null>(null);
  const [playing, setPlaying] = useState(false);

  const set = (k: keyof typeof DEF) => (v: number) => setP((s) => ({ ...s, [k]: v }));

  const run = useCallback(async (nombre: string, fn: () => Promise<void>) => {
    setBusy(nombre); setError(null);
    try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  }, []);

  const seek = useCallback(async (i: number, ts = timesteps) => {
    if (!ts.length) return;
    const idx = (i + ts.length) % ts.length;
    setTIdx(idx);
    try { setFrame(await api.connectivity(ts[idx])); } catch { /* noop */ }
  }, [timesteps]);

  const cargarTimesteps = useCallback(async () => {
    const { timesteps: ts } = await api.timesteps();
    setTimesteps(ts);
    if (ts.length) { setTIdx(0); try { setFrame(await api.connectivity(ts[0])); } catch { /* noop */ } }
  }, []);

  // Reproducción: avanza un instante cada 700 ms.
  useEffect(() => {
    if (!playing || timesteps.length === 0) return;
    const id = setInterval(() => {
      setTIdx((i) => {
        const n = (i + 1) % timesteps.length;
        api.connectivity(timesteps[n]).then(setFrame).catch(() => {});
        return n;
      });
    }, 700);
    return () => clearInterval(id);
  }, [playing, timesteps]);

  // Rehidratar: si el servidor ya tiene un escenario en output/, cargarlo.
  useEffect(() => {
    api.state().then((s) => {
      if (s.tiene_escenario && s.bounds) {
        setBounds(s.bounds);
        api.buildings().then((b) => setEdificios(b.edificios)).catch(() => {});
        setKpis((k) => ({ ...k, Junctions: s.n_junctions, Edificios: s.n_edificios }));
        if (s.tiene_simulacion) { setActivo(3); cargarTimesteps().catch(() => {}); }
        else if (s.tiene_rsus) setActivo(2);
      }
    }).catch((e) => setError(`API no disponible: ${e.message}`));
  }, [cargarTimesteps]);

  const generar = () => run("Generando escenario", async () => {
    if (!bbox) { setError("Dibuja un rectángulo en el mapa primero."); return; }
    const r = await api.generate({ bbox, num_vehiculos: p.num_vehiculos, tiempo_min: p.tiempo_min });
    setEdificios(r.edificios); setBounds(r.bounds);
    setCandidatas(null); setDesplegadas(null);
    setKpis({ Junctions: r.n_junctions, Edificios: r.n_edificios });
    setActivo(1);
  });

  const filtrar = () => run("Filtrando RSU", async () => {
    const r = await api.filterRsu({ min_grado: p.min_grado, radio_cluster: p.radio_cluster });
    setCandidatas(r.rsus); setDesplegadas(null);
    setKpis((k) => ({ ...k, "RSU candidatas": r.n_candidatas, "Reducción": `${r.reduccion_pct}%` }));
    setActivo(2);
  });

  const simular = () => run("Simulando conectividad", async () => {
    const r = await api.simulate({ radio_obu: p.radio_obu, step_min: p.step_min, bidireccional: true });
    setKpis((k) => ({
      ...k, "Tuplas V2I": r.v2i.total_tuplas, Snapshots: r.v2i.total_timesteps,
      "Tuplas V2V": r.v2v.total_tuplas, Vehículos: r.v2v.n_vehiculos,
    }));
    setActivo(3);
    await cargarTimesteps();
  });

  const optimizar = () => run("Optimizando despliegue", async () => {
    const r = await api.optimize({ H: p.H, max_rsu: null });
    setCandidatas(r.candidatas); setDesplegadas(r.desplegadas);
    setKpis((k) => ({
      ...k, Objetivo: r.objetivo ?? "—", "RSU desplegadas": r.n_desplegadas,
      "Tuplas CVR": r.resumen.n_tuplas_CVR,
    }));
    setActivo(3);
  });

  const kpiEntries = Object.entries(kpis);

  return (
    <div className="wrap">
      {/* HEADER */}
      <header className="topbar">
        <div className="brand">
          <span className="sat">🛰️</span>
          <h1>SmartCityNet</h1><span className="div">·</span>
          <span className="who">Consola de simulación y optimización VANET</span>
        </div>
        <span className="tag mono">EPN · TIC 2026</span>
      </header>

      <section className="hero">
        <div className="hero-in">
          <span className="eyebrow">Redes vehiculares ad-hoc · Centro Histórico de Quito</span>
          <h2>Del área en el mapa al despliegue óptimo de RSU</h2>
          <p>Selecciona una zona, genera la red vial con SUMO, simula la conectividad V2V/V2I con
             línea de vista y resuelve el despliegue de <em>Road Side Units</em> con CPLEX.</p>
        </div>
      </section>

      <Stepper activo={activo} />

      {error && <div className="banner err">⚠ {error}</div>}
      {busy && <div className="banner busy">⏳ {busy}…</div>}

      {/* CONSOLA */}
      <div className="console">
        <div className="panel">
          <div className="panel-hd">
            <span className="ttl">Área de trabajo{timesteps.length ? "" : " — dibuja un rectángulo"}</span>
            {frame ? (
              <span className="readout mono">
                t={frame.t}s · {frame.vehiculos.length} veh · {frame.v2i.length} V2I · {frame.v2v.length} V2V
              </span>
            ) : bbox ? (
              <span className="readout mono">{bbox.min_lat.toFixed(3)}, {bbox.min_lon.toFixed(3)}</span>
            ) : null}
          </div>
          <div className="panel-bd map-bd">
            <ScenarioMap edificios={edificios} candidatas={candidatas}
              desplegadas={desplegadas} bounds={bounds} frame={frame} onBbox={setBbox} />
          </div>
          {timesteps.length > 0 && (
            <div className="timeline">
              <button className="tl-play" onClick={() => setPlaying((v) => !v)}
                aria-label={playing ? "Pausar" : "Reproducir"}>{playing ? "❚❚" : "▶"}</button>
              <input type="range" min={0} max={timesteps.length - 1} value={tIdx}
                onChange={(e) => { setPlaying(false); seek(Number(e.target.value)); }} />
              <span className="tl-t mono">t={timesteps[tIdx]}s</span>
              <span className="tl-legend">
                <i style={{ background: "#2557a7" }} />veh
                <i style={{ background: "#0f9d6b" }} />V2I
                <i style={{ background: "#b9770b" }} />V2V
              </span>
            </div>
          )}
        </div>

        <div className="panel">
          <div className="panel-hd"><span className="ttl">Parámetros</span></div>
          <div className="panel-bd">
            <div className="grouplabel">M1 · Escenario</div>
            <Slider label="Vehículos" value={p.num_vehiculos} min={5} max={1000} step={5} onChange={set("num_vehiculos")} />
            <Slider label="Duración" value={p.tiempo_min} min={1} max={180} unit=" min" onChange={set("tiempo_min")} />
            <button className="cta" disabled={!!busy} onClick={generar}>▸ Generar escenario</button>

            <div className="grouplabel">RSU candidatas</div>
            <Slider label="Grado mínimo" value={p.min_grado} min={2} max={8} onChange={set("min_grado")} />
            <Slider label="Radio clúster" value={p.radio_cluster} min={0} max={100} step={5} unit=" m" onChange={set("radio_cluster")} />
            <button className="cta ghost" disabled={!!busy || !edificios} onClick={filtrar}>Filtrar RSU</button>

            <div className="grouplabel">M2 · Conectividad</div>
            <Slider label="Radio OBU" value={p.radio_obu} min={50} max={500} step={25} unit=" m" onChange={set("radio_obu")} />
            <Slider label="Muestreo" value={p.step_min} min={1} max={30} unit=" min" onChange={set("step_min")} />
            <button className="cta ghost" disabled={!!busy || !candidatas} onClick={simular}>Simular conectividad</button>

            <div className="grouplabel">M3 · Optimización</div>
            <Slider label="Saltos H" value={p.H} min={1} max={6} onChange={set("H")} />
            <button className="cta ok" disabled={!!busy} onClick={optimizar}>◉ Optimizar despliegue</button>
          </div>
        </div>
      </div>

      {/* KPIs */}
      {kpiEntries.length > 0 && (
        <>
          <div className="section-h"><span className="k">Resultados</span><span className="rule" /></div>
          <div className="tiles">
            {kpiEntries.map(([k, v]) => (
              <Tile key={k} label={k} value={v}
                tone={k === "Objetivo" || k === "RSU desplegadas" ? "ok" : undefined} />
            ))}
          </div>
        </>
      )}

      <footer className="foot">
        <span>SmartCityNet · Trabajo de Integración Curricular — Escuela Politécnica Nacional</span>
        <span className="mono">React + FastAPI</span>
      </footer>
    </div>
  );
}
