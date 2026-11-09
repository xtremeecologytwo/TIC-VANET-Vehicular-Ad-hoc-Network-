import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { FisicaOpciones, FisicaResumen, FisicaEtiqueta } from "../api/client";

/**
 * Panel "Capa física · IEEE 802.11p".
 *
 * Aquí se decide con qué NÚMEROS físicos corre el resto de la consola. Hasta
 * ahora el radio de la OBU (300 m), la penalización por salto (P[h] = h) y la
 * capacidad de una RSU (300) eran constantes sin justificación. Las notas
 * técnicas del tutor las derivan de un modelo publicado:
 *
 *   - radio       ← r80 / r90: la mayor distancia a la que un paquete llega
 *                   con probabilidad ≥ 0,8 / 0,9 (Monte Carlo de propagación,
 *                   fading, interferente y PER).
 *   - P[h]        ← Γ_h = 1 / P(éxito de una ruta de h saltos).
 *   - Cap, L      ← α·C₀(R, L): capacidad agregada de la RSU tras los
 *                   overheads MAC, y una carga por vehículo en la misma unidad.
 *
 * El panel NO cambia nada por sí solo: muestra la curva y los valores, y solo
 * cuando se pulsa "aplicar" se copian al slider de M2 o al cuerpo de M3. Así
 * los valores clásicos siguen disponibles para comparar.
 */

type ModoP = "gamma" | "extra";

export interface ModeloFisico {
  /** P[1..6]; App recorta a H antes de enviarlo. */
  P: number[];
  cap_kbps: number;
  carga_kbps: number;
  etiqueta: FisicaEtiqueta;
}

const ESC_NOMBRE: Record<string, string> = {
  noise_only: "solo ruido",
  with_interference: "con interferente",
};

/**
 * Curva P(éxito) frente a distancia, en SVG puro (sin librería de gráficos:
 * es una sola línea y dos umbrales). Las marcas verticales son r80 y r90; la
 * elegida se pinta más gruesa.
 */
function Curva({ res }: { res: FisicaResumen }) {
  const W = 620, H = 220, L = 42, R = 12, T = 12, B = 30;
  const x = (d: number) => L + (d / 1000) * (W - L - R);
  const y = (p: number) => T + (1 - p) * (H - T - B);
  const path = res.curva.map((c, i) => `${i ? "L" : "M"}${x(c.distance_m).toFixed(1)},${y(c.success_probability).toFixed(1)}`).join(" ");
  const marcas = [["r80", res.radios.r80_m], ["r90", res.radios.r90_m]] as const;
  return (
    <svg className="fis-chart" viewBox={`0 0 ${W} ${H}`} role="img"
      aria-label="Probabilidad de recepción frente a distancia">
      {[0, 0.25, 0.5, 0.75, 1].map((p) => (
        <g key={p}>
          <line className="grid" x1={L} x2={W - R} y1={y(p)} y2={y(p)} />
          <text x={L - 6} y={y(p) + 3} textAnchor="end">{p.toFixed(2)}</text>
        </g>
      ))}
      {[0, 200, 400, 600, 800, 1000].map((d) => (
        <text key={d} x={x(d)} y={H - 10} textAnchor="middle">{d} m</text>
      ))}
      {/* umbrales 0,8 y 0,9: por encima de ellos se define el radio */}
      {[0.8, 0.9].map((p) => <line key={p} className="lvl" x1={L} x2={W - R} y1={y(p)} y2={y(p)} />)}
      <path className="curve" d={path} />
      {marcas.map(([nombre, r]) => r != null && (
        <g key={nombre}>
          <line className="rad" x1={x(r)} x2={x(r)} y1={T} y2={H - B}
            strokeWidth={nombre === res.criterio ? 2.5 : 1} />
          <text x={x(r) + 4} y={T + 11}>{nombre} = {r} m</text>
        </g>
      ))}
    </svg>
  );
}

