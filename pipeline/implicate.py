"""Implicate: turn verified signals into Prologis-specific implications.

Runs on clusters of verified signals (same code + geography), not on raw text,
so the model reasons from facts we have already grounded. The prompt includes
config/prologis_context.md so implications name Prologis markets, teams and
products instead of being generic.

Each signal gets:
  implication : what it means for Prologis (1-2 sentences, hedged to the confidence)
  go_do       : a concrete action for a named team (leasing / account team / C-suite / none)
  audience    : c-suite | account_team | leasing | all
  horizon     : now (act or brief this cycle) | watch (monitor over 2+ quarters)

The model is told the confidence score and asked to hedge accordingly: low
confidence must read as "possible" or "worth watching", never as fact.
"""
from __future__ import annotations

import json

from .config import IMPLICATE_MODEL, ROOT
from .llm import structured_call
from .taxonomy import taxonomy_markdown

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "signal_id": {"type": "string"},
                    "implication": {"type": "string"},
                    "go_do": {"type": "string"},
                    "audience": {"type": "string", "enum": ["c-suite", "account_team", "leasing", "all"]},
                    "horizon": {"type": "string", "enum": ["now", "watch"]},
                },
                "required": ["signal_id", "implication", "go_do", "audience", "horizon"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def _system() -> str:
    ctx = (ROOT / "config" / "prologis_context.md").read_text()
    return f"""You are the Head of Customer Intelligence at Prologis writing for executives and field teams.
You receive VERIFIED customer signals (each with a verbatim quote and a confidence score) and write what they mean for Prologis.

<prologis_context>
{ctx}
</prologis_context>

Signal taxonomy:
{taxonomy_markdown()}

Rules
1. Reason only from the signals given plus the Prologis context. Do not add facts about the customer that are not in the signals.
2. Hedge to the confidence: >=0.8 state plainly; 0.6-0.8 use "likely" / "suggests"; <0.6 use "possible" / "worth watching".
3. `implication`: 1-2 sentences on what this means for Prologis demand, markets, or relationship with this customer.
4. `go_do`: one concrete action with the team named, e.g. "Leasing (Dallas): confirm availability of 500K+ sq ft Class A within 30 days." If no action is warranted write "None; monitor."
5. `horizon`: "now" if a team should act or be briefed this cycle; "watch" if it is a trend to monitor over the next 2+ quarters.
6. Be specific to Prologis markets and teams. Avoid generic statements like "this could affect demand".
"""


def run(con, customer: str, limit: int | None = None, batch_size: int = 12) -> dict:
    """Write implications for verified signals that do not have one yet."""
    q = """SELECT signal_id, signal_code, headline, quote, geography, magnitude, timeframe, direction,
                  confidence, corroboration, source_type, published_at, horizon
           FROM signals WHERE customer=? AND quote_verified=1 AND implication IS NULL
           ORDER BY confidence DESC"""
    rows = [dict(r) for r in con.execute(q, (customer,)).fetchall()]
    if limit:
        rows = rows[:limit]
    stats = {"signals": 0, "batches": 0, "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0}
    system = _system()
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        payload = json.dumps(batch, indent=1)
        user = (f"Customer: {customer}\n\nSignals (JSON):\n{payload}\n\n"
                "Return one item per signal_id with implication, go_do, audience and horizon.")
        data, usage = structured_call(model=IMPLICATE_MODEL, system=system, user=user, schema=SCHEMA, effort="high")
        stats["batches"] += 1
        for k in ("input", "output", "cache_read"):
            stats[f"{k}_tokens"] += usage.get(k, 0)
        for item in (data or {}).get("items", []):
            con.execute("UPDATE signals SET implication=?, go_do=?, audience=?, horizon=? WHERE signal_id=?",
                        (item["implication"], item["go_do"], item["audience"], item["horizon"], item["signal_id"]))
            stats["signals"] += 1
        con.commit()
    return stats
