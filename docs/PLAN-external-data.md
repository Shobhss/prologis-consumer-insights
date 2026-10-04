# Prologis Customer Intelligence: External Data Extraction Plan

Pilot customer: **Amazon**. Scope: dark-green customers only (Amazon, Walmart, DHL, PepsiCo, GXO, plus the rest of Sarah's list when it arrives).

## 1. What we are extracting

Not "everything about Amazon." Only evidence that changes demand for industrial real estate. Every extracted signal must carry a verbatim quote and a clickable source URL.

### Signal taxonomy v1 (for Sarah to react to)

| Code | Signal type | Example | Why Prologis cares |
|---|---|---|---|
| FOOT+ / FOOT- | Footprint expansion / contraction | "opening 3 new fulfillment centers in Texas", "closing 8 delivery stations" | Direct space demand, by market |
| NET | Network strategy shift | regionalization, same-day hubs, consolidation, inbound cross-dock redesign | Changes building type, size and location mix |
| CAPEX | Capex guidance change | "capex will be ~$X B, primarily fulfillment and AWS" | Leading indicator 2–6 quarters out |
| OWN/LEASE | Own vs. lease posture | land purchases, build-to-suit, sale-leaseback | Whether demand flows to Prologis or bypasses it |
| GEO | Geographic shift | new metros, nearshoring (Mexico), port shifts | Where to hold land / make offers |
| SECT | Sector demand trend | AI infra suppliers, EV, cold storage, reverse logistics | Portfolio and prospecting themes |
| STRESS | Financial stress in real estate | impairments, sublease, lease terminations, restructuring | Vacancy / credit risk |
| AUTO | Automation & labor | robotics rollout, headcount cuts per facility | Higher clear heights, power needs, fewer but larger boxes |
| ENERGY | Power / sustainability | on-site solar, EV fleet charging, microgrids | Prologis Essentials / energy business |
| M&A | Acquisitions / divestitures | acquiring a 3PL, exiting a business | Consolidated or vanished footprint |

Fields per signal:
`customer, date, source_type, source_url, quote, signal_code, geography, magnitude (sq ft / $ / facility count), timeframe, direction, specificity (1–3), source_reliability (1–3), corroboration_count, confidence, implication, go_do, audience (C-suite / leasing / account)`

Confidence rule: `confidence = f(specificity, source_reliability, corroboration)`. A named market plus a number from a 10-K is high. An analyst's inference in trade press is low, and we say so.

## 2. Sources, ranked by signal density

### Tier 1: Primary filings (highest reliability, structured, free)
**SEC EDGAR**: 10-K, 10-Q, 8-K.
- Item 2 *Properties*: square footage by segment, owned vs. leased, by year. Year-over-year deltas are a signal on their own.
- Item 7 *MD&A*: capex plans, fulfillment network commentary.
- Item 1A *Risk factors*: new risks about facilities, labor, energy.
- Lease footnote (ASC 842): operating lease commitments and weighted-average remaining term. Rising commitments = growing leased footprint.
- 8-K Item 2.02 (earnings) and 8.01 (other events) for announcements between quarters.
- Access: `data.sec.gov/submissions/CIK##########.json` for the filing index, full-text search at `efts.sec.gov/LATEST/search-index`, XBRL company facts API for numeric series. Requires a User-Agent header. No key.

### Tier 2: Earnings calls (high reliability, richest forward-looking language)
- Prepared remarks + Q&A, last 4–8 quarters. Q&A is where analysts ask about capex and network.
- Sources: company IR webcasts, Motley Fool free transcripts, Financial Modeling Prep transcript endpoint (free tier), API Ninjas. Seeking Alpha is paywalled; avoid.
- Split by speaker so quotes attribute to CFO vs. analyst.

### Tier 3: Company announcements (high reliability, very specific on location)
- IR newsroom RSS, PR Newswire, Business Wire.
- Facility openings, closures, regional investments ("$X B in Ohio"), sustainability reports.
- **State WARN Act notices**: legally required layoff/closure filings with exact addresses and dates. Very specific, underused. Each state publishes a page or CSV.

### Tier 4: Trade press (medium reliability, fastest)
- Supply Chain Dive, Logistics Management, DC Velocity, FreightWaves, Modern Distribution Management, Bisnow, GlobeSt, CoStar News, WSJ Logistics Report.
- Access via RSS feeds, Google News RSS per customer, or GDELT. Extract article text with `trafilatura`.
- Treat as corroboration for Tier 1–3, or as an early lead that needs confirmation.

### Tier 5: Market-level context (medium reliability, not customer-specific)
- Competitor REIT earnings calls (Rexford, EastGroup, First Industrial, Stag, Segro, Goodman) for what they say about tenant demand and markets.
- Broker reports (CBRE, JLL, Cushman) quarterly industrial outlooks.
- Use to build the "Prologis theme" roll-up, not customer rows.

### Stretch (only if time allows)
- Company career pages: warehouse hiring clustered in a new metro precedes a facility.
- Local planning / zoning permit filings for named projects.
- Import records (Census trade data is free; Panjiva/ImportGenius are paid).

## 3. Pipeline

```
fetch → normalize → prefilter → extract → dedupe/corroborate → score → implicate → publish → feedback
```

1. **Fetch**: one fetcher per source type. Store raw docs as JSON: `{customer, source_type, url, title, published_at, retrieved_at, content_hash, raw_text}`. Hash for dedupe. SQLite or DuckDB, one file, no server.
2. **Normalize**: strip HTML, split 10-Ks by Item, split transcripts by speaker, chunk to ~1,500 tokens with overlap.
3. **Prefilter (cheap)**: keyword and embedding filter for real-estate relevance (fulfillment, warehouse, distribution center, square feet, lease, capex, facility, logistics, data center). Cuts LLM cost roughly 10x.
4. **Extract (LLM)**: structured JSON per chunk against the schema above. Hard rules: quote must be a verbatim substring of the chunk, else drop the row. No inference fields at this stage.
5. **Dedupe / corroborate**: cluster signals describing the same event across sources. Count sources → `corroboration_count`.
6. **Score**: materiality (magnitude, customer size) × confidence. Threshold for the report.
7. **Implicate (LLM, separate step)**: given the signal plus a Prologis context doc (markets, products, strategy from Prologis's own 10-K and IR deck), write implication, go-do, and audience tag. Separate step keeps facts and reasoning apart, which is Sarah's main complaint about current tooling.
8. **Publish**: Excel/CSV table plus a one-page brief. Roll up to Prologis themes.
9. **Feedback**: reviewer marks each row useful / not / wrong. Store with the row. Use as few-shot examples and to tune scoring thresholds.

## 4. Amazon pilot corpus

- 10-K FY2025 and FY2024 (Item 2 delta), latest two 10-Qs, all 8-Ks in the last 12 months.
- Last 4 earnings call transcripts (Q3 2025 through Q2 2026).
- Amazon newsroom press releases, last 6 months, filtered to operations / regional investment.
- WARN notices naming Amazon, last 12 months, from CA, TX, NJ, IL, OH, PA, GA, WA.
- Trade press: Google News RSS for "Amazon fulfillment center" and "Amazon warehouse", last 6 months.
- Context doc: Prologis 10-K FY2025 Item 1 and latest investor presentation.

## 5. Suggested division (4 workstreams)

| Stream | Owner | Deliverable |
|---|---|---|
| A. Filings | | EDGAR fetcher + 10-K/10-Q section splitter + lease-footnote numeric series |
| B. Transcripts & announcements | | Transcript fetcher with speaker split; newsroom + WARN scrapers |
| C. News | | RSS/Google News collector + article text extraction + dedupe |
| D. Schema, prompts, eval | | Extraction schema, prompt with grounding checks, 20-row hand-labeled Amazon test set, scoring |

Integration after week 1: run A–C into D on Amazon, produce the first table.

## 6. Stack

Python 3.12, `requests`, `feedparser`, `trafilatura`, `beautifulsoup4`, `pandas`, `openpyxl`, SQLite, Claude API (`claude-sonnet-5-5` for extraction volume, `claude-fable-5-1` for the implication step). No scraping behind logins or against terms of service.

## 7. First milestone (recommended)

For Amazon only:
1. Signal taxonomy v1 (section 1) sent to Sarah for reaction.
2. Collected corpus in SQLite with source counts.
3. Signal table with ~20 rows, each with quote and link, confidence, and draft implication.
4. One-page brief in her exec format: 3 themes, each with signal → implication → go-do.

That gives her something concrete to critique in the first weekly and tests the whole pipeline end to end before scaling to other customers.
