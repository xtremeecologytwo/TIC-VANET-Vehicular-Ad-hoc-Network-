import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { V2iTuple, V2vTuple, Multihop } from "../api/client";

type Tab = "v2i" | "v2v" | "mat" | "mh";

/* Rejilla binaria 0/1 (celda coloreada si =1), acotada para no saturar. */
function MatrixGrid({ rows, cols, data, tone = "accent", max = 36 }: {
  rows: string[]; cols: string[]; data: number[][]; tone?: "accent" | "ok" | "warn"; max?: number;
}) {
  const rr = rows.slice(0, max);
  const cc = cols.slice(0, max);
  return (
    <div className="matwrap">
      <table className={`mat ${tone}`}>
        <thead>
          <tr><th className="corner" />{cc.map((c, j) => (
            <th key={j} title={c}>{c.length > 6 ? c.slice(-4) : c}</th>
          ))}</tr>
        </thead>
        <tbody>
          {rr.map((r, i) => (
            <tr key={i}>
              <th title={r}>{r}</th>
              {cc.map((_, j) => <td key={j} className={data[i][j] ? "on" : ""} />)}
            </tr>
          ))}
        </tbody>
      </table>
      {(rows.length > max || cols.length > max) && (
        <div className="matnote mono">
          mostrando {Math.min(rows.length, max)}×{Math.min(cols.length, max)} de {rows.length}×{cols.length}
        </div>
      )}
    </div>
  );
}

/* Deja solo las columnas con al menos un 1 (para que B, con cientos de RSU,
   muestre únicamente las alcanzadas en el instante). */
function soloAlcanzadas(labels: string[], data: number[][]) {
  const keep = labels.map((_, j) => data.some((r) => r[j] === 1));
  return { cols: labels.filter((_, j) => keep[j]), data: data.map((r) => r.filter((_, j) => keep[j])) };
}

/* Opciones y selección para el visor de matrices multisalto. */
function matOptions(H: number) {
  const o: { v: string; label: string }[] = [];
  for (let h = 1; h <= H; h++) o.push({ v: `R${h}`, label: `R${h} — acumulada (≤${h} saltos)` });
  for (let h = 1; h <= H; h++) o.push({ v: `S${h}`, label: `S${h} — primera aparición (exact. ${h})` });
  o.push({ v: "D", label: `D — desconexión (1 = no conecta con ≤${H})` });
  return o;
}
function pickMatrix(mh: Multihop, sel: string): { data: number[][]; tone: "accent" | "ok" | "warn" } {
  if (sel === "D") return { data: mh.D, tone: "warn" };
  const h = parseInt(sel.slice(1), 10) - 1;
  return sel[0] === "R" ? { data: mh.R[h], tone: "accent" } : { data: mh.S[h], tone: "ok" };
}

