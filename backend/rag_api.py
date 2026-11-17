"""Cottonil grounded data agent (v2).

Flow: question -> compact catalog -> model writes ONE read-only SQL query as JSON -> DuckDB runs it
(on views that already carry the dashboard filters) -> model explains the rows. Failed SQL is sent back to
the model with the database error so it can repair it. Numbers always come from DuckDB, never from the model.
"""
from __future__ import annotations

import json
import logging
import os
import re
import socket
import urllib.error
import time
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.rag_engine import INDEX_DIR, ingest_all, list_tables, run_readonly_sql, search_chunks

load_dotenv(Path(__file__).resolve().parent / ".env")  # main.py does not load .env itself
log = logging.getLogger("cottonil.rag")
router = APIRouter(prefix="/api/rag", tags=["Grounded RAG Agent"])

# ------------------------------------------------------------------ LLM config (free API, no local model)
# Any OpenAI-compatible provider works. Set LLM_API_KEY in backend/.env; the rest has sensible defaults.
PRESETS: dict[str, tuple[str, str]] = {
    "groq": ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
    "openrouter": ("https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free"),
}
PROVIDER = os.getenv("LLM_PROVIDER", "groq").strip().lower()
_default_url, _default_model = PRESETS.get(PROVIDER, PRESETS["groq"])
BASE_URL = os.getenv("LLM_BASE_URL", _default_url).strip().rstrip("/")
MODEL = os.getenv("LLM_MODEL", _default_model).strip()
API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))
MAX_REPAIRS = 2
PROMPT_CHAR_BUDGET = int(os.getenv("LLM_PROMPT_CHAR_BUDGET", "24000"))  # API models have large windows; this just caps cost/latency


class AskRequest(BaseModel):
    message: str = Field(min_length=1, max_length=3000)
    history: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    filters: dict[str, Any] = Field(default_factory=dict)
    page: str = "overview"


class ActionRequest(BaseModel):
    action: str
    value: dict[str, Any] = Field(default_factory=dict)


# ------------------------------------------------------------------ catalog
# friendly view name -> (physical table, one-line meaning). Only these tables are shown to the model.
SEMANTIC: dict[str, tuple[str, str]] = {
    "fact_sales": ("processed__fact_sales", "one row per sold line, with product, category, audience, channel and year_month"),
    "fact_returns": ("processed__fact_returns", "one row per returned line, with reason, refund and days_to_return"),
    "branches": ("branches", "branch names and governorates"),
    "customers": ("customers", "customer segment, governorate, age band"),
    "sales_orders": ("sales_orders", "one row per order (customer_id may be empty)"),
    "delivery_shipments": ("delivery_shipments", "e-commerce shipments only"),
    "monthly_stock": ("monthly_stock", "closing stock per location and category per month"),
    "purchase_orders": ("purchase_orders", "purchase order headers"),
    "purchase_order_items": ("purchase_order_items", "purchase order lines"),
    "import_shipments": ("import_shipments", "imports, amounts in USD"),
    "marketing_campaigns": ("marketing_campaigns", "campaign spend, clicks, impressions"),
    "payroll": ("payroll", "monthly payroll per employee"),
    "employees": ("employees", "employees and their branch"),
    "operating_expenses": ("operating_expenses", "expenses per branch (BR…) or warehouse (WH…)"),
    "suppliers": ("suppliers", "suppliers"),
    "warehouses": ("warehouses", "warehouses and capacity"),
    "inventory_transfers": ("inventory_transfers", "stock transfers to branches"),
    "products_catalog": ("products_catalog", "product master"),
    "sku_variants": ("sku_variants", "size and color per SKU"),
}


@lru_cache(maxsize=1)
def catalog_text() -> str:
    """Compact catalog (names only). The full typed catalog was ~5,400 tokens; this is roughly a fifth of that."""
    real = {t["table"]: [c["name"] for c in t["columns"]] for t in list_tables()}
    lines = []
    for view, (table, meaning) in SEMANTIC.items():
        if table in real:
            lines.append(f"{view} ({meaning}): " + ", ".join(real[table]))
    return "\n".join(lines)


def _lit(v: Any) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def _in(col: str, values: Any) -> str | None:
    vals = [v for v in (values or []) if str(v).strip()]
    return f"{col} IN ({', '.join(_lit(v) for v in vals)})" if vals else None


