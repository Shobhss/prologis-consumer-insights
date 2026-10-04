"""HTTP helpers shared by fetchers: polite requests, HTML to text, Google News link decoding."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from ..config import HTTP_USER_AGENT

_session = requests.Session()
_session.headers.update({"User-Agent": HTTP_USER_AGENT})


def get(url: str, *, headers: dict | None = None, timeout: int = 30, sleep: float = 0.0) -> requests.Response:
    """GET with a browser User-Agent and optional politeness delay."""
    if sleep:
        time.sleep(sleep)
    r = _session.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r


def html_to_text(html: str) -> str:
    """Convert HTML to readable plain text. Table rows become ' | '-joined lines so
    numeric tables (e.g. 10-K Item 2 square footage) stay parseable."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    for tag in soup.find_all(re.compile(r"^ix:header$")):
        tag.decompose()
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        tr.replace_with(soup.new_string(" | ".join(cells) + "\n") if cells else soup.new_string(""))
    text = soup.get_text("\n")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def domain(url: str) -> str:
    d = urlparse(url).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def parse_date(s: str | None) -> str | None:
    """Best-effort RFC-2822 / ISO date parsing to ISO date string."""
    if not s:
        return None
    try:
        return parsedate_to_datetime(s).date().isoformat()
    except Exception:
        pass
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None


def cutoff(since_days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=since_days)).date().isoformat()


def decode_google_news_link(link: str) -> str | None:
    """Resolve a news.google.com/rss/articles/... link to the publisher URL.

    Google no longer redirects server-side; the article page carries a signature
    and timestamp that the batchexecute endpoint exchanges for the real URL.
    Returns None if decoding fails. Known to work as of 2026-10."""
    try:
        art_id = link.split("/articles/")[1].split("?")[0]
        page = get(f"https://news.google.com/articles/{art_id}", timeout=20).text
        sg = re.search(r'data-n-a-sg="([^"]+)"', page)
        ts = re.search(r'data-n-a-ts="([^"]+)"', page)
        if not (sg and ts):
            return None
        inner = ["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1,
                 None, None, None, None, None, 0, 1], "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
                 art_id, ts.group(1), sg.group(1)]
        payload = [[["Fbv4je", json.dumps(inner), None, "generic"]]]
        resp = _session.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            data={"f.req": json.dumps(payload)}, timeout=20,
        ).text
        m = re.search(r'"(https?://[^"\\]+)', resp.split("\n", 2)[-1])
        return m.group(1) if m else None
    except Exception:
        return None


def google_news_rss(query: str) -> str:
    from urllib.parse import quote_plus
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
