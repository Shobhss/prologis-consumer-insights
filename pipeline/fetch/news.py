"""News fetcher: trade press RSS feeds plus Google News keyword searches.

Two discovery paths
-------------------
1. Trade feeds (config/sources.yaml): every item is scanned for the customer's
   aliases in title or summary. Reliable, low volume, logistics-specific.
2. Google News RSS searches using the customer's `news_queries`. High recall,
   mixed quality; links are decoded to publisher URLs and blocked domains dropped.

For each article we try to extract full text with trafilatura. If that fails
(paywall, JS-only page), we keep the RSS title + summary and mark
meta.full_text=false so the extraction step treats it as weaker evidence.

Inputs : customer dict (needs `aliases`, `news_queries`), config `news` block
Outputs: documents rows with source_type=news, tier 4 (tier 3 if the domain is the
         company's own newsroom or a wire service)
Known gaps: no WARN Act notices yet; no company IR newsroom RSS yet. Both are
listed in HANDOFF.md.
"""
from __future__ import annotations

import re

import feedparser
import trafilatura

from ..store import upsert_document
from .util import cutoff, decode_google_news_link, domain, get, google_news_rss, parse_date

WIRE_OR_OWN = ("prnewswire.com", "businesswire.com", "aboutamazon.com", "sec.gov")


def _mentions(text: str, aliases: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(a)}\b", text, re.I) for a in aliases)


def _parse_feed(url: str):
    """feedparser has no network timeout; fetch with requests first."""
    try:
        return feedparser.parse(get(url, timeout=15).content)
    except Exception as e:
        print(f"  feed failed {url}: {type(e).__name__}", flush=True)
        return feedparser.parse(b"")


def _article_text(url: str) -> str | None:
    try:
        html = get(url, timeout=12, sleep=0.5).text
    except Exception:
        return None
    try:
        return trafilatura.extract(html, include_comments=False, favor_recall=True)
    except Exception:
        return None


def _store(con, customer, *, title, url, published, summary, cfg) -> bool:
    d = domain(url)
    if any(d.endswith(b) for b in cfg.get("blocked_domains", [])):
        return False
    text = _article_text(url)
    full = bool(text and len(text) > 800)
    if not full:
        text = f"{title}\n\n{summary or ''}".strip()
    tier = 3 if d.endswith(WIRE_OR_OWN) else 4
    reliability = 3 if d.endswith(WIRE_OR_OWN) else (2 if any(d.endswith(h) for h in cfg.get("high_reliability_domains", [])) else 1)
    _, new = upsert_document(con, customer=customer["slug"], source_type="news", source_tier=tier,
                             title=title, url=url, published_at=published, text=text,
                             meta={"domain": d, "full_text": full, "reliability": reliability})
    con.commit()  # persist as we go; a long run may be interrupted
    return new


def fetch_trade_feeds(customer: dict, con, cfg: dict) -> dict:
    since = cutoff(cfg.get("since_days", 180))
    stats = {"seen": 0, "new": 0}
    for feed_cfg in cfg.get("trade_feeds", []):
        feed = _parse_feed(feed_cfg["url"])
        print(f"  [{feed_cfg['name']}] {len(feed.entries)} items", flush=True)
        for e in feed.entries:
            pub = parse_date(e.get("published") or e.get("updated"))
            if pub and pub < since:
                continue
            blob = f"{e.get('title','')} {e.get('summary','')}"
            if not _mentions(blob, customer["aliases"]):
                continue
            stats["seen"] += 1
            stats["new"] += int(_store(con, customer, title=e.title, url=e.link, published=pub,
                                       summary=re.sub("<[^>]+>", "", e.get("summary", "")), cfg=cfg))
    return stats


def fetch_google_news(customer: dict, con, cfg: dict) -> dict:
    since = cutoff(cfg.get("since_days", 180))
    cap = cfg.get("max_per_query", 30)
    stats = {"seen": 0, "new": 0, "undecoded": 0}
    seen_urls = set()
    for q in customer.get("news_queries", []):
        feed = _parse_feed(google_news_rss(q))
        print(f"  [google news] '{q}': {len(feed.entries)} items", flush=True)
        n = 0
        for e in feed.entries:
            if n >= cap:
                break
            pub = parse_date(e.get("published"))
            if pub and pub < since:
                continue
            url = decode_google_news_link(e.link)
            if not url:
                stats["undecoded"] += 1
                continue
            if url in seen_urls or "call-transcript" in url:
                continue
            if con.execute("SELECT 1 FROM documents WHERE url=?", (url,)).fetchone():
                seen_urls.add(url)
                n += 1
                continue
            seen_urls.add(url)
            title = re.sub(r"\s+-\s+[^-]+$", "", e.title)  # strip trailing " - Publisher"
            n += 1
            stats["seen"] += 1
            stats["new"] += int(_store(con, customer, title=title, url=url, published=pub,
                                       summary=re.sub("<[^>]+>", "", e.get("summary", "")), cfg=cfg))
    return stats


def fetch(customer: dict, con, cfg: dict) -> dict:
    out = {"trade_feeds": fetch_trade_feeds(customer, con, cfg)}
    if cfg.get("google_news", True):
        out["google_news"] = fetch_google_news(customer, con, cfg)
    return out
