# Sources

Ranked by signal density for industrial real estate. Tier drives the
`source_reliability` input to confidence. Everything here is free unless marked.

| Tier | Source | What we take | Access | Cost | Reliability | Status |
|---|---|---|---|---|---|---|
| 1 | SEC EDGAR 10-K | Item 1A risks, Item 2 properties, Item 7 MD&A, lease note | `data.sec.gov` JSON + Archives HTML, no key | Free | 3 | Live |
| 1 | SEC EDGAR 10-Q | Part I Items 1-3, Part II Item 1A, lease note | Same | Free | 3 | Live |
| 1 | SEC EDGAR 8-K + EX-99 exhibits | Earnings releases, material announcements | Same | Free | 3 | Live |
| 2 | Earnings call transcripts | Prepared remarks and Q&A, split by speaker | Motley Fool via Google News discovery; FMP optional | Free | 3 | Live, 3 of 4 quarters |
| 3 | Company newsroom and wire services | Facility openings, regional investments | Via Google News; dedicated RSS not yet wired | Free | 3 | Partial |
| 3 | State WARN Act notices | Closures and layoffs with exact addresses | Per-state web pages | Free | 3 | Not built |
| 4 | Trade press RSS | Supply Chain Dive, FreightWaves, DC Velocity, Logistics Management, MDM, Bisnow, GlobeSt | RSS, filtered by customer aliases | Free | 2 | Live |
| 4 | Google News search | Customer-specific keyword queries | RSS + link decoding | Free | 1 to 2 by domain | Live |
| 5 | Competitor REIT calls and broker reports | Market-level demand commentary | Same transcript path by ticker | Free | 2 | Not built |

## Blocked sources

Reddit, Substack, Medium, Quora, social networks, YouTube. Seeking Alpha is
blocked because its links are paywalled and reviewers cannot open them.

## Rate limits and etiquette

- SEC: 10 requests/second max, descriptive User-Agent with email. We sleep 150 ms.
- Motley Fool: resets connections after a few rapid fetches. We sleep 3 s and skip on failure.
- Google News: link decoding is two requests per article. We cap at 15 per query.

## Paid options considered and not used

- Financial Modeling Prep transcripts: free tier has been unreliable; code path exists if a key is supplied.
- Seeking Alpha, CoStar, Panjiva/ImportGenius: paid, not needed for the pilot.
