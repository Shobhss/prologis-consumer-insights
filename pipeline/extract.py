"""Extract: turn relevant chunks into grounded signal rows with Claude.

Grounding rule (the fix for "AI takes leaps")
---------------------------------------------
Every signal must carry a verbatim `quote`. After the model responds we check
that the quote is a substring of the chunk (whitespace and curly-quote
normalized). Signals that fail are stored with quote_verified=0 and are never
reported. Nothing in this stage asks the model for implications; that is a
separate step (implicate.py) so facts and reasoning stay apart.

Confidence (0-1) is computed in code, not by the model:
    0.45 * specificity/3 + 0.40 * source_reliability/3 + 0.15 * min(corroboration,3)/3
Corroboration is recomputed in `recompute_corroboration()` after each run by
grouping signals with the same code and geography across distinct documents.

Cost control: only chunks with relevant=1 are sent; the system prompt is cached.
"""
from __future__ import annotations

import json
import re

from .config import EXTRACT_MODEL
from .llm import structured_call
from .store import now_iso, sha1
from .taxonomy import CODES, taxonomy_markdown

SYSTEM = f"""You are an analyst at Prologis, the world's largest owner of logistics real estate.
You read documents about Prologis customers and extract SIGNALS that could change demand for industrial
real estate (warehouses, fulfillment and distribution centers, last-mile sites, land for logistics or data centers).

Signal taxonomy (use only these codes):
{taxonomy_markdown()}

Rules
1. Extract only what the text states. Do not infer, extrapolate or combine with outside knowledge.
2. `quote` must be copied VERBATIM from the text, 10 to 60 words, containing the key fact. Do not paraphrase.
3. Prefer specific facts: numbers (square feet, dollars, facility counts), named places, dates, named programs.
4. Skip generic business information (revenue growth, stock price, product launches) unless it states a real-estate consequence.
5. Skip boilerplate risk-factor language that appears every year unless it is new or quantified.
6. Several signals may come from one chunk; return an empty list if there are none.
7. `specificity`: 3 = named place AND a number or date; 2 = named place OR number; 1 = directional statement only.
8. `is_about_customer`: false if the text is about another company (e.g. a competitor or an analyst's view of the sector).
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "signals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "signal_code": {"type": "string", "enum": CODES},
                    "headline": {"type": "string", "description": "One factual sentence, max 25 words."},
                    "quote": {"type": "string"},
                    "geography": {"type": "string", "description": "Metro, state or country named; 'unspecified' if none."},
                    "magnitude": {"type": "string", "description": "Number with unit (sq ft, $, facilities, %), or 'unspecified'."},
                    "timeframe": {"type": "string", "description": "When it happens or happened, e.g. 'Q3 2026', 'FY2025', 'by 2027', or 'unspecified'."},
                    "direction": {"type": "string", "enum": ["expansion", "contraction", "shift", "neutral"]},
                    "specificity": {"type": "integer", "minimum": 1, "maximum": 3},
                    "is_about_customer": {"type": "boolean"},
                    "forward_looking": {"type": "boolean"},
                },
                "required": ["signal_code", "headline", "quote", "geography", "magnitude", "timeframe",
                             "direction", "specificity", "is_about_customer", "forward_looking"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["signals"],
    "additionalProperties": False,
}

TIER_RELIABILITY = {1: 3, 2: 3, 3: 3, 4: 2, 5: 2}


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def verify_quote(quote: str, chunk: str) -> bool:
    """True if `quote` appears verbatim in `chunk` after normalization. Allows the
    model to drop a trailing period or ellipsis."""
    q, c = _norm(quote), _norm(chunk)
    q = q.strip(" .…")
    return bool(q) and q in c


def confidence(specificity: int, reliability: int, corroboration: int = 1) -> float:
    return round(0.45 * specificity / 3 + 0.40 * reliability / 3 + 0.15 * min(corroboration, 3) / 3, 3)


def _user_prompt(customer_name: str, source_type: str, section: str, published: str | None, text: str) -> str:
    return (f"Customer: {customer_name}\nSource type: {source_type}\nSection: {section}\n"
            f"Published: {published or 'unknown'}\n\n<text>\n{text}\n</text>\n\n"
            f"Extract real-estate-relevant signals about {customer_name} from the text above.")


def run(con, customer: str, limit: int | None = None, sections: str | None = None) -> dict:
    """Extract signals for all relevant, not-yet-extracted chunks of `customer`."""
    cust_row = con.execute("SELECT customer FROM documents WHERE customer=? LIMIT 1", (customer,)).fetchone()
    if not cust_row:
        return {"error": f"no documents for {customer}"}
    from .config import get_customer
    cust = get_customer(customer)
    q = """SELECT c.chunk_id, c.text, c.section, d.doc_id, d.source_type, d.source_tier, d.url, d.published_at, d.meta
           FROM chunks c JOIN documents d ON d.doc_id=c.doc_id
           WHERE d.customer=? AND c.relevant=1 AND c.extracted_at IS NULL"""
    args: list = [customer]
    if sections:
        prefixes = [s.strip() for s in sections.split(",")]
        q += " AND (" + " OR ".join(["c.section LIKE ?"] * len(prefixes)) + ")"
        args += [p + "%" for p in prefixes]
    q += " ORDER BY d.source_tier, d.published_at DESC"
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = con.execute(q, args).fetchall()
    stats = {"chunks": 0, "signals": 0, "unverified": 0, "not_about_customer": 0, "refusals": 0,
             "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0}
    for r in rows:
        meta = json.loads(r["meta"] or "{}")
        reliability = meta.get("reliability") or TIER_RELIABILITY.get(r["source_tier"], 2)
        if r["source_type"] == "news" and not meta.get("full_text", True):
            reliability = min(reliability, 1)  # RSS summary only
        data, usage = structured_call(model=EXTRACT_MODEL, system=SYSTEM, schema=SCHEMA, effort="medium",
                                      user=_user_prompt(cust["name"], r["source_type"], r["section"], r["published_at"], r["text"]))
        stats["chunks"] += 1
        stats["input_tokens"] += usage.get("input", 0)
        stats["output_tokens"] += usage.get("output", 0)
        stats["cache_read_tokens"] += usage.get("cache_read", 0)
        if usage.get("refusal"):
            stats["refusals"] += 1
        for s in (data or {}).get("signals", []):
            if not s.get("is_about_customer", True):
                stats["not_about_customer"] += 1
                continue
            verified = verify_quote(s["quote"], r["text"])
            if not verified:
                stats["unverified"] += 1
            sid = sha1(f"{r['chunk_id']}|{s['signal_code']}|{s['quote'][:80]}")[:16]
            con.execute(
                """INSERT OR REPLACE INTO signals(signal_id, chunk_id, doc_id, customer, signal_code, headline, quote,
                   quote_verified, geography, magnitude, timeframe, direction, specificity, source_reliability,
                   confidence, source_url, source_type, published_at, model, created_at, horizon)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (sid, r["chunk_id"], r["doc_id"], customer, s["signal_code"], s["headline"], s["quote"],
                 int(verified), s["geography"], s["magnitude"], s["timeframe"], s["direction"], s["specificity"],
                 reliability, confidence(s["specificity"], reliability), r["url"], r["source_type"], r["published_at"],
                 usage.get("model"), now_iso(), "watch" if s.get("forward_looking") else "now"))
            stats["signals"] += 1
        con.execute("UPDATE chunks SET extracted_at=? WHERE chunk_id=?", (now_iso(), r["chunk_id"]))
        con.commit()
    stats.update(recompute_corroboration(con, customer))
    return stats


def recompute_corroboration(con, customer: str) -> dict:
    """Group verified signals by (code, geography) and count distinct source documents."""
    rows = con.execute("SELECT signal_id, signal_code, geography, doc_id, specificity, source_reliability FROM signals WHERE customer=? AND quote_verified=1", (customer,)).fetchall()
    groups: dict[tuple, set] = {}
    for r in rows:
        key = (r["signal_code"], _norm(r["geography"] or "unspecified"))
        groups.setdefault(key, set()).add(r["doc_id"])
    for r in rows:
        key = (r["signal_code"], _norm(r["geography"] or "unspecified"))
        n = len(groups[key]) if key[1] != "unspecified" else 1
        con.execute("UPDATE signals SET corroboration=?, cluster_id=?, confidence=? WHERE signal_id=?",
                    (n, sha1("|".join(key))[:10], confidence(r["specificity"], r["source_reliability"], n), r["signal_id"]))
    return {"clusters": len(groups)}
