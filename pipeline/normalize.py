"""Normalize: split documents into labeled sections and ~1,500-token chunks.

* 10-K / 10-Q  -> split by "Item N." headings so we can target Item 1A (risks),
                  Item 2 (properties), Item 7 (MD&A) and the lease note.
* transcript   -> split by speaker turn ("Name -- Title" lines), grouped into chunks
                  so each chunk carries the speaker names it contains.
* everything else -> paragraph-boundary chunks.

Chunks are stored in the `chunks` table with a `section` label. Chunk size is in
characters (6,000 chars ~ 1,500 tokens) because we do not want a tokenizer
dependency here; the extraction step tolerates the variance.
"""
from __future__ import annotations

import re

from .store import sha1

CHUNK_CHARS = 6000
OVERLAP_CHARS = 400

ITEM_RE = re.compile(r"(?im)^\s*item\s+(\d{1,2}[a-c]?)\s*[\.\:\-–—]\s*")
SPEAKER_RE = re.compile(r"(?m)^([A-Z][A-Za-z\.\'\- ]{2,60}) -- (.{2,80})$")

PART_RE = re.compile(r"(?im)^\s*part\s+(i{1,2}|[12])\b[^\n]*$")

ITEM_NAMES_10K = {
    "1": "Item 1 Business", "1a": "Item 1A Risk Factors", "1c": "Item 1C Cybersecurity",
    "2": "Item 2 Properties", "3": "Item 3 Legal", "5": "Item 5 Market", "7": "Item 7 MD&A",
    "7a": "Item 7A Market Risk", "8": "Item 8 Financial Statements", "9a": "Item 9A Controls",
}
ITEM_NAMES_10Q = {
    "i-1": "Part I Item 1 Financial Statements", "i-2": "Part I Item 2 MD&A",
    "i-3": "Part I Item 3 Market Risk", "i-4": "Part I Item 4 Controls",
    "ii-1": "Part II Item 1 Legal", "ii-1a": "Part II Item 1A Risk Factors",
    "ii-2": "Part II Item 2 Unregistered Sales", "ii-5": "Part II Item 5 Other", "ii-6": "Part II Item 6 Exhibits",
}
TRANSCRIPT_START = re.compile(r"(?im)^\s*full conference call transcript\s*$")
# "Andrew Jassy: Thank you." style (2026 Motley Fool layout)
SPEAKER_COLON_RE = re.compile(r"(?m)^((?:[A-Z][A-Za-z\.\'\-]+ ){0,3}[A-Z][A-Za-z\.\'\-]+):\s(?=[A-Z])")  # 1-4 capitalized words then ': '



def _part_at(pos: int, parts: list[tuple[int, str]]) -> str:
    cur = "i"
    for start, label in parts:
        if start <= pos:
            cur = label
    return cur


def split_filing_sections(text: str, form: str = "10-K") -> dict[str, str]:
    """Split a 10-K/10-Q into {section_label: text}.

    Filings list every Item twice (table of contents, then body). For each Item
    label we keep the occurrence with the longest span before the next heading,
    which is the body. 10-Qs repeat Item numbers in Part I and Part II, so for
    10-Qs the label is prefixed with the Part it falls under.
    """
    matches = list(ITEM_RE.finditer(text))
    if len(matches) < 4:
        return {"Full text": text}
    is_10q = form.upper().startswith("10-Q")
    parts = []
    if is_10q:
        for pm in PART_RE.finditer(text):
            lab = pm.group(1).lower().replace("1", "i").replace("2", "ii")
            parts.append((pm.start(), lab))
    names = ITEM_NAMES_10Q if is_10q else ITEM_NAMES_10K
    spans = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        label = m.group(1).lower()
        if is_10q:
            label = f"{_part_at(m.start(), parts)}-{label}"
        spans.append((label, m.start(), end))
    best: dict[str, tuple[int, int]] = {}
    for label, start, end in spans:
        if label not in best or (end - start) > (best[label][1] - best[label][0]):
            best[label] = (start, end)
    sections = {}
    for label, (start, end) in sorted(best.items(), key=lambda kv: kv[1][0]):
        body = text[start:end].strip()
        if len(body) < 300:
            continue
        sections[names.get(label, f"Item {label.upper()}")] = body
    # Lease note lives inside Item 8; pull it out as its own section when found.
    fin_key = "Item 8 Financial Statements" if not is_10q else "Part I Item 1 Financial Statements"
    fin = sections.get(fin_key, "")
    # Heading renders as "Note 4 \u2014\nLEASES" (iXBRL puts the title on its own line)
    hits = list(re.finditer(r"(?i)note\s+\d+\s*[\-\u2014\u2013:]?\s*\n?\s*leases\s*\n", fin))
    if hits:
        start = hits[-1].start()
        nxt = re.search(r"(?i)\nnote\s+\d+\s*[\-\u2014\u2013:]", fin[start + 50:])
        end = start + 50 + nxt.start() if nxt else start + 20000
        sections["Lease Note"] = fin[start:end]
    return sections or {"Full text": text}


