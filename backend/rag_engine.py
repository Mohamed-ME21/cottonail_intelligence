"""Cottonil RAG engine: materialized CSV tables + searchable chunks."""
from __future__ import annotations

import os
import re
import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("COTTONIL_DATA_DIR", str(BASE_DIR / "data")))
INDEX_DIR = Path(os.getenv("COTTONIL_RAG_DIR", str(BASE_DIR / "rag_index")))
DUCKDB_PATH = INDEX_DIR / "cottonil.duckdb"
FTS_PATH = INDEX_DIR / "chunks.sqlite3"

IGNORE_DIRS = {"rag_index", "__pycache__"}


def csv_files():
    if not DATA_DIR.exists():
        raise RuntimeError(f"Data directory not found: {DATA_DIR}")

    return sorted(
        p for p in DATA_DIR.rglob("*.csv")
        if not any(part in IGNORE_DIRS for part in p.parts)
    )


def safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not name or name[0].isdigit():
        name = "t_" + name
    return name.lower()


def connect_duckdb(read_only: bool = False):
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("Install DuckDB: pip install duckdb") from exc

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DUCKDB_PATH), read_only=read_only)


def ingest_all() -> dict[str, Any]:
    """Load CSV files into physical DuckDB tables and build FTS chunks."""
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    files = csv_files()
    if not files:
        raise RuntimeError(f"No CSV files found in {DATA_DIR}")

    con = connect_duckdb()
    db = sqlite3.connect(str(FTS_PATH))
    manifest = []

    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY,
                source TEXT,
                chunk_type TEXT,
                content TEXT,
                metadata TEXT
            )
        """)
        db.execute("DROP TABLE IF EXISTS chunks_fts")
        db.execute("DELETE FROM chunks")

        for path in files:
            rel = path.relative_to(DATA_DIR).as_posix()
            table = safe_name(rel[:-4].replace("/", "__"))
            escaped_path = str(path.resolve()).replace("\\", "/").replace("'", "''")

            # Remove an old view/table before materializing the CSV.
            con.execute(f'DROP VIEW IF EXISTS "{table}"')
            con.execute(f'DROP TABLE IF EXISTS "{table}"')

            # This creates a physical DuckDB table, not an external CSV view.
            con.execute(
                f'''
                CREATE TABLE "{table}" AS
                SELECT *
                FROM read_csv_auto(
                    '{escaped_path}',
                    header = true,
                    sample_size = 20000,
                    ignore_errors = true
                )
                '''
            )

            columns = con.execute(
                f'DESCRIBE SELECT * FROM "{table}"'
            ).fetchall()

            row_count = con.execute(
                f'SELECT COUNT(*) FROM "{table}"'
            ).fetchone()[0]

            column_names = [c[0] for c in columns]
            schema = ", ".join(f"{c[0]} ({c[1]})" for c in columns)

            sample = con.execute(
                f'SELECT * FROM "{table}" LIMIT 3'
            ).df().to_dict(orient="records")

            description = (
                f"Table: {table}. Source: {rel}. Rows: {row_count}. "
                f"Columns: {schema}. "
                f"Sample: {json.dumps(sample, ensure_ascii=False, default=str)[:4000]}"
            )

            db.execute(
                """
                INSERT INTO chunks(source, chunk_type, content, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (
                    rel,
                    "table_schema",
                    description,
                    json.dumps({
                        "table": table,
                        "rows": int(row_count),
                        "columns": column_names
                    }, ensure_ascii=False)
                )
            )

            # Small dimension/reference tables can be chunked as records.
            # Large fact tables remain query-first in DuckDB.
            if row_count <= 10000:
                try:
                    df = con.execute(
                        f'SELECT * FROM "{table}"'
                    ).df()

                    records = df.to_dict(orient="records")

                    for start in range(0, len(records), 40):
                        part = records[start:start + 40]
                        content = (
                            f"Records from {rel}: "
                            + json.dumps(
                                part,
                                ensure_ascii=False,
                                default=str
                            )[:6500]
                        )

                        db.execute(
                            """
                            INSERT INTO chunks(source, chunk_type, content, metadata)
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                rel,
                                "records",
                                content,
                                json.dumps({
                                    "table": table,
                                    "offset": start,
                                    "count": len(part)
                                }, ensure_ascii=False)
                            )
                        )
                except Exception as exc:
                    print(f"Warning: record chunking skipped for {rel}: {exc}")

            manifest.append({
                "source": rel,
                "table": table,
                "rows": int(row_count),
                "columns": column_names
            })

            print(f"Loaded {rel}: {row_count:,} rows")

        # Rebuild full-text search index.
        db.execute("""
            CREATE VIRTUAL TABLE chunks_fts
            USING fts5(source, content, metadata,
                       content='chunks', content_rowid='id')
        """)
        db.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        db.commit()

    finally:
        db.close()
        con.close()

    (INDEX_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    chunk_db = sqlite3.connect(str(FTS_PATH))
    try:
        chunk_count = chunk_db.execute(
            "SELECT COUNT(*) FROM chunks"
        ).fetchone()[0]
    finally:
        chunk_db.close()

    return {
        "files": len(manifest),
        "rows": sum(item["rows"] for item in manifest),
        "chunks": chunk_count,
        "manifest": manifest
    }


STOPWORDS = {
    "the", "of", "a", "an", "and", "or", "in", "on", "by", "for", "to", "is", "are", "what", "which", "how", "many",
    "much", "show", "me", "top", "list", "give", "from", "with", "per", "all", "was", "were",
    "ما", "ماذا", "من", "في", "على", "عن", "هل", "كم", "هو", "هي", "الى", "إلى", "مع", "كل", "هذا", "هذه", "اعرض", "اعطني",
}


def search_chunks(query: str, limit: int = 6, sources: list[str] | None = None) -> list[dict[str, Any]]:
    """Full-text search over the indexed chunks. Stop-words are dropped so that common words do not match everything."""
    if not FTS_PATH.exists():
        return []

    all_terms = re.findall(r"[\w\u0600-\u06FF]+", query)
    terms = [t for t in all_terms if t.lower() not in STOPWORDS and len(t) > 1] or all_terms
    if not terms:
        return []

    match = " OR ".join('"' + t.replace('"', '""') + '"' for t in terms[:12])
    where = "chunks_fts MATCH ?"
    params: list[Any] = [match]
    if sources:
        where += " AND c.source IN (" + ",".join("?" * len(sources)) + ")"
        params += list(sources)

    db = sqlite3.connect(str(FTS_PATH))
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            f"""
            SELECT c.source, c.chunk_type, c.content, c.metadata, bm25(chunks_fts) AS score
            FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid
            WHERE {where} ORDER BY score LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error:
        return []
    finally:
        db.close()


def list_tables():
    if not DUCKDB_PATH.exists():
        return []

    con = connect_duckdb(read_only=True)
    try:
        tables = con.execute("SHOW TABLES").fetchall()
        catalog = []

        for row in tables:
            table_name = row[0]
            columns = con.execute(
                f"PRAGMA table_info('{table_name}')"
            ).fetchall()

            catalog.append({
                "table": table_name,
                "columns": [
                    {
                        "name": col[1],
                        "type": col[2]
                    }
                    for col in columns
                ]
            })

        return catalog
    finally:
        con.close()



def _clean_value(v: Any) -> Any:
    """Make a DuckDB/pandas value safe for JSON (no NaN, Inf, Decimal, Timestamp or numpy types)."""
    if v is None:
        return None
    if isinstance(v, float):
        return None if (v != v or v in (float("inf"), float("-inf"))) else v
    if isinstance(v, (bool, int, str)):
        return v
    if hasattr(v, "item"):
        try:
            return _clean_value(v.item())
        except Exception:
            pass
    return str(v)


def run_readonly_sql(sql: str, views: dict[str, str] | None = None, max_rows: int = 200, timeout: float = 25.0) -> dict[str, Any]:
    """Execute one read-only SELECT/WITH query.

    `views` maps a friendly name to a SELECT used to create a TEMP view for this connection only, which is how
    dashboard filters are enforced without trusting the model to repeat them.
    """
    import threading

    cleaned = sql.strip().rstrip(";")

    if not re.match(r"^(SELECT|WITH)\b", cleaned, re.I):
        raise ValueError("Only SELECT queries are allowed.")

    if ";" in cleaned or re.search(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|COPY|ATTACH|DETACH|INSTALL|LOAD|PRAGMA|EXPORT|IMPORT|CALL)\b",
        cleaned,
        re.I,
    ):
        raise ValueError("Query contains a prohibited operation.")

    if not DUCKDB_PATH.exists():
        raise RuntimeError("RAG database is not built. Run ingestion first.")

    con = connect_duckdb(read_only=True)
    timer = threading.Timer(timeout, con.interrupt)
    try:
        for name, select in (views or {}).items():
            con.execute(f'CREATE OR REPLACE TEMP VIEW "{name}" AS {select}')
        con.execute("SET enable_external_access = false")
        timer.start()
        df = con.execute(cleaned).df()
        records = df.head(max_rows).to_dict(orient="records")
        return {
            "columns": [str(c) for c in df.columns],
            "rows": [{k: _clean_value(v) for k, v in r.items()} for r in records],
            "row_count": len(df),
            "truncated": len(df) > max_rows,
        }
    finally:
        timer.cancel()
        con.close()