export default function ResultsTabs({ t, H }: { t: number | null; H: number }) {
  const [tab, setTab] = useState<Tab>("v2i");
  const [v2i, setV2i] = useState<{ total: number; tuplas: V2iTuple[] } | null>(null);
  const [v2v, setV2v] = useState<{ total: number; tuplas: V2vTuple[] } | null>(null);
  const [mh, setMh] = useState<Multihop | null>(null);
  const [mhMat, setMhMat] = useState("");
  const [q, setQ] = useState("");   // filtro de texto para las tablas de tuplas
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { if (tab === "v2i" && !v2i) api.tuplesV2i().then(setV2i).catch((e) => setErr(e.message)); }, [tab, v2i]);
  useEffect(() => { if (tab === "v2v" && !v2v) api.tuplesV2v().then(setV2v).catch((e) => setErr(e.message)); }, [tab, v2v]);
  useEffect(() => {
    // Las matrices siguen a la línea de tiempo: se piden para el instante activo
    // (también mientras se reproduce, para ver qué matriz se usa en cada momento).
    if ((tab === "mat" || tab === "mh") && t != null) {
      setErr(null);
      api.multihop(t, H).then((r) => { setMh(r); setMhMat(`R${r.H}`); }).catch((e) => setErr(e.message));
    }
  }, [tab, t, H]);

  const B = mh ? soloAlcanzadas(mh.rsu_ids, mh.B) : null;

  return (
    <div className="results">
      <div className="rtabs">
        {([["v2i", "Tuplas V2I"], ["v2v", "Tuplas V2V"], ["mat", "Matrices A/B"], ["mh", "Multisalto"]] as [Tab, string][])
          .map(([id, label]) => (
            <button key={id} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>{label}</button>
          ))}
        {(tab === "mat" || tab === "mh") && t != null && <span className="rt-t mono">instante t={t}s · H={H}</span>}
      </div>

      {err && <div className="banner err">⚠ {err}</div>}

      {tab === "v2i" && (() => {
        const ql = q.trim().toLowerCase();
        const rows = (v2i?.tuplas ?? []).filter((r) => !ql ||
          r.vehiculo.toLowerCase().includes(ql) || String(r.rsu).toLowerCase().includes(ql) || String(r.t).includes(ql));
        return (
          <>
            <div className="filterbar">
              <input className="tsearch" placeholder="Filtrar por vehículo, RSU o t…" value={q} onChange={(e) => setQ(e.target.value)} />
              {v2i && <span className="matnote mono">{rows.length} de {v2i.total} (cargadas {v2i.tuplas.length})</span>}
            </div>
            <div className="tablewrap">
              <table className="dtable">
                <thead><tr><th>t (s)</th><th>Vehículo</th><th>RSU</th><th>Dist (m)</th></tr></thead>
                <tbody>{rows.map((r, i) => (
                  <tr key={i}><td className="mono">{r.t}</td><td>{r.vehiculo}</td><td className="mono">{r.rsu}</td><td className="mono">{r.distancia}</td></tr>
                ))}</tbody>
              </table>
            </div>
          </>
        );
      })()}

      {tab === "v2v" && (() => {
        const ql = q.trim().toLowerCase();
        const rows = (v2v?.tuplas ?? []).filter((r) => !ql ||
          r.vehiculo_i.toLowerCase().includes(ql) || r.vehiculo_j.toLowerCase().includes(ql) || String(r.t).includes(ql));
        return (
          <>
            <div className="filterbar">
              <input className="tsearch" placeholder="Filtrar por vehículo o t…" value={q} onChange={(e) => setQ(e.target.value)} />
              {v2v && <span className="matnote mono">{rows.length} de {v2v.total} (cargadas {v2v.tuplas.length})</span>}
            </div>
            <div className="tablewrap">
              <table className="dtable">
                <thead><tr><th>t (s)</th><th>Vehículo i</th><th>Vehículo j</th><th>Dist (m)</th></tr></thead>
                <tbody>{rows.map((r, i) => (
                  <tr key={i}><td className="mono">{r.t}</td><td>{r.vehiculo_i}</td><td>{r.vehiculo_j}</td><td className="mono">{r.distancia}</td></tr>
                ))}</tbody>
              </table>
            </div>
          </>
        );
      })()}

      {tab === "mat" && (mh ? (
        mh.vehiculos.length === 0 ? <div className="empty mono">Sin vehículos activos en t={t}s.</div> : (
          <div className="matgrid2">
            <div><div className="matlab">A — vehículo × vehículo (V2V)</div>
              <MatrixGrid rows={mh.vehiculos} cols={mh.vehiculos} data={mh.A} tone="accent" /></div>
            <div><div className="matlab">B — vehículo × RSU alcanzada (V2I)</div>
              {B && B.cols.length ? <MatrixGrid rows={mh.vehiculos} cols={B.cols} data={B.data} tone="ok" />
                : <div className="empty mono">Ningún RSU directo en este instante.</div>}</div>
          </div>
        )
      ) : <div className="empty mono">Cargando…</div>)}

      {tab === "mh" && (mh ? (
        mh.vehiculos.length === 0 ? <div className="empty mono">Sin vehículos activos en t={t}s.</div> : (
          <div className="tablewrap">
            <table className="dtable">
              <thead><tr><th>Saltos ≤ h</th><th>Pares V→RSU alcanzables</th><th>Vehículos con ≥1 RSU</th><th>Pares nuevos (exact. h)</th></tr></thead>
              <tbody>{mh.resumen.por_salto.map((p) => (
                <tr key={p.h}><td className="mono">{p.h}</td><td className="mono">{p.pares_acumulados}</td><td className="mono">{p.vehiculos_conectados}</td><td className="mono">{p.pares_nuevos}</td></tr>
              ))}</tbody>
            </table>
            <div className={`mh-note ${mh.resumen.vehiculos_desconectados ? "warn" : "ok"} mono`}>
              {mh.resumen.vehiculos_desconectados
                ? `⚠ ${mh.resumen.vehiculos_desconectados} vehículo(s) sin RSU ni con ${H} saltos: ${mh.resumen.ids_desconectados.join(", ")}`
                : `✓ Todos los ${mh.resumen.n_vehiculos} vehículos alcanzan un RSU con ≤ ${H} saltos.`}
            </div>

            {mhMat && (() => {
              const pk = pickMatrix(mh, mhMat);
              const flt = soloAlcanzadas(mh.rsu_ids, pk.data);
              return (
                <div className="mh-mat">
                  <div className="mh-mat-hd">
                    <span className="matlab">Matriz del instante (vehículo × RSU)</span>
                    <select value={mhMat} onChange={(e) => setMhMat(e.target.value)}>
                      {matOptions(mh.H).map((o) => <option key={o.v} value={o.v}>{o.label}</option>)}
                    </select>
                  </div>
                  {flt.cols.length
                    ? <MatrixGrid rows={mh.vehiculos} cols={flt.cols} data={flt.data} tone={pk.tone} />
                    : <div className="empty mono">Matriz vacía (ningún 1) en este instante.</div>}
                </div>
              );
            })()}
          </div>
        )
      ) : <div className="empty mono">Cargando…</div>)}
    </div>
  );
}