def split_transcript(text: str) -> list[tuple[str, str]]:
    """Return [(speaker, turn_text)] from a Motley Fool transcript.

    Handles both layouts: the older "Name -- Title" heading lines and the 2026
    layout where each paragraph starts with "Name: ". The Motley Fool AI summary
    (TAKEAWAYS / RISKS / SUMMARY) that precedes "Full Conference Call Transcript"
    is dropped so quotes come only from the call itself.
    """
    m0 = TRANSCRIPT_START.search(text)
    if m0:
        text = text[m0.end():]
    turns, pos, speaker = [], 0, "Preamble"
    dash_hits = list(SPEAKER_RE.finditer(text))
    colon_hits = list(SPEAKER_COLON_RE.finditer(text))
    if len(colon_hits) > len(dash_hits):
        for m in colon_hits:
            body = text[pos:m.start()].strip()
            if body:
                turns.append((speaker, body))
            speaker = m.group(1).strip()
            pos = m.end()
        tail = text[pos:].strip()
        if tail:
            turns.append((speaker, tail))
        return turns
    for m in dash_hits:
        body = text[pos:m.start()].strip()
        if body:
            turns.append((speaker, body))
        speaker = f"{m.group(1).strip()} ({m.group(2).strip()})"
        pos = m.end()
    tail = text[pos:].strip()
    if tail:
        turns.append((speaker, tail))
    return turns


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Split on paragraph boundaries into pieces of at most `size` chars with overlap."""
    paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(p) > size:  # very long paragraph (tables): hard split
            for i in range(0, len(p), size - overlap):
                chunks.append(p[i:i + size])
            cur = ""
            continue
        if len(cur) + len(p) + 2 > size and cur:
            chunks.append(cur)
            cur = cur[-overlap:] + "\n\n" + p if overlap else p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        chunks.append(cur)
    return chunks


def chunks_for_document(source_type: str, text: str) -> list[tuple[str, str]]:
    """Return [(section_label, chunk_text)] for a document."""
    out = []
    if source_type in ("10-K", "10-Q"):
        for label, body in split_filing_sections(text, form=source_type).items():
            out += [(label, c) for c in chunk_text(body)]
    elif source_type == "transcript":
        turns = split_transcript(text)
        buf, speakers = "", []
        for speaker, body in turns:
            if len(body) > CHUNK_CHARS:  # a long prepared-remarks turn: split it
                for sub in chunk_text(body):
                    out.append((speaker, f"{speaker}:\n{sub}"))
                continue
            piece = f"{speaker}:\n{body}"
            if len(buf) + len(piece) > CHUNK_CHARS and buf:
                out.append((" / ".join(dict.fromkeys(speakers)), buf))
                buf, speakers = "", []
            buf = f"{buf}\n\n{piece}" if buf else piece
            speakers.append(speaker.split(" (")[0])
        if buf:
            out.append((" / ".join(dict.fromkeys(speakers)), buf))
    else:
        out = [("Body", c) for c in chunk_text(text)]
    return out


def build_chunks(con, customer: str | None = None, rebuild: bool = False) -> int:
    """Create chunk rows for every document that has none. Returns chunks created."""
    q = "SELECT doc_id, source_type, text_path FROM documents"
    args = ()
    if customer:
        q += " WHERE customer=?"
        args = (customer,)
    created = 0
    for row in con.execute(q, args).fetchall():
        if rebuild:
            con.execute("DELETE FROM chunks WHERE doc_id=?", (row["doc_id"],))
        elif con.execute("SELECT 1 FROM chunks WHERE doc_id=? LIMIT 1", (row["doc_id"],)).fetchone():
            continue
        text = open(row["text_path"], encoding="utf-8").read()
        for idx, (section, chunk) in enumerate(chunks_for_document(row["source_type"], text)):
            con.execute(
                "INSERT OR REPLACE INTO chunks(chunk_id, doc_id, idx, section, text, n_chars) VALUES (?,?,?,?,?,?)",
                (sha1(f"{row['doc_id']}|{idx}")[:16], row["doc_id"], idx, section, chunk, len(chunk)),
            )
            created += 1
    return created
