"""Prefilter: cheap keyword screen so only real-estate-relevant chunks reach the LLM.

A chunk is marked relevant when it contains at least one STRONG term or at least
three WEAK terms. News documents are always sent through (they are already
customer-filtered and short). The matched terms are saved in `kw_hits` so
reviewers can see why a chunk was selected.

Tune the lists here; false negatives (missed chunks) are the main risk, so err
on the side of inclusion. On the Amazon 10-K this cuts ~85% of chunks.
"""
from __future__ import annotations

import json
import re

STRONG = [
    "square feet", "square foot", "sq. ft", "sq ft", "fulfillment center", "fulfilment center",
    "distribution center", "warehouse", "delivery station", "sortation", "sort center",
    "logistics network", "fulfillment network", "operating lease", "lease commitment",
    "build-to-suit", "sale-leaseback", "industrial real estate", "data center", "data centers",
    "cold storage", "cross-dock", "3pl", "third-party logistics", "nearshoring",
]
WEAK = [
    "capital expenditure", "capex", "facilities", "footprint", "expansion", "leased",
    "closure", "consolidat", "automation", "robotics", "supply chain", "logistics",
    "last mile", "last-mile", "same-day", "acquisition", "real estate", "property and equipment",
    "impairment", "sublease", "restructuring", "layoff", "hiring", "land",
    "solar", "ev charging", "electric vehicle", "nearshor", "tariff",
]


def score(text: str) -> tuple[bool, list[str]]:
    low = text.lower()
    strong = [t for t in STRONG if t in low]
    weak = [t for t in WEAK if t in low]
    relevant = bool(strong) or len(weak) >= 3
    return relevant, strong + weak


def run(con, customer: str | None = None, force: bool = False) -> dict:
    q = """SELECT c.chunk_id, c.text, d.source_type FROM chunks c JOIN documents d ON d.doc_id=c.doc_id"""
    conds, args = [], []
    if customer:
        conds.append("d.customer=?")
        args.append(customer)
    if not force:
        conds.append("c.relevant IS NULL")
    if conds:
        q += " WHERE " + " AND ".join(conds)
    stats = {"scored": 0, "relevant": 0}
    for row in con.execute(q, args).fetchall():
        if row["source_type"] == "news":
            rel, hits = True, score(row["text"])[1]
        else:
            rel, hits = score(row["text"])
        con.execute("UPDATE chunks SET relevant=?, kw_hits=? WHERE chunk_id=?",
                    (int(rel), json.dumps(hits[:12]), row["chunk_id"]))
        stats["scored"] += 1
        stats["relevant"] += int(rel)
    return stats
