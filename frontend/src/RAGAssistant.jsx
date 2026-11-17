import { useCallback, useContext, useEffect, useRef, useState } from "react";
import { AlertTriangle, Bot, Code2, Database, MessageCircle, Send, Sparkles, Square, X } from "lucide-react";
import { Lang } from "./ui.jsx";
import "./rag-extra.css";

const TIMEOUT_MS = 200_000;

const TEXT = {
  en: {
    title: "Ask Cottonil data", intro: "Numbers come from database queries on your CSV data; the model only explains them.",
    placeholder: "Ask about company data...", busy: "Searching and querying...", stop: "Stop", sources: "Sources", sql: "SQL used",
    rows: "Result table", filters: "Filters applied", retry: "Check again", offline: "Cannot reach the backend. Make sure uvicorn is running and that the port matches vite.config.js.",
    failed: "Request failed", cancelled: "Request cancelled.", timeout: "The request took too long and was cancelled.",
    prompts: ["Analyze monthly sales", "Top 5 products by net sales", "Which governorates sell the most?", "What are the main return reasons?"],
  },
  ar: {
    title: "اسأل بيانات Cottonil", intro: "الأرقام تأتي من استعلامات على ملفات البيانات، والنموذج يشرحها فقط.",
    placeholder: "اكتب سؤالك عن البيانات...", busy: "جاري البحث والاستعلام...", stop: "إيقاف", sources: "المصادر", sql: "الاستعلام المستخدم",
    rows: "جدول النتائج", filters: "الفلاتر المطبقة", retry: "إعادة الفحص", offline: "تعذر الوصول للخادم. تأكد من تشغيل uvicorn وأن المنفذ يطابق vite.config.js.",
    failed: "فشل الطلب", cancelled: "تم إلغاء الطلب.", timeout: "استغرق الطلب وقتًا طويلًا وتم إلغاؤه.",
    prompts: ["حلل المبيعات شهريًا", "أعلى 5 منتجات من حيث صافي المبيعات", "أي المحافظات الأعلى مبيعًا؟", "ما أسباب المرتجعات الرئيسية؟"],
  },
};

/* ------------------------------------------------------------ rendering */
function Inline({ text }) {
  return <>{String(text).split(/(\*\*[^*]+\*\*)/g).map((p, i) => (p.startsWith("**") && p.endsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : <span key={i}>{p}</span>))}</>;
}

function Markdown({ text = "" }) {
  const blocks = [];
  let list = [];
  const flush = () => { if (list.length) { blocks.push(<ul key={`l${blocks.length}`}>{list.map((x, i) => <li key={i}><Inline text={x} /></li>)}</ul>); list = []; } };
  String(text).replace(/\r/g, "").split("\n").forEach((raw, i) => {
    const line = raw.trim();
    const item = line.match(/^(?:[-*•]|\d+[.)])\s+(.+)$/);
    if (item) { list.push(item[1]); return; }
    flush();
    if (!line) return;
    const head = line.match(/^#{1,4}\s+(.+)$/);
    blocks.push(head ? <h4 key={i}><Inline text={head[1]} /></h4> : <p key={i}><Inline text={line} /></p>);
  });
  flush();
  return <div className="rag-md">{blocks}</div>;
}

const fmt = (v) => (typeof v === "number" ? v.toLocaleString("en-US", { maximumFractionDigits: 2 }) : v == null ? "—" : String(v));

