"""SQLite store for raw documents, chunks and extracted signals.

Tables
------
documents : one row per fetched source document (filing, transcript, article)
chunks    : documents split into ~1,500-token pieces; prefilter flag lives here
signals   : LLM-extracted signals, one row per signal, with grounding fields
feedback  : reviewer verdicts on signals (useful / not_useful / wrong)
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH, DATA_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  doc_id        TEXT PRIMARY KEY,
  customer      TEXT NOT NULL,
  source_type   TEXT NOT NULL,     -- 10-K | 10-Q | 8-K | transcript | press_release | news
  source_tier   INTEGER NOT NULL,  -- 1 filings, 2 transcripts, 3 announcements, 4 trade press, 5 market
  title         TEXT,
  url           TEXT NOT NULL,
  published_at  TEXT,
  retrieved_at  TEXT NOT NULL,
  content_hash  TEXT NOT NULL,
  n_chars       INTEGER,
  meta          TEXT,              -- JSON
  text_path     TEXT NOT NULL      -- file under data/raw holding the plain text
);
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id      TEXT PRIMARY KEY,
  doc_id        TEXT NOT NULL REFERENCES documents(doc_id),
  idx           INTEGER NOT NULL,
  section       TEXT,
  text          TEXT NOT NULL,
  n_chars       INTEGER,
  relevant      INTEGER,           -- NULL = not scored, 0/1 after prefilter
  kw_hits       TEXT,              -- JSON list of matched keywords
  extracted_at  TEXT
);
CREATE TABLE IF NOT EXISTS signals (
  signal_id        TEXT PRIMARY KEY,
  chunk_id         TEXT NOT NULL REFERENCES chunks(chunk_id),
  doc_id           TEXT NOT NULL,
  customer         TEXT NOT NULL,
  signal_code      TEXT NOT NULL,
  headline         TEXT NOT NULL,
  quote            TEXT NOT NULL,
  quote_verified   INTEGER NOT NULL,
  geography        TEXT,
  magnitude        TEXT,
  timeframe        TEXT,
  direction        TEXT,
  specificity      INTEGER,
  source_reliability INTEGER,
  confidence       REAL,
  source_url       TEXT,
  source_type      TEXT,
  published_at     TEXT,
  implication      TEXT,
  go_do            TEXT,
  audience         TEXT,
  horizon          TEXT,
  cluster_id       TEXT,
  corroboration    INTEGER DEFAULT 1,
  model            TEXT,
  created_at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
  signal_id   TEXT NOT NULL,
  verdict     TEXT NOT NULL,   -- useful | not_useful | wrong
  note        TEXT,
  reviewer    TEXT,
  created_at  TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


@contextmanager
def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def upsert_document(con, *, customer, source_type, source_tier, title, url,
                    published_at, text, meta=None) -> tuple[str, bool]:
    """Store a document. Returns (doc_id, is_new). Dedupes on URL+content hash."""
    content_hash = sha1(text)
    doc_id = sha1(f"{url}|{content_hash}")[:16]
    cur = con.execute("SELECT 1 FROM documents WHERE doc_id=?", (doc_id,))
    if cur.fetchone():
        return doc_id, False
    from .config import RAW_DIR
    path = RAW_DIR / customer / source_type.replace("-", "").lower()
    path.mkdir(parents=True, exist_ok=True)
    text_path = path / f"{doc_id}.txt"
    text_path.write_text(text, encoding="utf-8")
    con.execute(
        """INSERT INTO documents(doc_id, customer, source_type, source_tier, title, url,
           published_at, retrieved_at, content_hash, n_chars, meta, text_path)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (doc_id, customer, source_type, source_tier, title, url, published_at,
         now_iso(), content_hash, len(text), json.dumps(meta or {}), str(text_path)),
    )
    return doc_id, True


def doc_counts(con, customer: str | None = None):
    q = "SELECT source_type, COUNT(*) n, SUM(n_chars) chars FROM documents"
    args = ()
    if customer:
        q += " WHERE customer=?"
        args = (customer,)
    q += " GROUP BY source_type ORDER BY source_type"
    return [dict(r) for r in con.execute(q, args)]
