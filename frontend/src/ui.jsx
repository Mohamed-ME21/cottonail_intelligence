import { createContext, useContext, useEffect, useState, useCallback } from "react";
import {
  Area, Bar, CartesianGrid, Cell, ComposedChart, Line, Pie, PieChart, ResponsiveContainer,
  Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import { AlertTriangle, Info, RefreshCw } from "lucide-react";

export const C = { purple: "#6D4AFF", soft: "#9B83FF", lav: "#DCD3FF", navy: "#12284C", blue: "#2F6FDE", pink: "#E96FC6", green: "#22B07D", amber: "#F5A524" };
export const PALETTE = [C.purple, C.blue, C.pink, C.soft, C.green, C.amber];

/* ------------------------------------------------------------ language */
export const Lang = createContext({ lang: "en", tr: (en) => en });
export const useT = () => useContext(Lang).tr;
export const useLang = () => useContext(Lang).lang;

/* ----------------------------------------------------------- formatters */
export const n = (v, d = 0) => {
  const x = Number(v);
  return Number.isFinite(x) ? x.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: 0 }) : "—";
};
export const compact = (v, d = 1) => {
  const x = Number(v);
  if (!Number.isFinite(x)) return "—";
  const a = Math.abs(x);
  if (a >= 1e9) return `${(x / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${(x / 1e6).toFixed(d)}M`;
  if (a >= 1e3) return `${(x / 1e3).toFixed(d)}K`;
  return n(x, d > 0 && a < 100 ? 1 : 0);
};
export const egp = (v) => (Number.isFinite(Number(v)) ? `EGP ${compact(v)}` : "—");
export const usd = (v) => (Number.isFinite(Number(v)) ? `USD ${compact(v)}` : "—");
export const pct = (v, d = 1) => (Number.isFinite(Number(v)) ? `${Number(v).toFixed(d)}%` : "—");

/* ------------------------------------------------------------- data hook */
const cache = new Map();
export function useApi(url) {
  const { filters } = useContext(Lang);
  const query = new URLSearchParams();
  if (filters) Object.entries(filters).forEach(([key, value]) => {
    if (Array.isArray(value)) value.forEach((item) => item && query.append(key, item));
    else if (value) query.set(key, value);
  });
  const requestUrl = query.toString() ? `${url}${url.includes("?") ? "&" : "?"}${query}` : url;
  const [state, setState] = useState(() => ({ data: cache.get(requestUrl) ?? null, error: "", loading: !cache.has(requestUrl) }));
  const load = useCallback((force = false) => {
    if (!force && cache.has(requestUrl)) { setState({ data: cache.get(requestUrl), error: "", loading: false }); return; }
    setState((s) => ({ ...s, loading: true, error: "" }));
    fetch(requestUrl).then((r) => { if (!r.ok) throw new Error(`${requestUrl} → ${r.status}`); return r.json(); })
      .then((data) => { cache.set(requestUrl, data); setState({ data, error: "", loading: false }); })
      .catch((e) => setState({ data: null, error: e.message, loading: false }));
  }, [requestUrl]);
  useEffect(() => { load(); }, [load]);
  return { ...state, reload: () => load(true) };
}
export const clearCache = () => cache.clear();

/* -------------------------------------------------------------- layout */
export function Page({ urls, children }) {
  const tr = useT();
  const res = urls.map((u) => useApi(u)); // urls array length is constant per page
  const err = res.find((r) => r.error);
  const wait = res.some((r) => r.loading && !r.data);
  if (err) return (
    <Notice tone="bad">
      <b>{tr("Could not load data.", "تعذر تحميل البيانات.")}</b> {err.error}{" "}
      <button className="link" onClick={() => res.forEach((r) => r.reload())}><RefreshCw size={14} /> {tr("Retry", "إعادة المحاولة")}</button>
    </Notice>
  );
  if (wait) return <div className="skeleton-grid" aria-busy="true">{Array.from({ length: 6 }, (_, i) => <div key={i} className="glass skeleton" />)}</div>;
  return <div className="page-body">{children(...res.map((r) => r.data))}</div>;
}

export const Notice = ({ tone = "info", children }) => (
  <div className={`notice ${tone}`} role={tone === "bad" ? "alert" : "note"}>
    {tone === "info" ? <Info size={18} /> : <AlertTriangle size={18} />}<div>{children}</div>
  </div>
);

export const Card = ({ title, sub, span = 1, children, className = "" }) => (
  <section className={`glass card span-${span} ${className}`}>
    {(title || sub) && <header className="card-head"><h2>{title}</h2>{sub && <p>{sub}</p>}</header>}
    {children}
  </section>
);
export const Grid = ({ cols = 2, children }) => <div className={`grid g${cols}`}>{children}</div>;

