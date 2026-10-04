"""Earnings call transcript fetcher.

Default provider: Motley Fool free transcripts, discovered through a Google News
RSS search restricted to fool.com (there is no public listing by ticker). Each
hit is decoded to the publisher URL and the article text extracted with
trafilatura. Transcripts are formatted as speaker turns:

    Brian Olsavsky -- Chief Financial Officer
    <paragraphs>

normalize.py splits on these speaker lines so quotes attribute correctly.

Optional provider: Financial Modeling Prep (set FMP_API_KEY). Kept as a fallback;
free-tier transcript access has changed over time, so verify before relying on it.

Inputs : customer dict (needs `name`, `ticker`), config `transcripts` block
Outputs: documents rows with source_type=transcript, tier 2
Known gaps: Google News returns ~100 results and not every quarter is guaranteed
to surface. Missing quarters can be added by URL with `add_url()`.
"""
from __future__ import annotations

import os
import re

import feedparser
import trafilatura

from ..store import upsert_document
from .util import cutoff, decode_google_news_link, get, google_news_rss, parse_date


def discover_fool_urls(customer: dict, since: str) -> list[tuple[str, str, str]]:
    """Return (url, published_date, title) for Motley Fool transcripts of this ticker."""
    q = f"{customer['name']} {customer['ticker']} earnings call transcript site:fool.com"
    feed = feedparser.parse(google_news_rss(q))
    ticker = customer["ticker"].lower()
    out, seen = [], set()
    for e in feed.entries:
        pub = parse_date(e.get("published"))
        if not pub or pub < since:
            continue
        if "earnings call transcript" not in e.title.lower():
            continue
        url = decode_google_news_link(e.link)
        if not url or "call-transcript" not in url or f"-{ticker}-" not in url:
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append((url, pub, e.title))
    return sorted(out, key=lambda t: t[1], reverse=True)


def extract_transcript(url: str) -> str | None:
    html = get(url, timeout=30, sleep=3.0).text
    return trafilatura.extract(html, include_comments=False, include_tables=False, favor_recall=True)


def _quarter_from_title(title: str) -> str | None:
    m = re.search(r"\bQ([1-4])\s+(\d{4})\b", title)
    return f"Q{m.group(1)} {m.group(2)}" if m else None


def add_url(customer: dict, con, url: str, published: str | None = None) -> bool:
    """Manually add a transcript by URL (for quarters discovery missed)."""
    text = extract_transcript(url)
    if not text:
        return False
    title = text.splitlines()[0][:120]
    _, new = upsert_document(con, customer=customer["slug"], source_type="transcript", source_tier=2,
                             title=title, url=url, published_at=published, text=text,
                             meta={"provider": "motley_fool", "quarter": _quarter_from_title(text[:300])})
    return new


def fetch_fmp(customer: dict, con, cfg: dict) -> dict:
    key = os.environ.get("FMP_API_KEY")
    if not key:
        return {"seen": 0, "new": 0, "note": "FMP_API_KEY not set"}
    url = f"https://financialmodelingprep.com/stable/earning-call-transcript-latest?symbol={customer['ticker']}&apikey={key}"
    data = get(url).json()
    stats = {"seen": 0, "new": 0}
    for t in data[: cfg.get("max_transcripts", 5)]:
        text = t.get("content") or ""
        if len(text) < 1000:
            continue
        title = f"{customer['name']} Q{t.get('quarter')} {t.get('year')} earnings call (FMP)"
        _, new = upsert_document(con, customer=customer["slug"], source_type="transcript", source_tier=2,
                                 title=title, url=url.split("&apikey")[0], published_at=str(t.get("date", ""))[:10],
                                 text=text, meta={"provider": "fmp", "quarter": f"Q{t.get('quarter')} {t.get('year')}"})
        stats["seen"] += 1
        stats["new"] += int(new)
    return stats


def fetch(customer: dict, con, cfg: dict) -> dict:
    if cfg.get("provider") == "fmp":
        return fetch_fmp(customer, con, cfg)
    since = cutoff(cfg.get("since_days", 400))
    stats = {"seen": 0, "new": 0, "failed": 0}
    for url, pub, title in discover_fool_urls(customer, since)[: cfg.get("max_transcripts", 5)]:
        if con.execute("SELECT 1 FROM documents WHERE url=?", (url,)).fetchone():
            stats["seen"] += 1
            continue
        try:
            text = extract_transcript(url)
        except Exception as e:  # fool.com resets connections after a few rapid fetches
            print(f"  transcript fetch failed for {url}: {type(e).__name__}", flush=True)
            stats["failed"] += 1
            continue
        if not text or len(text) < 5000:
            stats["failed"] += 1
            continue
        _, new = upsert_document(con, customer=customer["slug"], source_type="transcript", source_tier=2,
                                 title=title.replace(" - The Motley Fool", ""), url=url, published_at=pub,
                                 text=text, meta={"provider": "motley_fool", "quarter": _quarter_from_title(title)})
        stats["seen"] += 1
        stats["new"] += int(new)
    return stats