def filter_views(filters: dict[str, Any]) -> dict[str, str]:
    """Temp views carrying the dashboard filters (same keys as the dashboard: date_from, date_to, branches, ...)."""
    f = filters or {}
    real = {t["table"] for t in list_tables()}

    def build(table: str, alias: str, date_col: str, channel: bool, product: bool, category: bool) -> str:
        where, join = [], ""
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(f.get("date_from", ""))):
            where.append(f"{alias}.{date_col} >= DATE '{f['date_from']}'")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(f.get("date_to", ""))):
            where.append(f"{alias}.{date_col} <= DATE '{f['date_to']}'")
        where.append(_in(f"{alias}.branch_id", f.get("branches")))
        if category:
            where.append(_in(f"{alias}.category_en", f.get("categories")))
        if product:
            where.append(_in(f"{alias}.product_id", f.get("products")))
        if channel:
            where.append(_in(f"{alias}.sales_channel", f.get("channels")))
        gov = _in("g.governorate_ar", f.get("governorates"))
        if gov:
            join = f" JOIN branches g ON g.branch_id = {alias}.branch_id"
            where.append(gov)
        clauses = [w for w in where if w]
        return f"SELECT {alias}.* FROM {table} {alias}{join}" + (" WHERE " + " AND ".join(clauses) if clauses else "")

    views: dict[str, str] = {}
    if "processed__fact_sales" in real:
        views["fact_sales"] = build("processed__fact_sales", "s", "order_date", True, True, True)
    if "processed__fact_returns" in real:
        views["fact_returns"] = build("processed__fact_returns", "r", "return_date", True, True, True)
    if "sales_orders" in real:
        views["sales_orders"] = build("sales_orders", "o", "order_date", True, False, False)
    for view, (table, _) in SEMANTIC.items():
        if view not in views and table in real:
            views[view] = f"SELECT * FROM {table}"
    return views


# ------------------------------------------------------------------ prompts
PLANNER = """You are Cottonil's data analyst. Reply with ONE JSON object and nothing else.
Shapes: {"mode":"sql","sql":"SELECT ...","explanation":"..."} or {"mode":"rag","answer":"..."} or {"mode":"insufficient","reason":"..."}.
Rules:
- Any number, ranking, trend, comparison or count -> mode "sql". Descriptive questions about the data -> mode "rag".
- Write ONE read-only DuckDB SELECT/WITH using ONLY tables and columns listed in CATALOG. Never invent a column.
- Sales questions use fact_sales. Return questions use fact_returns. Product names are in fact_sales.product_name_ar.
- Branch name or governorate: JOIN branches USING (branch_id).
- Net sales = SUM(net_line_EGP). Margin % = SUM(margin_EGP)/SUM(net_line_EGP)*100. Orders = COUNT(DISTINCT sales_order_id). Units = SUM(quantity).
- Return rate % = SUM(refund_amount_EGP) / net sales of the same scope. Imports are USD, everything else EGP.
- Months: use the year_month column or strftime(order_date,'%Y-%m'). Always ORDER BY, and LIMIT 10 unless asked otherwise.
- Data ends on 2026-10-18, so October 2026 is a partial month.
- The dashboard filters are already applied inside the views. Do not repeat them.
Examples:
Q: top 5 products by sales
{"mode":"sql","sql":"SELECT product_name_ar, SUM(net_line_EGP) AS net_sales FROM fact_sales GROUP BY 1 ORDER BY 2 DESC LIMIT 5","explanation":"net sales per product"}
Q: sales by governorate
{"mode":"sql","sql":"SELECT b.governorate_ar, SUM(s.net_line_EGP) AS net_sales FROM fact_sales s JOIN branches b USING (branch_id) GROUP BY 1 ORDER BY 2 DESC LIMIT 10","explanation":"net sales per governorate"}
Q: monthly sales trend
{"mode":"sql","sql":"SELECT year_month, SUM(net_line_EGP) AS net_sales FROM fact_sales GROUP BY 1 ORDER BY 1","explanation":"net sales per month"}"""

EXPLAINER = (
    "Answer in the language of the question (Arabic if it is Arabic). Use ONLY the result rows provided. "
    "Start with one headline sentence, then at most 6 short bullets with the exact numbers (thousands separators, EGP for money). "
    "Never add causes or figures that are not in the rows. If there are no rows, say no matching records were found. "
    "Mention the active filters in one short line if any are set."
)


