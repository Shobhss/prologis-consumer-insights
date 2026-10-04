"""Thin wrapper around the Anthropic SDK used by extract.py and implicate.py.

Credentials: `anthropic.Anthropic()` reads ANTHROPIC_API_KEY from the environment
(.env is loaded by pipeline.config). Nothing is hardcoded.

Design choices
--------------
* Structured outputs via `output_config.format` so every response is valid JSON
  matching our schema; no regex parsing of model text.
* Prompt caching on the system prompt (taxonomy + rules) because it is identical
  across hundreds of chunk calls.
* Server-side fallback enabled so a safety-classifier refusal on one chunk routes
  to a fallback model instead of failing the batch.
* Adaptive thinking is the model default; effort is set per call.
"""
from __future__ import annotations

import json
import time

import anthropic

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def structured_call(*, model: str, system: str, user: str, schema: dict, effort: str = "medium",
                    max_tokens: int = 8000, retries: int = 3) -> tuple[dict | None, dict]:
    """Call Claude and return (parsed_json_or_None, usage_dict)."""
    for attempt in range(retries):
        try:
            resp = client().beta.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            usage = {"input": resp.usage.input_tokens, "output": resp.usage.output_tokens,
                     "cache_read": getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
                     "model": getattr(resp, "model", model)}
            if resp.stop_reason == "refusal":
                return None, {**usage, "refusal": True}
            text = next((b.text for b in resp.content if b.type == "text"), None)
            if not text:
                return None, usage
            return json.loads(text), usage
        except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError):
            time.sleep(5 * (attempt + 1))
        except anthropic.APIStatusError as e:
            raise RuntimeError(f"Claude API error {e.status_code}: {e.message}") from e
    return None, {"input": 0, "output": 0, "cache_read": 0, "model": model, "gave_up": True}
