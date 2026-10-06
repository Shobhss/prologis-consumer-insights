"""Dashboard: a single self-contained HTML page of verified signals for all customers.

Written to outputs/dashboard/index.html so the folder can be deployed as a static
site (Vercel, Netlify, GitHub Pages). No server, no build step: the page embeds the
signal data as JSON and renders with vanilla JS.

Design follows the shadcn/ui dashboard example (github.com/shadcn-ui/ui):
zinc palette, Geist type, bordered cards, dense table, light and dark mode.

Each row shows the four things reviewers asked for: the insight, the source link,
what it means for Prologis, and the action to take. The verbatim quote is one
click away so nobody has to trust a summary.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .config import OUT_DIR, ROOT, load_customers
from .taxonomy import SIGNALS

TEMPLATE = ROOT / "pipeline" / "templates" / "dashboard.html"
FIELDS = ["signal_id", "customer", "signal_code", "headline", "quote", "geography", "magnitude", "timeframe",
          "direction", "specificity", "source_reliability", "corroboration", "confidence", "source_url",
          "source_type", "published_at", "implication", "go_do", "audience", "horizon"]


def collect(con, min_confidence: float = 0.0) -> list[dict]:
    rows = con.execute(
        f"SELECT {', '.join(FIELDS)} FROM signals WHERE quote_verified=1 AND confidence>=? "
        "ORDER BY customer, confidence DESC, published_at DESC", (min_confidence,)).fetchall()
    return [dict(r) for r in rows]


def run(con, min_confidence: float = 0.0, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or OUT_DIR / "dashboard"
    out_dir.mkdir(parents=True, exist_ok=True)
    customers = {c["slug"]: c["name"] for c in load_customers()}
    payload = {
        "generated": date.today().isoformat(),
        "customers": customers,
        "types": {code: name for code, (name, _) in SIGNALS.items()},
        "signals": collect(con, min_confidence),
    }
    html = TEMPLATE.read_text(encoding="utf-8").replace(
        "/*__DATA__*/null", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
    path = out_dir / "index.html"
    path.write_text(html, encoding="utf-8")
    return path
