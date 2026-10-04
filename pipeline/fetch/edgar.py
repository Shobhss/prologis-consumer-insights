"""SEC EDGAR fetcher: 10-K, 10-Q and 8-K filings for a customer by CIK.

What it pulls
-------------
* The filing index from https://data.sec.gov/submissions/CIK##########.json
* The primary document of each matching filing (HTML -> text)
* For 8-Ks, the EX-99.* exhibits (earnings press releases, announcements),
  because the 8-K body itself is usually a one-paragraph cover.

Why it matters
--------------
Item 2 (Properties) and the lease footnote in the 10-K are the most reliable
footprint signals available: square footage by segment, owned vs leased,
operating lease commitments. These are split out later in normalize.py.

Rules
-----
SEC fair-access policy: max 10 requests/second and a descriptive User-Agent.
We sleep 0.15s between requests. No API key needed.

Inputs : customer dict (needs `cik`), config `edgar` block
Outputs: documents rows with source_type in {10-K, 10-Q, 8-K}, tier 1
Known gaps: XBRL numeric facts API (companyfacts) is not yet used; it would give
clean lease-commitment time series without text parsing.
"""
from __future__ import annotations

import time

from ..config import SEC_USER_AGENT
from ..store import upsert_document
from .util import cutoff, get, html_to_text

SEC_HEADERS = {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
SLEEP = 0.15


def _sec_get(url: str):
    return get(url, headers=SEC_HEADERS, sleep=SLEEP)


def list_filings(cik: str, forms: tuple[str, ...], since: str) -> list[dict]:
    """Return recent filings for a CIK matching `forms` filed on/after `since` (ISO date)."""
    data = _sec_get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()
    rec = data["filings"]["recent"]
    out = []
    for i, form in enumerate(rec["form"]):
        if form not in forms or rec["filingDate"][i] < since:
            continue
        out.append({
            "form": form,
            "accession": rec["accessionNumber"][i],
            "filing_date": rec["filingDate"][i],
            "report_date": rec["reportDate"][i],
            "primary_doc": rec["primaryDocument"][i],
            "description": rec["primaryDocDescription"][i],
            "items": rec.get("items", [""] * len(rec["form"]))[i],
        })
    return out


def _archive_base(cik: str, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"


def list_exhibits(cik: str, accession: str) -> list[str]:
    """File names of EX-99 exhibits in a filing folder."""
    idx = _sec_get(f"{_archive_base(cik, accession)}/index.json").json()
    names = [it["name"] for it in idx["directory"]["item"]]
    return [n for n in names if "ex99" in n.lower() and n.lower().endswith((".htm", ".html"))]


def fetch(customer: dict, con, cfg: dict) -> dict:
    """Fetch all configured filings for `customer` into the store. Returns counts."""
    cik = customer["cik"]
    forms = tuple(cfg.get("forms", ["10-K", "10-Q", "8-K"]))
    since = cutoff(cfg.get("since_days", 400))
    stats = {"seen": 0, "new": 0, "exhibits": 0}
    for f in list_filings(cik, forms, since):
        base = _archive_base(cik, f["accession"])
        url = f"{base}/{f['primary_doc']}"
        text = html_to_text(_sec_get(url).text)
        title = f"{customer['name']} {f['form']} filed {f['filing_date']} (period {f['report_date']})"
        meta = {k: f[k] for k in ("form", "accession", "filing_date", "report_date", "items")}
        _, new = upsert_document(con, customer=customer["slug"], source_type=f["form"], source_tier=1,
                                 title=title, url=url, published_at=f["filing_date"], text=text, meta=meta)
        stats["seen"] += 1
        stats["new"] += int(new)
        if f["form"] == "8-K" and cfg.get("include_8k_exhibits", True):
            for name in list_exhibits(cik, f["accession"]):
                ex_url = f"{base}/{name}"
                ex_text = html_to_text(_sec_get(ex_url).text)
                if len(ex_text) < 500:
                    continue
                _, new = upsert_document(
                    con, customer=customer["slug"], source_type="8-K", source_tier=1,
                    title=f"{title} exhibit {name}", url=ex_url, published_at=f["filing_date"],
                    text=ex_text, meta={**meta, "exhibit": name})
                stats["exhibits"] += 1
                stats["new"] += int(new)
    return stats
