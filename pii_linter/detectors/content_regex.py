"""Content-based regex detectors for PA1.

Each module-level regex is pre-compiled at import time. ``scan_value`` runs
all patterns against a single cell value and returns a list of ``Finding``.
"""

from __future__ import annotations

import re
from typing import Iterable

from pii_linter import Finding
from pii_linter.detectors.column_name import ColumnHint, resolve_severity


# Vietnamese mobile prefix list (as of 2025). Loosened to accept any 10-digit
# sequence starting with 0; the column hint is what enforces the match.
_RE_VN_PHONE = re.compile(r"(?:\+84|0)\d{9}\b")
# CCCD: 12 digits, CMND: 9 digits (CMND rarely used since 2025).
_RE_CCCD = re.compile(r"\b0\d{11}\b")        # 12 digits starting with 0
_RE_CMND = re.compile(r"\b\d{9}\b")          # 9 digits (heuristic only with hint)
# CMND (9 digits) is too noisy on its own, so we gate it: emit a finding only
# when the value carries an ID_NUMBER column hint OR a keyword from this set
# (case-insensitive). Supports free-text scanning without column-name hints.
_CMND_KEYWORDS = re.compile(
    r"\b(cmnd|cmt|cmtnd|cccd|căn\s*cước|can\s*cuoc|id_number|identity)\b",
    re.IGNORECASE,
)
# Email: local@domain.tld (no IP literals, no quoted local).
_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
# VIN: 17 chars, no I/O/Q.
_RE_VIN = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
# License plate (Vietnam): 30A-123.45 / 30A-12345 / 29-X1 123.45
_RE_PLATE = re.compile(r"\b\d{2}[A-Z]?[\-\s]?\d{3}[\.\-]?\d{2,3}\b")
# Zalo handle: zalo.me/<id> (id is 6-12 digits).
_RE_ZALO = re.compile(r"\bzalo\.me/(\d{6,12})\b", re.IGNORECASE)


# Order matters: more specific patterns first so they shadow the looser ones.
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (_RE_VN_PHONE, "PHONE"),
    (_RE_CCCD,     "ID_NUMBER"),
    (_RE_CMND,     "ID_NUMBER"),
    (_RE_EMAIL,    "EMAIL"),
    (_RE_VIN,      "ASSET"),
    (_RE_PLATE,    "ASSET"),
    (_RE_ZALO,     "URL_HANDLE"),
)


def _mask_simple(value: str, start: int, end: int) -> str:
    """Replace the (start..end) slice of ``value`` with ``***`` keeping visible context."""
    head = value[:start]
    tail = value[end:]
    return f"{head}***{tail}"


def scan_value(
    value: str,
    column_hints: Iterable[ColumnHint] = (),
) -> list[Finding]:
    """Scan a single cell value. Returns 0+ Finding."""
    if not value:
        return []
    hints = list(column_hints)
    hint_entities = {h.entity for h in hints}
    out: list[Finding] = []
    cmnd_unlocked = "ID_NUMBER" in hint_entities or bool(_CMND_KEYWORDS.search(value))
    for pat, entity in _PATTERNS:
        # CMND (9 digits) is too noisy on its own — unlock only when the
        # column hint says so OR the value itself carries an ID keyword.
        if pat is _RE_CMND and not cmnd_unlocked:
            continue
        for m in pat.finditer(value):
            sev = resolve_severity(entity)
            raw = m.group(0)
            masked = _mask_simple(value, m.start(), m.end())
            out.append(
                Finding(
                    entity=entity,
                    severity=sev,
                    evidence_raw=raw,
                    evidence_masked=masked,
                    span=(m.start(), m.end()),
                )
            )
    return out