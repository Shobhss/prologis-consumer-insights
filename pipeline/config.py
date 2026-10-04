"""Shared paths, constants and customer config loading."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
OUT_DIR = ROOT / "outputs"
DB_PATH = DATA_DIR / "pipeline.sqlite"

# SEC requires a descriptive User-Agent with contact info.
SEC_USER_AGENT = os.environ.get(
    "SEC_USER_AGENT", "PrologisCapstone research bot sdixit@together.ai"
)
HTTP_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

EXTRACT_MODEL = os.environ.get("EXTRACT_MODEL", "claude-opus-5-5")
IMPLICATE_MODEL = os.environ.get("IMPLICATE_MODEL", "claude-opus-5-5")


def load_customers(path: Path | None = None) -> list[dict]:
    path = path or ROOT / "config" / "customers.yaml"
    with open(path) as f:
        return yaml.safe_load(f)["customers"]


def get_customer(slug: str) -> dict:
    for c in load_customers():
        if c["slug"] == slug:
            return c
    raise KeyError(f"unknown customer slug: {slug}")
