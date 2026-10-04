"""Source fetchers. Each exposes `fetch(customer: dict, con, cfg: dict) -> dict` and
writes documents into the SQLite store. Fetchers are idempotent: re-running
skips documents already stored (dedupe on URL + content hash)."""
