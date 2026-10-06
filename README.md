# Prologis Customer Intelligence Pipeline

Prototype that turns public signals about Prologis customers into decision-ready
intelligence: grounded signals, Prologis-specific implications, and a brief in
the format Sarah Logman's team already uses.

Built for the Prologis capstone (Sep to Dec 2026). Client contact: Sarah Logman,
Head of Customer Intelligence. Pilot customer: Amazon.

## What it does

```
fetch  ->  normalize  ->  prefilter  ->  extract  ->  implicate  ->  report
 SEC         split          keyword       Claude        Claude        Excel +
 calls       chunk          screen        + quote       + Prologis    Markdown
 news                                     check         context       brief
```

1. **fetch**: SEC filings (10-K, 10-Q, 8-K with exhibits), earnings call
   transcripts, trade press and Google News, for one customer at a time.
2. **normalize**: split filings by Item, transcripts by speaker, everything into
   ~1,500-token chunks.
3. **prefilter**: keyword screen so only real-estate-relevant chunks go to the LLM.
4. **extract**: Claude pulls signals with a verbatim quote; code verifies the
   quote exists in the source. Unverified rows are kept for audit but never reported.
5. **implicate**: a second Claude pass writes what each signal means for
   Prologis, a go-do for a named team, audience, and horizon, hedged to confidence.
6. **report**: `signals.xlsx` and `brief.md` under `outputs/<customer>/<date>/`, and
   a refreshed `outputs/dashboard/index.html` covering every customer.

The separation of extract and implicate is deliberate. It is the fix for the
"AI takes leaps" problem Sarah described: facts are grounded first, reasoning
happens second on verified facts only.

## Quickstart

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # add ANTHROPIC_API_KEY
.venv/bin/python -m pipeline.cli run --customer amazon
```

Stages can be run one at a time; each is idempotent and skips work already done:

```bash
.venv/bin/python -m pipeline.cli fetch     --customer amazon --only edgar,transcripts
.venv/bin/python -m pipeline.cli normalize --customer amazon
.venv/bin/python -m pipeline.cli prefilter --customer amazon
.venv/bin/python -m pipeline.cli extract   --customer amazon --limit 20 --sections "Item 2,Lease Note"
.venv/bin/python -m pipeline.cli implicate --customer amazon
.venv/bin/python -m pipeline.cli report    --customer amazon --min-confidence 0.6
.venv/bin/python -m pipeline.cli status    --customer amazon
```

Import signals produced outside the API stage (a reviewer, or Claude in a Claude Code session)
through the same quote verification:

```bash
.venv/bin/python -m pipeline.import_signals docs/samples/amazon_signals_2026-10-05.json
```

Record reviewer feedback on a signal (feeds the learning loop):

```bash
.venv/bin/python -m pipeline.cli feedback --signal-id abc123 --verdict useful --note "used in exec brief"
```

Run tests:

```bash
.venv/bin/python -m unittest discover tests
```

## Dashboard

`outputs/dashboard/index.html` is a single self-contained page: KPI tiles, signals
by type, the actions to take this cycle, and a filterable table with the insight,
the source link, what it means for Prologis, and the go-do. Quotes expand inline.
Light and dark mode. Styled with prologis.com's design tokens: Inter type, the
`--c-teal` / `--c-green` / `--c-blue` palette, the near-black header band, white
square-cornered cards and the cyan call-to-action accent.

Regenerate with `python -m pipeline.cli dashboard` (the `report` stage also does it).

Deploy from the repo. The root `vercel.json` tells Vercel to skip install and build
(the repo also contains Python, which Vercel would otherwise try to run as a
function) and to serve `outputs/dashboard` as static files. Connect the GitHub repo
to a Vercel project with default settings, or from the CLI:

```bash
vercel --prod
```

The page sets `noindex` so it stays out of search engines. Commit a regenerated
`outputs/dashboard/index.html` to publish new signals.

## Adding a customer

Add one block to `config/customers.yaml` and run the pipeline with its slug.
Nothing else changes.

```yaml
  - name: GXO Logistics
    slug: gxo
    cik: "0001852244"          # SEC CIK, 10 digits. Look up at sec.gov/cgi-bin/browse-edgar
    ticker: GXO
    aliases: ["GXO", "GXO Logistics"]
    news_queries: ["GXO warehouse", "GXO Logistics contract", "GXO automation"]
```

Public companies only. Private customers have no filings or calls and Sarah
advised against chasing them.

## Repository layout

| Path | Purpose |
|---|---|
| `pipeline/fetch/edgar.py` | SEC filings by CIK |
| `pipeline/fetch/transcripts.py` | Earnings call transcripts by ticker |
| `pipeline/fetch/news.py` | Trade press RSS and Google News |
| `pipeline/fetch/util.py` | HTTP helpers, HTML to text, Google News link decoding |
| `pipeline/normalize.py` | Section splitting and chunking |
| `pipeline/prefilter.py` | Keyword relevance screen |
| `pipeline/taxonomy.py` | The 12 signal types (single source of truth) |
| `pipeline/llm.py` | Anthropic SDK wrapper: structured outputs, caching, fallbacks |
| `pipeline/extract.py` | Signal extraction and quote verification |
| `pipeline/import_signals.py` | Import externally produced signals through the same checks |
| `pipeline/implicate.py` | Implications, go-dos, audience, horizon |
| `pipeline/report.py` | Excel and Markdown outputs |
| `pipeline/dashboard.py` + `templates/dashboard.html` | Static HTML dashboard, all customers |
| `pipeline/store.py` | SQLite schema |
| `pipeline/cli.py` | Entry point |
| `config/customers.yaml` | Customer list |
| `config/sources.yaml` | Feeds, tiers, blocked domains |
| `config/prologis_context.md` | Prologis facts injected into the implication prompt |
| `docs/` | Plan, signal taxonomy, source catalog, sample signal sets |
| `tests/` | Unit tests for grounding, chunking, transcript parsing |
| `data/` | SQLite store and raw text (git-ignored) |
| `outputs/` | Generated reports (git-ignored except structure) |

## Confidence

Computed in code, never by the model:

```
confidence = 0.45 * specificity/3 + 0.40 * source_reliability/3 + 0.15 * min(corroboration,3)/3
```

Specificity is the model's 1 to 3 rating of how concrete the fact is.
Reliability comes from the source tier (filings and calls 3, trade press 2,
other 1). Corroboration counts distinct documents reporting the same signal
type in the same geography. See `docs/signal-taxonomy.md`.

## Cost

Only prefiltered chunks are sent. The system prompt is cached. For the Amazon
pilot (about 150 relevant chunks, roughly 250K input tokens) a full extract and
implicate run on Claude Opus 5.5 is in the range of $2 to $4. Change the model
with `EXTRACT_MODEL` / `IMPLICATE_MODEL` in `.env`.

## Cadence

Sarah asked for every two weeks to monthly. Re-running `fetch` only pulls new
documents, so a biweekly cron on `run --customer <slug>` is enough.

## Documents

- `docs/PLAN-external-data.md`: the plan Sarah approved on 2026-10-02
- `docs/signal-taxonomy.md`: signal types and field definitions
- `docs/sources.md`: every source, access method, cost and status
- `HANDOFF.md`: what worked, what did not, open items