function ResultTable({ result }) {
  if (!result?.columns?.length) return null;
  return (
    <div className="rag-table-wrap" dir="ltr">
      <table className="rag-table">
        <thead><tr>{result.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>{result.rows.slice(0, 10).map((r, i) => <tr key={i}>{result.columns.map((c) => <td key={c} className={typeof r[c] === "number" ? "n" : ""} dir="auto">{fmt(r[c])}</td>)}</tr>)}</tbody>
      </table>
      {result.row_count > 10 && <small>{result.row_count.toLocaleString("en-US")} rows</small>}
    </div>
  );
}

/* ---------------------------------------------------------------- hooks */
function useStatus() {
  const [state, setState] = useState({ loading: true });
  const check = useCallback(() => {
    setState({ loading: true });
    fetch("/api/rag/status")
      .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then((s) => setState({ loading: false, ...s }))
      .catch(() => setState({ loading: false, unreachable: true }));
  }, []);
  useEffect(check, [check]);
  return [state, check];
}

const hasFilters = (f = {}) => Object.values(f).some((v) => (Array.isArray(v) ? v.length : Boolean(v)));

/* ---------------------------------------------------------------- panel */
function Panel({ floating = false, onClose }) {
  const ctx = useContext(Lang);
  const lang = ctx.lang === "ar" ? "ar" : "en";
  const filters = ctx.filters ?? {};
  const t = TEXT[lang];
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, recheck] = useStatus();
  const abortRef = useRef(null);
  const bottomRef = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView?.({ block: "end" }); }, [messages, busy]);
  useEffect(() => () => abortRef.current?.abort(), []);

  async function send(value = input) {
    const q = value.trim();
    if (!q || busy) return;
    // Error bubbles are UI-only: they must never be sent back to the model as conversation history.
    const history = messages.filter((m) => !m.error).slice(-6).map(({ role, content }) => ({ role, content }));
    setMessages((m) => [...m, { role: "user", content: q }]);
    setInput("");
    setBusy(true);
    const controller = new AbortController();
    abortRef.current = controller;
    const timer = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
    try {
      const res = await fetch("/api/rag/ask", {
        method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.signal,
        body: JSON.stringify({ message: q, history, page: window.location.hash.slice(1) || "overview", filters }),
      });
      const raw = await res.text();
      let data = {};
      try { data = JSON.parse(raw); } catch { data = { detail: raw.slice(0, 300) }; }
      if (!res.ok) {
        const d = data.detail;
        throw new Error(Array.isArray(d) ? d.map((x) => `${(x.loc || []).join(".")}: ${x.msg}`).join(" | ") : typeof d === "string" ? d : `HTTP ${res.status}`);
      }
      setMessages((m) => [...m, { role: "assistant", content: data.answer || "—", sources: data.sources || [], sql: data.sql, result: data.sql_result, failed: data.mode === "sql_failed" }]);
    } catch (e) {
      const reason = controller.signal.aborted ? (controller.signal.reason === "timeout" ? t.timeout : t.cancelled) : `${t.failed}: ${e.message}`;
      setMessages((m) => [...m, { role: "assistant", content: reason, error: true }]);
      recheck();
    } finally {
      clearTimeout(timer);
      abortRef.current = null;
      setBusy(false);
    }
  }

  const problem = status.unreachable ? t.offline : status.hint;
  return (
    <section className={`rag-panel ${floating ? "rag-floating" : ""}`} dir={lang === "ar" ? "rtl" : "ltr"}>
      <header>
        <span className="rag-avatar"><Bot size={19} /></span>
        <div><b>Cottonil RAG Agent</b><small><Database size={12} /> {status.model || "AI model"} · SQL + Retrieval</small></div>
        {floating && <button onClick={onClose} aria-label="Close"><X size={18} /></button>}
      </header>

      {!status.loading && problem && (
        <div className="rag-status" role="alert"><AlertTriangle size={16} /><span>{problem}</span><button onClick={recheck}>{t.retry}</button></div>
      )}

      <div className="rag-messages" aria-live="polite">
        {!messages.length && (
          <div className="rag-welcome">
            <Sparkles size={26} /><h3>{t.title}</h3><p>{t.intro}</p>
            <div className="rag-prompts">{t.prompts.map((p) => <button key={p} onClick={() => send(p)} disabled={busy}>{p}</button>)}</div>
          </div>
        )}
        {messages.map((m, i) => (
          <article key={i} className={`rag-message ${m.role} ${m.error || m.failed ? "is-error" : ""}`}>
            {m.role === "assistant" ? <Markdown text={m.content} /> : <div>{m.content}</div>}
            {m.result?.rows?.length > 0 && <details open><summary>{t.rows} ({m.result.row_count})</summary><ResultTable result={m.result} /></details>}
            {m.sql && <details><summary><Code2 size={12} /> {t.sql}</summary><pre dir="ltr">{m.sql}</pre></details>}
            {m.sources?.some((s) => s.file) && <small className="rag-sources">{t.sources}: {m.sources.filter((s) => s.file).map((s) => s.file).join(" · ")}</small>}
          </article>
        ))}
        {busy && <div className="rag-message assistant rag-busy">{t.busy}</div>}
        <div ref={bottomRef} />
      </div>

      {hasFilters(filters) && <div className="rag-filters">{t.filters}: {Object.entries(filters).filter(([, v]) => (Array.isArray(v) ? v.length : v)).map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(", ") : v}`).join(" · ")}</div>}

      <form className="rag-compose" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={t.placeholder} maxLength={3000} />
        {busy
          ? <button type="button" onClick={() => abortRef.current?.abort("user")} aria-label={t.stop} title={t.stop}><Square size={16} /></button>
          : <button disabled={!input.trim()} aria-label="Send"><Send size={17} /></button>}
      </form>
    </section>
  );
}

export function RAGPage() {
  return (
    <div className="rag-page">
      <div className="rag-intro"><h2>AI & RAG Intelligence</h2><p>استرجاع من الملفات + استعلامات SQL قابلة للتحقق</p></div>
      <Panel />
    </div>
  );
}

export default function RAGFloating() {
  const [open, setOpen] = useState(false);
  return (
    <div className="rag-fab-wrap">
      <button className="rag-fab" onClick={() => setOpen((v) => !v)} aria-label="Open AI assistant"><MessageCircle size={22} /></button>
      {open && <Panel floating onClose={() => setOpen(false)} />}
    </div>
  );
}