"""Import hand-written or externally produced signals through the same checks as extract.py.

Used when the LLM stage cannot run (no API key) or when a reviewer wants to add a
signal by hand. Every row still goes through verify_quote(); a row whose quote is
not found verbatim in any chunk of the customer is rejected, not stored.

    python -m pipeline.import_signals docs/samples/amazon_signals_2026-10-05.json

JSON format: {"customer": "amazon", "model": "manual:...", "signals": [ {chunk_id?, signal_code,
headline, quote, geography, magnitude, timeframe, direction, specificity, forward_looking,
implication?, go_do?, audience?, horizon?} ]}
"""
from __future__ import annotations

import json
import sys

from . import store
from .extract import TIER_RELIABILITY, confidence, recompute_corroboration, verify_quote


def locate_chunk(con, customer: str, chunk_id: str | None, quote: str):
    """Return the chunk row containing `quote`, preferring `chunk_id` if given."""
    if chunk_id:
        r = con.execute("SELECT c.*, d.source_type, d.source_tier, d.url, d.published_at, d.meta FROM chunks c JOIN documents d ON d.doc_id=c.doc_id WHERE c.chunk_id=?", (chunk_id,)).fetchone()
        if r and verify_quote(quote, r["text"]):
            return r
    for r in con.execute("SELECT c.*, d.source_type, d.source_tier, d.url, d.published_at, d.meta FROM chunks c JOIN documents d ON d.doc_id=c.doc_id WHERE d.customer=? ORDER BY d.source_tier, d.published_at DESC", (customer,)):
        if verify_quote(quote, r["text"]):
            return r
    return None


def run(path: str) -> dict:
    spec = json.load(open(path))
    customer, model = spec["customer"], spec.get("model", "manual")
    stats = {"stored": 0, "rejected": []}
    with store.connect() as con:
        for s in spec["signals"]:
            r = locate_chunk(con, customer, s.get("chunk_id"), s["quote"])
            if r is None:
                stats["rejected"].append(s["headline"])
                continue
            meta = json.loads(r["meta"] or "{}")
            reliability = meta.get("reliability") or TIER_RELIABILITY.get(r["source_tier"], 2)
            if r["source_type"] == "news" and not meta.get("full_text", True):
                reliability = min(reliability, 1)
            sid = store.sha1(f"{r['chunk_id']}|{s['signal_code']}|{s['quote'][:80]}")[:16]
            con.execute(
                """INSERT OR REPLACE INTO signals(signal_id, chunk_id, doc_id, customer, signal_code, headline, quote,
                   quote_verified, geography, magnitude, timeframe, direction, specificity, source_reliability,
                   confidence, source_url, source_type, published_at, implication, go_do, audience, horizon, model, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (sid, r["chunk_id"], r["doc_id"], customer, s["signal_code"], s["headline"], s["quote"], 1,
                 s.get("geography", "unspecified"), s.get("magnitude", "unspecified"), s.get("timeframe", "unspecified"),
                 s.get("direction", "neutral"), int(s.get("specificity", 1)), reliability,
                 confidence(int(s.get("specificity", 1)), reliability), r["url"], r["source_type"], r["published_at"],
                 s.get("implication"), s.get("go_do"), s.get("audience"),
                 s.get("horizon") or ("watch" if s.get("forward_looking") else "now"), model, store.now_iso()))
            con.execute("UPDATE chunks SET extracted_at=COALESCE(extracted_at, ?) WHERE chunk_id=?", (store.now_iso(), r["chunk_id"]))
            stats["stored"] += 1
        stats.update(recompute_corroboration(con, customer))
    return stats


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1]), indent=1))