# ------------------------------------------------------------------ LLM client (OpenAI-compatible)
def _llm(messages: list[dict[str, str]], *, json_mode: bool = False, num_predict: int = 700) -> str:
    if not API_KEY:
        raise HTTPException(503, "LLM_API_KEY is not set. Add it to backend/.env and restart the backend.")
    payload: dict[str, Any] = {"model": MODEL, "messages": messages, "temperature": 0.1, "max_tokens": num_predict}
    if "gpt-oss" in MODEL.lower():
        # gpt-oss is a reasoning model: hidden reasoning tokens count against max_tokens, so keep the reasoning short
        # and leave room, otherwise the visible answer can come back empty.
        payload["max_tokens"] = max(num_predict, 1500)
        if PROVIDER == "groq":
            payload["reasoning_effort"] = "low"
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}",
               "User-Agent": "cottonil-hub/1.0"}  # some providers sit behind Cloudflare and block the default urllib agent

    content, waited, dropped_json = "", False, False
    while True:
        req = urllib.request.Request(BASE_URL + "/chat/completions", headers=headers,
                                     data=json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        try:
            with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as r:
                data = json.loads(r.read().decode("utf-8"))
            choices = data.get("choices") or []
            content = ((choices[0].get("message") or {}).get("content") or "") if choices else ""
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            if e.code == 400 and json_mode and not dropped_json and "response_format" in payload:
                payload.pop("response_format")  # this model/provider has no JSON mode; parse_plan() copes with plain text
                dropped_json = True
                continue
            if e.code == 429 and not waited:  # free tiers are rate limited: wait once, then retry
                waited = True
                try:
                    delay = min(float(e.headers.get("Retry-After", "3")), 20.0)
                except (TypeError, ValueError):
                    delay = 3.0
                time.sleep(delay)
                continue
            if e.code == 429:
                raise HTTPException(429, "Free-tier rate limit reached. Wait a minute and try again, or switch to another provider/model in .env.")
            if e.code in (401, 403):
                raise HTTPException(503, f"The API key was rejected by {PROVIDER} (HTTP {e.code}). Check LLM_API_KEY. Details: {body[:200]}")
            if e.code == 404:
                raise HTTPException(503, f"Model '{MODEL}' was not found at {BASE_URL}. Check LLM_MODEL and LLM_PROVIDER in .env. Details: {body[:200]}")
            raise HTTPException(502, f"LLM provider HTTP {e.code}: {body}")
        except (urllib.error.URLError, ConnectionError):
            raise HTTPException(503, f"Cannot reach the LLM provider at {BASE_URL}. Check the internet connection.")
        except (socket.timeout, TimeoutError):
            raise HTTPException(504, "The model took too long to answer. Try a shorter question.")
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()  # some models print their reasoning
    if not content:
        raise HTTPException(502, "The model returned an empty answer.")
    return content


def parse_plan(raw: str) -> dict[str, Any] | None:
    text = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    for candidate in (text, text[text.find("{"): text.rfind("}") + 1]):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except (ValueError, TypeError):
            continue
    return None


def fit(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep the prompt inside the context window by dropping the oldest history first (never the instructions)."""
    msgs = list(messages)
    while sum(len(m["content"]) for m in msgs) > PROMPT_CHAR_BUDGET and len(msgs) > 2:
        del msgs[1]
    total = sum(len(m["content"]) for m in msgs)
    log.info("prompt chars=%d (budget %d), messages=%d", total, PROMPT_CHAR_BUDGET, len(msgs))
    return msgs


def _table_text(result: dict[str, Any], limit: int = 15) -> str:
    cols = result["columns"]
    lines = [" | ".join(cols)] + [" | ".join(str(r.get(c, "")) for c in cols) for r in result["rows"][:limit]]
    return "\n".join(lines)


# ------------------------------------------------------------------ routes
@router.get("/status")
def status() -> dict[str, Any]:
    """Config-only check (no call to the provider, so it never spends free-tier quota)."""
    configured = bool(API_KEY)
    index = (INDEX_DIR / "manifest.json").exists()
    hint = None if (configured and index) else (
        "Set LLM_API_KEY in backend/.env (free key from Groq, Google AI Studio or OpenRouter) and restart the backend."
        if not configured else "Build the index: py -m backend.ingest_data")
    return {"llm_configured": configured, "provider": PROVIDER, "model": MODEL, "model_ready": configured,
            "index_ready": index, "tables": len(SEMANTIC) if index else 0, "hint": hint}


@router.post("/ingest")
def ingest() -> dict[str, Any]:
    try:
        result = {"ok": True, **ingest_all()}
        catalog_text.cache_clear()
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/tables")
def tables() -> dict[str, Any]:
    p = INDEX_DIR / "manifest.json"
    return {"tables": json.loads(p.read_text(encoding="utf-8")) if p.exists() else []}


@router.post("/ask")
def ask(body: AskRequest) -> dict[str, Any]:
    history = [{"role": m["role"], "content": m["content"][:600]} for m in body.history[-6:]
               if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str) and m["content"].strip()]
    notes = search_chunks(body.message, 2, sources=["data_dictionary.csv"])
    note_text = "\n".join(n["content"][:600] for n in notes)
    sources: list[dict[str, Any]] = [{"file": n["source"], "type": n["chunk_type"]} for n in notes]
    catalog = catalog_text()
    if not catalog:
        raise HTTPException(503, "The data index is empty. Run: py -m backend.ingest_data")

    planning = [{"role": "system", "content": PLANNER}, *history,
                {"role": "user", "content": f"CATALOG:\n{catalog}\n\nDATA DICTIONARY NOTES:\n{note_text}\n\nQ: {body.message}"}]
    raw = _llm(fit(planning), json_mode=True)
    plan = parse_plan(raw)
    if plan is None:  # one retry: ask for valid JSON only
        raw = _llm(fit([*planning, {"role": "assistant", "content": raw[:400]},
                           {"role": "user", "content": "That was not valid JSON. Return only the JSON object."}]), json_mode=True)
        plan = parse_plan(raw)
    if plan is None:
        return {"answer": "لم أستطع فهم رد النموذج. أعد صياغة السؤال بشكل أقصر.", "mode": "error", "sql": None,
                "sql_result": None, "sources": sources, "grounded": False, "filters_applied": body.filters, "dashboard_action": None}

    mode, result, sql, attempts = plan.get("mode"), None, None, 0
    if mode == "sql":
        views = filter_views(body.filters)
        error = ""
        while True:
            sql = str(plan.get("sql", ""))
            try:
                result = run_readonly_sql(sql, views=views)
                sources.append({"type": "executed_sql", "sql": sql})
                break
            except Exception as e:  # database error -> let the model repair it
                error = str(e)[:600]
                log.warning("SQL failed (attempt %d): %s | %s", attempts, error, sql[:200])
                if attempts >= MAX_REPAIRS:
                    break
                attempts += 1
                fix = _llm(fit([*planning, {"role": "assistant", "content": json.dumps(plan, ensure_ascii=False)[:800]},
                                   {"role": "user", "content": f"The SQL failed with: {error}\nFix it using only columns from CATALOG and return the JSON again."}]),
                              json_mode=True)
                plan = parse_plan(fix) or plan
                if plan.get("mode") != "sql":
                    break
        if result is None:
            answer = f"لم أتمكن من تنفيذ استعلام صحيح لهذا السؤال بعد {attempts + 1} محاولات. جرّب صياغة أبسط أو حدّد الفترة أو الفرع. (تفاصيل: {error})"
            return {"answer": answer, "mode": "sql_failed", "sql": sql, "sql_result": None, "sources": sources, "grounded": False,
                    "filters_applied": body.filters, "dashboard_action": None, "attempts": attempts + 1}
        try:
            answer = _llm(fit([{"role": "system", "content": EXPLAINER},
                                  {"role": "user", "content": f"Question: {body.message}\nActive filters: {json.dumps(body.filters, ensure_ascii=False)}\n"
                                                              f"Rows ({result['row_count']} total{', truncated' if result['truncated'] else ''}):\n{_table_text(result)}"}]), num_predict=500)
        except HTTPException:  # the numbers are already computed: never lose them because the explainer failed
            answer = "نتيجة الاستعلام:\n" + _table_text(result)
    elif mode == "insufficient":
        answer = "لا توجد معلومات كافية في البيانات للإجابة بثقة. " + str(plan.get("reason", ""))
    else:
        answer = str(plan.get("answer") or "لم أجد معلومات كافية للإجابة.")
    return {"answer": answer, "mode": mode or "rag", "sql": sql, "sql_result": result, "sources": sources,
            "grounded": bool(result), "filters_applied": body.filters, "dashboard_action": None, "attempts": attempts + 1}


@router.post("/action")
def dashboard_action(body: ActionRequest) -> dict[str, Any]:
    if body.action not in {"navigate", "set_filters", "show_chart", "clear_filters"}:
        raise HTTPException(400, "Unsupported dashboard action")
    return {"ok": True, "action": body.action, "payload": body.value, "requires_frontend_apply": True}