/* -------------------------------------------------------------- KPIs */
function useCount(target) {
  const [v, setV] = useState(0);
  useEffect(() => {
    const t = Number(target);
    if (!Number.isFinite(t) || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) { setV(t); return; }
    let raf, t0;
    const step = (now) => {
      t0 ??= now;
      const p = Math.min((now - t0) / 900, 1);
      setV(t * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target]);
  return v;
}
export function Kpi({ label, value, fmt = compact, note, icon: Icon, tone = "purple", delta }) {
  const shown = useCount(value);
  return (
    <article className="glass kpi">
      <div className="kpi-top"><span>{label}</span>{Icon && <i className={`ico ${tone}`}><Icon size={18} /></i>}</div>
      <strong>{value == null ? "—" : fmt(shown)}</strong>
      <small>{delta != null && Number.isFinite(Number(delta)) && <em className={delta >= 0 ? "up" : "down"}>{delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}%</em>} {note}</small>
    </article>
  );
}
export const Kpis = ({ items }) => <div className="kpis" style={{ "--n": items.length }}>{items.map((k) => <Kpi key={k.label} {...k} />)}</div>;

/* ------------------------------------------------------------ bar list */
export function BarList({ rows, fmt = compact, color = C.purple, max }) {
  if (!rows?.length) return <Empty />;
  const top = max ?? Math.max(...rows.map((r) => Math.abs(r.value)), 1);
  return (
    <div className="barlist">
      {rows.map((r, i) => (
        <div className="bl-row" key={`${r.label}-${i}`}>
          <span className="bl-label" dir="auto" title={r.label}>{r.label}</span>
          <div className="bl-track"><div className="bl-fill" style={{ width: `${Math.max(2, (Math.abs(r.value) / top) * 100)}%`, background: r.color || color, animationDelay: `${i * 40}ms` }} /></div>
          <span className="bl-val">{fmt(r.value)}{r.note && <small>{r.note}</small>}</span>
        </div>
      ))}
    </div>
  );
}

export const Empty = () => <div className="empty">—</div>;

/* -------------------------------------------------------------- charts */
const tick = { fontSize: 11, fill: "#6B6F8F" };
function Tip({ active, payload, label, fmts }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tip"><b dir="auto">{label}</b>
      {payload.filter((p) => p.value != null).map((p, i) => <div key={i}><i style={{ background: p.color || p.stroke || p.fill }} />{p.name}: <strong>{(fmts?.[p.dataKey] || compact)(p.value)}</strong></div>)}
    </div>
  );
}
/** series: [{key,name,type:'area'|'line'|'bar',color,axis:'l'|'r',fmt}] */
export function Trend({ data, x = "year_month", series, height = 260, fmtL = compact, fmtR = compact, dual = false }) {
  const fmts = Object.fromEntries(series.map((s) => [s.key, s.fmt || (s.axis === "r" ? fmtR : fmtL)]));
  const step = Math.max(0, Math.ceil((data?.length || 1) / 8) - 1);
  return (
    <div className="chart" dir="ltr" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: dual ? 4 : 8, left: 0, bottom: 0 }}>
          <defs>{series.map((s) => <linearGradient key={s.key} id={`g-${s.key}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={s.color} stopOpacity={0.35} /><stop offset="100%" stopColor={s.color} stopOpacity={0} /></linearGradient>)}</defs>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(18,40,76,.08)" />
          <XAxis dataKey={x} tick={tick} interval={step} tickLine={false} axisLine={false} />
          <YAxis yAxisId="l" tick={tick} tickFormatter={(v) => fmtL(v)} width={52} tickLine={false} axisLine={false} />
          {dual && <YAxis yAxisId="r" orientation="right" tick={tick} tickFormatter={(v) => fmtR(v)} width={48} tickLine={false} axisLine={false} />}
          <Tooltip content={<Tip fmts={fmts} />} />
          {series.map((s) => {
            const common = { key: s.key, dataKey: s.key, name: s.name, yAxisId: s.axis === "r" ? "r" : "l", stroke: s.color, isAnimationActive: true, animationDuration: 900 };
            if (s.type === "bar") return <Bar {...common} fill={s.color} radius={[6, 6, 0, 0]} />;
            if (s.type === "line") return <Line {...common} type="monotone" strokeWidth={2.4} dot={false} />;
            return <Area {...common} type="monotone" strokeWidth={2.4} fill={`url(#g-${s.key})`} />;
          })}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function Donut({ data, nameKey, valueKey, fmt = compact, height = 220 }) {
  if (!data?.length) return <Empty />;
  const total = data.reduce((s, d) => s + Number(d[valueKey] || 0), 0);
  return (
    <div className="donut">
      <div className="chart" dir="ltr" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey={valueKey} nameKey={nameKey} innerRadius="58%" outerRadius="88%" paddingAngle={2} stroke="none" animationDuration={900}>
              {data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
            </Pie>
            <Tooltip formatter={(v) => fmt(v)} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="legend">
        {data.map((d, i) => <li key={i}><i style={{ background: PALETTE[i % PALETTE.length] }} /><span dir="auto">{d[nameKey]}</span><b>{total ? ((d[valueKey] / total) * 100).toFixed(0) : 0}%</b></li>)}
      </ul>
    </div>
  );
}

export function Dots({ data, xKey, yKey, zKey, nameKey, xFmt = compact, yFmt = (v) => pct(v), xLabel, yLabel, height = 280 }) {
  return (
    <div className="chart" dir="ltr" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 12, left: 0, bottom: 16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(18,40,76,.08)" />
          <XAxis dataKey={xKey} type="number" name={xLabel} tick={tick} tickFormatter={(v) => xFmt(v)} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
          <YAxis dataKey={yKey} type="number" name={yLabel} tick={tick} tickFormatter={(v) => yFmt(v)} width={48} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
          {zKey && <ZAxis dataKey={zKey} range={[50, 280]} />}
          <Tooltip cursor={{ strokeDasharray: "3 3" }} content={({ active, payload }) => active && payload?.length ? (
            <div className="tip"><b dir="auto">{payload[0].payload[nameKey]}</b><div>{xLabel}: <strong>{xFmt(payload[0].payload[xKey])}</strong></div><div>{yLabel}: <strong>{yFmt(payload[0].payload[yKey])}</strong></div></div>) : null} />
          <Scatter data={data} fill={C.purple} fillOpacity={0.7} animationDuration={900} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

/* --------------------------------------------------------------- heat map */
export function Heat({ rows, rowKey, colKey, valKey, fmt = (v) => pct(v), rowOrder, colOrder }) {
  const rs = rowOrder || [...new Set(rows.map((r) => r[rowKey]))];
  const cs = colOrder || [...new Set(rows.map((r) => r[colKey]))];
  const map = new Map(rows.map((r) => [`${r[rowKey]}|${r[colKey]}`, r[valKey]]));
  const vals = [...map.values()].filter((v) => v != null);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  return (
    <div className="heat" style={{ gridTemplateColumns: `minmax(96px,1.3fr) repeat(${cs.length}, minmax(44px,1fr))` }} dir="ltr">
      <span />{cs.map((c) => <b key={c} className="heat-h" dir="auto">{c}</b>)}
      {rs.map((r) => (
        <Row key={r} label={r} cs={cs} get={(c) => map.get(`${r}|${c}`)} lo={lo} hi={hi} fmt={fmt} />
      ))}
    </div>
  );
}
function Row({ label, cs, get, lo, hi, fmt }) {
  return (
    <>
      <span className="heat-r" dir="auto">{label}</span>
      {cs.map((c) => {
        const v = get(c), t = v == null || hi === lo ? 0 : (v - lo) / (hi - lo);
        return <span key={c} className="heat-c" title={v == null ? "" : fmt(v)} style={{ background: v == null ? "transparent" : `rgba(109,74,255,${0.1 + t * 0.75})`, color: t > 0.55 ? "#fff" : C.navy }}>{v == null ? "" : fmt(v)}</span>;
      })}
    </>
  );
}

/* ------------------------------------------------------------------ table */
export function Table({ cols, rows, max = 10 }) {
  const [all, setAll] = useState(false);
  const tr = useT();
  if (!rows?.length) return <Empty />;
  const shown = all ? rows : rows.slice(0, max);
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{cols.map((c) => <th key={c.k} className={c.num ? "num" : ""}>{c.label}</th>)}</tr></thead>
        <tbody>{shown.map((r, i) => <tr key={i}>{cols.map((c) => <td key={c.k} className={c.num ? "num" : ""} dir={c.num ? "ltr" : "auto"}>{c.r ? c.r(r[c.k]) : (r[c.k] ?? "—")}</td>)}</tr>)}</tbody>
      </table>
      {rows.length > max && <button className="link more" onClick={() => setAll(!all)}>{all ? tr("Show less", "عرض أقل") : tr(`Show all ${rows.length}`, `عرض الكل (${rows.length})`)}</button>}
    </div>
  );
}
