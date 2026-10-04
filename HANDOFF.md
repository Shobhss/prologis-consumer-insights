# Handoff notes

Running log for teammates picking this up. Newest first.

## 2026-10-03 (Shobhit): pipeline built, Amazon corpus collected, LLM stages ready

### State
- All six stages are written and importable. Fetch, normalize and prefilter have
  run on Amazon. Extract and implicate have **not** run yet: no `ANTHROPIC_API_KEY`
  on this machine. Add one to `.env` and run
  `python -m pipeline.cli extract --customer amazon --limit 10` as a smoke test.
- Amazon corpus in `data/pipeline.sqlite`: 1 x 10-K, 3 x 10-Q, 28 x 8-K documents
  (16 bodies + 12 exhibits), 3 earnings transcripts (Q4 2025, Q1 2026, Q2 2026),
  news articles still being collected at time of writing (see `status`).
- 298 chunks, 150 marked relevant by the prefilter.

### What worked
- **EDGAR** is the cleanest source. Free, fast, structured. Item split works for
  both 10-K and 10-Q (10-Q needs Part-aware labels because Item numbers repeat).
- **Motley Fool transcripts** are discoverable via Google News RSS restricted to
  `site:fool.com`, then decoding the Google redirect. Their 2026 layout prepends
  an AI summary (TAKEAWAYS / RISKS / SUMMARY) which we drop; only text after
  "Full Conference Call Transcript" is used.
- **Google News link decoding** works with the `batchexecute` trick in
  `fetch/util.py`. If Google changes this, fall back to publisher RSS feeds.
- **Table rows to " | " lines** in `html_to_text` keeps 10-K square-footage
  tables parseable.

### What did not work or needs care
- Motley Fool resets the connection after ~3 rapid fetches. We sleep 3 s and
  continue on failure; Q3 2025 transcript was missed and can be added with
  `transcripts.add_url()`.
- `feedparser.parse(url)` has no timeout and hung the first news run. Feeds are
  now fetched with `requests` first. Logistics Management's feed returns 0 items.
- Long fetches get killed if run as background shell jobs; run them in the
  foreground or split by `--only`.
- Prefilter first pass was too loose (77% of chunks). Tightened to strong term OR
  three weak terms: now 50%. Expect to tune again after seeing extraction output.
- Python on this machine is 3.9 (no `uv`, no `pandoc`). Code avoids 3.10+ syntax.

### Open items, by priority
1. **Run extract + implicate on Amazon** and review the signal table. Check the
   unverified-quote rate; if above ~10%, tighten the quote instruction.
2. **Hand-label a 20-row Amazon test set** (signal / not signal) to measure
   precision and tune the prefilter and prompt. This is the eval Sarah's "AI
   takes leaps" complaint needs.
3. **Add a second, smaller customer** (GXO or Home Depot from Sarah's list) to
   prove the YAML-only onboarding and to see how sparse sources behave.
4. **WARN Act notices**: exact addresses for closures. Per-state pages; start
   with CA, TX, NJ, IL, OH, PA, GA, WA.
5. **Company newsroom RSS** (aboutamazon.com) as a tier-3 source.
6. **XBRL companyfacts API** for lease-commitment time series without text parsing.
7. **Sarah's agent instructions and example reports** are still outstanding from
   her; fold her source list and report structure into `prologis_context.md`
   and `report.py` when they arrive.
8. **Feedback loop**: `feedback` table exists; next step is to use useful /
   not_useful rows as few-shot examples in the extraction prompt.

### Decisions made
- External sources only; internal Salesforce data deferred per Sarah.
- Public companies only.
- Extract and implicate are separate LLM calls, by design.
- Confidence is computed in code from specificity, reliability and corroboration.
- Opus 5.5 for both LLM stages; cost for the Amazon pilot is a few dollars.
