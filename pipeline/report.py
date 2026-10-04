"""Report: Excel signal table plus a Markdown brief in Sarah's format.

Outputs land in outputs/<customer>/<YYYY-MM-DD>/:
  signals.xlsx  - one row per verified signal; columns match the fields Sarah
                  described (customer, signal, implication, confidence, source link)
                  plus a Themes sheet rolling signals up by type and geography.
  brief.md      - "What's happening / Why it matters / What it means for Prologis /
                  What we're watching", top signals by confidence, every claim linked.

Only signals with quote_verified=1 and confidence >= min_confidence are included.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

from .config import OUT_DIR
from .taxonomy import SIGNALS

COLUMNS = ["customer", "signal_code", "signal_type", "headline", "implication", "go_do", "audience", "horizon",
           "confidence", "corroboration", "specificity", "source_reliability", "geography", "magnitude", "timeframe",
           "direction", "quote", "source_type", "published_at", "source_url", "signal_id"]


def load(con, customer: str, min_confidence: float = 0.0) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT * FROM signals WHERE customer=? AND quote_verified=1 AND confidence>=? ORDER BY confidence DESC, published_at DESC",
        con, params=(customer, min_confidence))
    df["signal_type"] = df["signal_code"].map(lambda c: SIGNALS.get(c, (c,))[0])
    return df[[c for c in COLUMNS if c in df.columns]]


def write_excel(df: pd.DataFrame, path: Path) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name="Signals", index=False)
        themes = (df.groupby(["signal_type", "geography"], dropna=False)
                    .agg(signals=("signal_id", "count"), avg_confidence=("confidence", "mean"),
                         sources=("source_url", "nunique"), example=("headline", "first"))
                    .reset_index().sort_values(["signals", "avg_confidence"], ascending=False))
        themes["avg_confidence"] = themes["avg_confidence"].round(2)
        themes.to_excel(xw, sheet_name="Themes", index=False)
        for ws in xw.sheets.values():
            for col in ws.columns:
                width = min(60, max(12, max(len(str(c.value or "")) for c in col[:50]) + 2))
                ws.column_dimensions[col[0].column_letter].width = width
            ws.freeze_panes = "A2"


def _link(row) -> str:
    label = f"{row.source_type} {row.published_at or ''}".strip()
    return f"[{label}]({row.source_url})"


def write_brief(df: pd.DataFrame, customer_name: str, path: Path, top_n: int = 12) -> None:
    today = date.today().isoformat()
    lines = [f"# {customer_name}: customer intelligence brief", f"_Generated {today}. {len(df)} verified signals. "
             "Every statement links to its source; confidence is computed from specificity, source reliability and corroboration._", ""]
    now = df[df.horizon == "now"].head(top_n)
    watch = df[df.horizon == "watch"].head(top_n)

    lines += ["## What's happening", ""]
    by_type = defaultdict(list)
    for r in df.head(top_n * 2).itertuples():
        by_type[r.signal_type].append(r)
    for t, rows in by_type.items():
        lines.append(f"**{t}**")
        for r in rows[:4]:
            lines.append(f"- {r.headline} (confidence {r.confidence:.2f}, {_link(r)})")
        lines.append("")

    lines += ["## Why it matters and what it means for Prologis", ""]
    for r in now.itertuples():
        lines.append(f"- **{r.headline}** {r.implication or ''} {_link(r)}")
        if r.go_do and r.go_do.lower() != "none; monitor.":
            lines.append(f"  - Go-do: {r.go_do}")
    if now.empty:
        lines.append("_No signals flagged for action this cycle._")
    lines.append("")

    lines += ["## What we're watching", ""]
    for r in watch.itertuples():
        lines.append(f"- {r.headline} {('(' + r.implication + ')') if r.implication else ''} {_link(r)}")
    if watch.empty:
        lines.append("_Nothing on the watch list yet._")
    lines.append("")

    lines += ["## Evidence table", "", "| Confidence | Type | Signal | Quote | Source |", "|---|---|---|---|---|"]
    for r in df.head(40).itertuples():
        q = r.quote.replace("|", "/").replace("\n", " ")
        lines.append(f"| {r.confidence:.2f} | {r.signal_code} | {r.headline} | \"{q}\" | {_link(r)} |")
    path.write_text("\n".join(lines), encoding="utf-8")


def run(con, customer: str, min_confidence: float = 0.0) -> list[Path]:
    from .config import get_customer
    cust = get_customer(customer)
    df = load(con, customer, min_confidence)
    out = OUT_DIR / customer / date.today().isoformat()
    out.mkdir(parents=True, exist_ok=True)
    xlsx, brief = out / "signals.xlsx", out / "brief.md"
    write_excel(df, xlsx)
    write_brief(df, cust["name"], brief)
    return [xlsx, brief]