export default function CapaFisica({ H, busy, aplicado, onAplicarRadio, onAplicarModelo, onQuitar }: {
  H: number;
  busy: boolean;
  /** Qué está aplicado ahora mismo (para mostrarlo y para el botón de quitar). */
  aplicado: { radio: FisicaEtiqueta | null; modelo: ModeloFisico | null };
  onAplicarRadio: (radio_m: number, etiqueta: FisicaEtiqueta) => void;
  onAplicarModelo: (m: ModeloFisico) => void;
  onQuitar: () => void;
}) {
  const [op, setOp] = useState<FisicaOpciones | null>(null);
  const [q, setQ] = useState({
    rate: 6, packet_bytes: 1000, escenario: "with_interference", criterio: "r90",
    alfa: 0.8, carga_kbps: 80, semilla: "" as string, n: "" as string,
  });
  const [modoP, setModoP] = useState<ModoP>("gamma");
  const [res, setRes] = useState<FisicaResumen | null>(null);
  const [cargando, setCargando] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Opciones (tasas, tamaños, α recomendados) y valores por defecto: del backend,
  // para que la web no duplique los números de las notas del tutor.
  useEffect(() => {
    api.fisicaOpciones().then((o) => {
      setOp(o);
      setQ((s) => ({ ...s, rate: o.por_defecto.rate_mbps, packet_bytes: o.por_defecto.packet_bytes,
        escenario: o.por_defecto.escenario, criterio: o.por_defecto.criterio,
        alfa: o.por_defecto.alfa, carga_kbps: o.por_defecto.carga_kbps }));
    }).catch((e: Error) => setErr(e.message));
  }, []);

  // Cada cambio de parámetro pide el resumen. `vivo` evita que una respuesta
  // lenta (Monte Carlo en vivo) pise a una más reciente.
  useEffect(() => {
    if (!op) return;
    let vivo = true;
    setCargando(true); setErr(null);
    api.fisicaResumen({
      rate: q.rate, packet_bytes: q.packet_bytes, escenario: q.escenario, criterio: q.criterio,
      alfa: q.alfa, carga_kbps: q.carga_kbps, H: op.h_max,
      semilla: q.semilla.trim() === "" ? null : Number(q.semilla),
      n: q.n.trim() === "" ? null : Number(q.n),
    }).then((r) => { if (vivo) setRes(r); })
      .catch((e: Error) => { if (vivo) { setRes(null); setErr(e.message); } })
      .finally(() => { if (vivo) setCargando(false); });
    return () => { vivo = false; };
  }, [op, q.rate, q.packet_bytes, q.escenario, q.criterio, q.alfa, q.carga_kbps, q.semilla, q.n]);

  const etiqueta = (r: FisicaResumen): FisicaEtiqueta => ({
    rate_mbps: r.rate_mbps, packet_bytes: r.packet_bytes, escenario: r.escenario,
    criterio: r.criterio, alfa: r.alfa, fuente: r.fuente.alcance, resumen: r.etiqueta,
  });

  const P = res ? (modoP === "gamma" ? res.modelo.P_gamma : res.modelo.P_extra) : [];
  const sel = (k: keyof typeof q) => (e: React.ChangeEvent<HTMLSelectElement | HTMLInputElement>) =>
    setQ((s) => ({ ...s, [k]: e.target.type === "number" || e.target.tagName === "SELECT" && !isNaN(Number(e.target.value)) ? Number(e.target.value) : e.target.value }));

  return (
    <div className="panel">
      <div className="panel-hd">
        <span className="ttl">Capa física · IEEE 802.11p (notas del tutor)</span>
        <span className="hd-right">
          {cargando && <span className="readout mono">calculando…</span>}
          {(aplicado.radio || aplicado.modelo) && (
            <button className="chip-btn on" onClick={onQuitar} disabled={busy}>✕ Volver a valores clásicos</button>
          )}
        </span>
      </div>

      <div className="fis-ctl">
        <label>Tasa PHY
          <select value={q.rate} onChange={(e) => setQ((s) => ({ ...s, rate: Number(e.target.value) }))}>
            {(op?.tasas_mbps ?? [6]).map((t) => <option key={t} value={t}>{t} Mb/s</option>)}
          </select>
        </label>
        <label>Paquete
          <select value={q.packet_bytes} onChange={(e) => setQ((s) => ({ ...s, packet_bytes: Number(e.target.value) }))}>
            {(op?.tamanos_bytes ?? [1000]).map((b) => <option key={b} value={b}>{b} B</option>)}
          </select>
        </label>
        <label>Escenario
          <select value={q.escenario} onChange={(e) => setQ((s) => ({ ...s, escenario: e.target.value }))}>
            {(op?.escenarios ?? ["with_interference"]).map((e) => <option key={e} value={e}>{ESC_NOMBRE[e] ?? e}</option>)}
          </select>
        </label>
        <label>Criterio de radio
          <select value={q.criterio} onChange={(e) => setQ((s) => ({ ...s, criterio: e.target.value }))}>
            {(op?.criterios ?? ["r90"]).map((c) => <option key={c} value={c}>{c} — P(éxito) ≥ {c === "r80" ? "80" : "90"} %</option>)}
          </select>
        </label>
        <label>α (contienda)
          <select value={q.alfa} onChange={(e) => setQ((s) => ({ ...s, alfa: Number(e.target.value) }))}>
            {Object.entries(op?.alfa ?? { base: 0.8 }).map(([k, v]) => <option key={k} value={v}>{v} — {k.replace("_", " ")}</option>)}
          </select>
        </label>
        <label>Carga por vehículo (kb/s)
          <input type="number" min={1} max={10000} value={q.carga_kbps} onChange={sel("carga_kbps")} />
        </label>
        <label title="Vacío = usar los CSV oficiales del tutor. Con valor = recalcular con su código y esta semilla.">
          Semilla (opcional)
          <input type="text" placeholder={op ? String(op.semilla_tutor) : ""} value={q.semilla}
            onChange={(e) => setQ((s) => ({ ...s, semilla: e.target.value }))} />
        </label>
        <label title="Paquetes por distancia y rutas por H. Vacío = 5000 (lo del tutor).">
          Muestras (opcional)
          <input type="text" placeholder={op ? String(op.muestras_tutor) : ""} value={q.n}
            onChange={(e) => setQ((s) => ({ ...s, n: e.target.value }))} />
        </label>
      </div>

      {err && <div className="banner err" style={{ margin: 12 }}>⚠ {err}</div>}

      {res && (
        <div className="fis">
          <div>
            <Curva res={res} />
            <div className="fis-src">
              alcance: {res.fuente.alcance} · multisalto: {res.fuente.multisalto}
            </div>
            <div className="fis-kv">
              <div><div className="lab">Radio elegido ({res.criterio})</div>
                <div className="val">{res.radio_elegido_m} <small>m</small></div></div>
              <div><div className="lab">r80 / r90</div>
                <div className="val">{res.radios.r80_m ?? "—"} / {res.radios.r90_m ?? "—"} <small>m</small></div></div>
              <div><div className="lab">Radio por sensibilidad</div>
                <div className="val">{res.radios.sensitivity_radius_m?.toFixed(0)} <small>m (potencia media)</small></div></div>
              <div><div className="lab">C₀ → α·C₀</div>
                <div className="val">{res.capacidad.c0_mbps.toFixed(2)} → {res.capacidad.c_agg_mbps.toFixed(2)} <small>Mb/s</small></div></div>
            </div>
            <div className="fis-apply">
              <button className="cta ghost" disabled={busy}
                onClick={() => onAplicarRadio(res.radio_elegido_m, etiqueta(res))}>
                ◎ Usar {res.radio_elegido_m} m como radio OBU (M2)
              </button>
            </div>
          </div>

          <div>
            <div className="tablewrap" style={{ maxHeight: 260 }}>
              <table className="dtable">
                <thead><tr><th>H</th><th>P(ruta)</th><th>Γ_H</th><th>P[h] a usar</th></tr></thead>
                <tbody>
                  {res.multisalto.map((f, i) => (
                    <tr key={f.n_hops} style={{ opacity: f.n_hops <= H ? 1 : 0.45 }}>
                      <td className="mono">{f.n_hops}</td>
                      <td className="mono">{f.success_probability?.toFixed(4) ?? "—"}</td>
                      <td className="mono">{f.penalty_factor?.toFixed(4) ?? "—"}</td>
                      <td className="mono">{P[i]?.toFixed(4) ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="matnote mono">
              saltos de longitud U(10, {res.radio_elegido_m}) m, siempre con interferente ·
              filas atenuadas: más allá de H = {H}
            </div>
            {/* Pregunta 4 al tutor: ¿P[h] = Γ_h o Γ_h − 1? Se dejan las dos. */}
            <div className="fis-ctl" style={{ borderTop: "1px solid var(--line)", borderBottom: 0 }}>
              <label>P[h] =
                <select value={modoP} onChange={(e) => setModoP(e.target.value as ModoP)}>
                  <option value="gamma">Γ_h (factor de retransmisión)</option>
                  <option value="extra">Γ_h − 1 (solo retransmisiones extra)</option>
                </select>
              </label>
              <label>Cap[r] · L[s][v]
                <span className="mono" style={{ fontSize: 12.5, color: "var(--ink)" }}>
                  {(res.modelo.cap_kbps).toFixed(0)} · {res.modelo.carga_kbps} kb/s
                </span>
              </label>
            </div>
            <div className="fis-apply">
              <button className="cta ghost" disabled={busy}
                onClick={() => onAplicarModelo({ P, cap_kbps: res.modelo.cap_kbps,
                  carga_kbps: res.modelo.carga_kbps, etiqueta: etiqueta(res) })}>
                ◉ Usar Γ_h y capacidad en la optimización (M3)
              </button>
            </div>
            <p className="hint" style={{ padding: "0 15px 12px" }}>
              Con el objetivo lexicográfico, P[h] solo desempata entre despliegues que ya tienen
              cobertura máxima con el mínimo de RSU. Cap y L sí restringen (Ec. 4).
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
