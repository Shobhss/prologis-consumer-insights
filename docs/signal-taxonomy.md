# Signal taxonomy (v1, approved by Sarah Logman 2026-10-02)

The extractor may only assign one of these codes. The definitions below are the
same text the model sees, so editing `pipeline/taxonomy.py` changes both.

| Code | Signal type | Definition |
|---|---|---|
| FOOT+ | Footprint expansion | Opening, building, leasing or acquiring logistics facilities; adding square footage; new fulfillment/distribution/delivery sites. |
| FOOT- | Footprint contraction | Closing, subleasing, exiting or consolidating facilities; delaying or cancelling planned sites; reducing square footage. |
| NET | Network strategy shift | Changes to how the logistics network is designed: regionalization, same-day hubs, inbound cross-docks, consolidation of nodes, insourcing vs 3PL. |
| CAPEX | Capex guidance | Stated or changed capital expenditure plans and the share going to fulfillment, logistics or infrastructure. |
| OWN/LEASE | Own vs lease posture | Statements or numbers on owned vs leased property, land purchases, build-to-suit, sale-leaseback, lease term or commitment changes. |
| GEO | Geographic shift | Entering or exiting specific metros, states or countries; nearshoring; port or trade-lane changes that move where space is needed. |
| DATACENTER | Data center demand | Data center builds, land/power acquisitions, or growth in data center suppliers (electrical, cooling, plumbing, equipment) that could use industrial space. |
| SECT | Sector demand trend | Category-level demand changes relevant to industrial space: grocery, cold chain, EV, returns/reverse logistics, AI hardware, healthcare. |
| STRESS | Financial stress on real estate | Impairments, lease terminations, restructuring charges, subleasing, headcount cuts tied to facilities, going-concern language. |
| AUTO | Automation and labor | Robotics or automation rollouts, labor cost or availability issues, that change building specs or headcount per facility. |
| M&A | M&A / portfolio change | Acquisitions, divestitures or partnerships that add or remove a logistics footprint. |
| ENERGY | Power and sustainability (peripheral) | On-site solar, EV fleet charging, grid or power constraints at facilities. Relevant to Prologis Essentials; secondary to real estate. |

## Fields on every signal

| Field | Meaning | Who sets it |
|---|---|---|
| headline | One factual sentence, max 25 words | Model |
| quote | Verbatim text from the source, 10-60 words | Model, verified in code |
| quote_verified | 1 if the quote is a substring of the source chunk | Code |
| geography | Metro, state or country named, else "unspecified" | Model |
| magnitude | Number with unit (sq ft, $, facilities, %) or "unspecified" | Model |
| timeframe | When it happens or happened | Model |
| direction | expansion, contraction, shift, neutral | Model |
| specificity | 3 place and number or date; 2 place or number; 1 directional only | Model |
| source_reliability | 3 filings, transcripts, wire or company newsroom; 2 established trade press; 1 other | Code, from source tier and domain |
| corroboration | Distinct source documents with the same code and geography | Code |
| confidence | 0.45 specificity/3 + 0.40 reliability/3 + 0.15 min(corroboration,3)/3 | Code |
| implication | What it means for Prologis, hedged to confidence | Model, separate step |
| go_do | One concrete action naming a team, or "None; monitor." | Model, separate step |
| audience | c-suite, account_team, leasing, all | Model, separate step |
| horizon | now (brief or act this cycle) or watch (2+ quarters) | Model, separate step |

## Confidence bands used in the brief

| Band | Range | How it reads |
|---|---|---|
| High | 0.80 to 1.00 | Stated plainly |
| Medium | 0.60 to 0.79 | "likely", "suggests" |
| Low | below 0.60 | "possible", "worth watching" |

## What is deliberately excluded

Revenue, margins, stock moves, product launches, AWS results and other general
business news, unless the text states a real-estate consequence. Sarah's team
already receives general news monitoring; this pipeline is for signals that
change demand for industrial space.
