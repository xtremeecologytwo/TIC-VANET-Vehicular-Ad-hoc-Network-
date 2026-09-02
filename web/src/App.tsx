import { useEffect, useState, useCallback } from "react";
import ScenarioMap from "./components/ScenarioMap";
import ResultsTabs from "./components/ResultsTabs";
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

/** Campo numérico escribible (para valores exactos, como MaxR o el tope del solver). */
function Num({ label, value, min, max, onChange }: {
  label: string; value: number; min: number; max: number; onChange: (v: number) => void;
}) {
  return (
    <label className="field num">
      <span>{label}</span>
      <input type="number" className="mono" min={min} max={max} value={value}
        onChange={(e) => {
          const v = Number(e.target.value);
          if (Number.isFinite(v)) onChange(Math.min(max, Math.max(min, Math.round(v))));
        }} />
    </label>
  );
}

function Tile({ label, value, sub, tone }: { label: string; value: string | number; sub?: string; tone?: "ok" | "warn" }) {
  // Los valores de texto largo (p. ej. "Cortado por tiempo") no caben con el
  // cuerpo grande de los números: se muestran en un tamaño menor.
  const texto = typeof value === "string" && value.length > 9;
  return (
    <div className={`tile ${tone ?? ""}`}>
      <div className="lab">{label}</div>
      <div className={`num mono ${texto ? "txt" : ""}`}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

/** Un KPI puede ser un valor suelto o llevar subtítulo y color. */
type Kpi = string | number | { value: string | number; sub?: string; tone?: "ok" | "warn" };

/* ---------- app ---------- */

const DEF = { num_vehiculos: 100, tiempo_min: 120, min_grado: 4, radio_cluster: 20, radio_obu: 300, step_min: 2, H: 3 };

export default function App() {
  const [p, setP] = useState(DEF);
  const [bbox, setBbox] = useState<BBox | null>(null);
  const [edificios, setEdificios] = useState<LatLon[][] | null>(null);
  const [candidatas, setCandidatas] = useState<Rsu[] | null>(null);
  const [desplegadas, setDesplegadas] = useState<Rsu[] | null>(null);
  const [bounds, setBounds] = useState<[LatLon, LatLon] | null>(null);
  const [kpis, setKpis] = useState<Record<string, Kpi>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activo, setActivo] = useState(1);
  // Animación de conectividad
  const [timesteps, setTimesteps] = useState<number[]>([]);
  const [tIdx, setTIdx] = useState(0);
  const [frame, setFrame] = useState<ConnFrame | null>(null);
  const [playing, setPlaying] = useState(false);
  const [drawing, setDrawing] = useState(false);
  const [coberturaOn, setCoberturaOn] = useState(false);
  const [coberturaR, setCoberturaR] = useState(200);
  // MaxR: límite del nº de RSU desplegables. Apagado = como estaba (el backend
  // lo fija al nº de RSU candidatas, así que la restricción no ata).
  const [maxRsuOn, setMaxRsuOn] = useState(false);
  const [maxRsu, setMaxRsu] = useState(50);
  // Tope de tiempo del solver. Apagado = sin límite: CPLEX busca hasta demostrar
  // el óptimo (la petición se queda esperando todo ese rato).
  const [topeOn, setTopeOn] = useState(true);
  const [tope, setTope] = useState(60);

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

  // Arranca EN BLANCO: solo comprueba que la API responda (no carga el escenario
  // precargado, para que el usuario seleccione el área desde cero).
  useEffect(() => {
    api.health().catch(() =>
      setError("API no disponible. Arranca el backend: uvicorn api.main:app --reload --port 8000"));
  }, []);

  const generar = () => run("Generando escenario", async () => {
    if (!bbox) { setError("Dibuja un rectángulo en el mapa primero."); return; }
    const r = await api.generate({ bbox, num_vehiculos: p.num_vehiculos, tiempo_min: p.tiempo_min });
    setEdificios(r.edificios); setBounds(r.bounds);
    setCandidatas(null); setDesplegadas(null);
    setTimesteps([]); setFrame(null); setPlaying(false);   // limpia la línea de tiempo del escenario anterior (evita 409)
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
    const r = await api.optimize({
      H: p.H,
      max_rsu: maxRsuOn ? maxRsu : null,
      limite_tiempo: topeOn ? tope : null,
    });
    setCandidatas(r.candidatas); setDesplegadas(r.desplegadas);
    const s = r.solver;
    const c = r.cobertura;
    setKpis((k) => ({
      ...k, Objetivo: r.objetivo != null ? r.objetivo.toFixed(1) : "—",
      "RSU desplegadas": r.n_desplegadas,
      "Tuplas CVR": r.resumen.n_tuplas_CVR,
      // La métrica del proyecto: qué fracción de los pares (instante, vehículo)
      // queda comunicada, y cuántos de ellos gracias al multisalto V2V.
      ...(c ? {
        Cobertura: {
          value: `${c.cobertura_pct.toFixed(2)} %`,
          sub: `${c.conectados.toFixed(0)} de ${c.n_pares} pares (instante, vehículo)`,
          tone: "ok" as const,
        },
        Desconectados: {
          value: c.desconectados.toFixed(0),
          sub: `${(100 - c.cobertura_pct).toFixed(2)} % sin cobertura`,
          tone: c.desconectados > 0 ? ("warn" as const) : undefined,
        },
        Multisalto: {
          value: c.multisalto.toFixed(0),
          sub: `vía V2V · ${c.directos.toFixed(0)} directos a RSU`,
        },
      } : {}),
      MaxR: maxRsuOn ? maxRsu : `sin límite (${r.resumen.max_rsu})`,
      // Cómo terminó el solver y cuánto tardó: si topó el límite, el tiempo
      // medido es el del reloj, no el que costó realmente el problema.
      Solver: { value: s.etiqueta, sub: s.detalle, tone: s.optimo ? "ok" : "warn" },
      "Tiempo solver": {
        value: `${s.segundos.toFixed(1)} s`,
        sub: s.limite_tiempo == null
          ? "sin límite de tiempo"
          : s.corto_por_tiempo
            ? `topó el límite de ${s.limite_tiempo} s`
            : `de un límite de ${s.limite_tiempo} s`,
        tone: s.corto_por_tiempo ? "warn" : undefined,
      },
    }));
    setActivo(3);
  });

  // Reinicia el frontend para empezar un escenario nuevo (el próximo "Generar"
  // sobreescribe el del backend). No borra output/ hasta regenerar.
  const nuevoEscenario = () => {
    setBbox(null); setEdificios(null); setCandidatas(null); setDesplegadas(null);
    setBounds(null); setFrame(null); setTimesteps([]); setKpis({});
    setActivo(1); setPlaying(false); setError(null); setDrawing(true);
  };

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
        <div className="hd-right">
          <button className="chip-btn" onClick={nuevoEscenario} disabled={!!busy}>↺ Nuevo escenario</button>
          <span className="tag mono">EPN · TIC 2026</span>
        </div>
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
            <span className="ttl">Área de trabajo</span>
            <span className="hd-right">
              {drawing ? (
                <span className="readout mono">2 clics en el mapa…</span>
              ) : frame ? (
                <span className="readout mono">
                  t={frame.t}s · {frame.vehiculos.length} veh · {frame.v2i.length} V2I · {frame.v2v.length} V2V
                </span>
              ) : bbox ? (
                <span className="readout mono">{bbox.min_lat.toFixed(3)}, {bbox.min_lon.toFixed(3)}</span>
              ) : null}
              <button className={`chip-btn ${drawing ? "on" : ""}`}
                onClick={() => { if (drawing) setDrawing(false); else nuevoEscenario(); }}>
                {drawing ? "✕ Cancelar" : "◱ Seleccionar área"}
              </button>
            </span>
          </div>
          <div className="panel-bd map-bd">
            <ScenarioMap edificios={edificios} candidatas={candidatas}
              desplegadas={desplegadas} bounds={bounds} frame={frame}
              drawing={drawing} bbox={bbox} cobertura={coberturaOn ? coberturaR : 0}
              onBbox={(b) => { setBbox(b); setDrawing(false); }} />
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
            <label className="chk">
              <input type="checkbox" checked={coberturaOn} onChange={(e) => setCoberturaOn(e.target.checked)} />
              Mostrar cobertura de RSU
            </label>
            {coberturaOn && (
              <Slider label="Radio cobertura" value={coberturaR} min={50} max={500} step={25} unit=" m" onChange={setCoberturaR} />
            )}

            <div className="grouplabel">M2 · Conectividad</div>
            <Slider label="Radio OBU" value={p.radio_obu} min={50} max={500} step={25} unit=" m" onChange={set("radio_obu")} />
            <Slider label="Muestreo" value={p.step_min} min={1} max={30} unit=" min" onChange={set("step_min")} />
            <button className="cta ghost" disabled={!!busy || !candidatas} onClick={simular}>Simular conectividad</button>

            <div className="grouplabel">M3 · Optimización</div>
            <Slider label="Saltos H" value={p.H} min={1} max={6} onChange={set("H")} />
            <label className="chk">
              <input type="checkbox" checked={maxRsuOn}
                onChange={(e) => setMaxRsuOn(e.target.checked)} />
              Limitar nº de RSU (MaxR)
            </label>
            {maxRsuOn && (
              <Num label="MaxR — RSU máximas" value={maxRsu} min={1}
                max={candidatas?.length ?? 1000} onChange={setMaxRsu} />
            )}
            <p className="hint">
              {maxRsuOn
                ? `El modelo podrá desplegar como máximo ${maxRsu} RSU.`
                : "Sin límite: el modelo puede usar todas las RSU candidatas."}
            </p>

            <label className="chk">
              <input type="checkbox" checked={topeOn}
                onChange={(e) => setTopeOn(e.target.checked)} />
              Limitar el tiempo del solver
            </label>
            {topeOn && (
              <Num label="Tope del solver (s)" value={tope} min={5} max={3600}
                onChange={setTope} />
            )}
            <p className="hint">
              {topeOn
                ? `Si CPLEX no termina en ${tope} s, devuelve la mejor solución que haya encontrado.`
                : "Sin límite: CPLEX busca hasta demostrar el óptimo. Puede tardar mucho y la app queda esperando."}
            </p>

            <button className="cta ok" disabled={!!busy || timesteps.length === 0} onClick={optimizar}>◉ Optimizar despliegue</button>
          </div>
        </div>
      </div>

      {/* KPIs */}
      {kpiEntries.length > 0 && (
        <>
          <div className="section-h"><span className="k">Resultados</span><span className="rule" /></div>
          <div className="tiles">
            {kpiEntries.map(([k, v]) => {
              const o = typeof v === "object" ? v : { value: v, sub: undefined, tone: undefined };
              return (
                <Tile key={k} label={k} value={o.value} sub={o.sub}
                  tone={o.tone ?? (k === "Objetivo" || k === "RSU desplegadas" ? "ok" : undefined)} />
              );
            })}
          </div>
        </>
      )}

      {timesteps.length > 0 && (
        <>
          <div className="section-h"><span className="k">Análisis</span><span className="rule" /></div>
          <ResultsTabs t={timesteps[tIdx] ?? null} H={p.H} />
        </>
      )}

      <footer className="foot">
        <span>SmartCityNet · Trabajo de Integración Curricular — Escuela Politécnica Nacional</span>
        <span className="mono">React + FastAPI</span>
      </footer>
    </div>
  );
}
