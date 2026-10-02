"""Column-name heuristic for PA1.

Maps a CSV/JSONL column header to one or more ``ColumnHint`` guesses. The
heuristic is regex-based and case-insensitive. It is intentionally conservative:
unknown column names return an empty list, which means content regex must
fire on its own.
"""

from __future__ import annotations

import re

from pii_linter import ColumnHint
from pii_linter.severity import (
    HIGH,
    CRITICAL,
    MEDIUM,
    SEVERITY_BY_ENTITY,
)


# (regex pattern, entity, severity). Order matters: first match wins per
# distinct entity. If a single column matches two rules for different entities
# (e.g. "customer_id_cccd"), both ColumnHints are returned.
COLUMN_RULES: tuple[tuple[str, str, int], ...] = (
    (r"^(sđt|so_dien_thoai|phone|mobile|tel|hotline)$", "PHONE", HIGH),
    (r"(phone|mobile|tel|sđt|điện thoại)",            "PHONE", HIGH),
    (r"^(email|mail|e_?mail)$",                       "EMAIL", MEDIUM),
    (r"email",                                         "EMAIL", MEDIUM),
    (r"(cccd|cmnd|passport|id_number|cmtnd|cmt|so_cmnd)", "ID_NUMBER", HIGH),
    (r"(account_no|stk|số tài khoản|so_tai_khoan)",   "ACCOUNT_NO", HIGH),
    (r"(pan|credit_card|card_no|số thẻ)",             "CARD_NO", CRITICAL),
    (r"^(name|ten|full_name|ho_ten|khach_hang|ten_kh|customer_name)$", "PERSON", HIGH),
    (r"(name|ten|họ tên|ho_ten)",                    "PERSON", HIGH),
    (r"^(vin|so_khung|frame_no)$",                   "ASSET", MEDIUM),
    (r"(plate|license_plate|so_ky_hieu|biển số)",     "ASSET", MEDIUM),
    (r"(note|notes|ghi_chu|mo_ta|description)",       "NOTE", MEDIUM),
    (r"(zalo|zalo\.me)",                              "URL_HANDLE", MEDIUM),
)

# Pre-compile once for speed.
_COMPILED: tuple[tuple[re.Pattern[str], str, int], ...] = tuple(
    (re.compile(pat, re.IGNORECASE), ent, sev)
    for pat, ent, sev in COLUMN_RULES
)


def score_column(name: str) -> list[ColumnHint]:
    """Return a list of ``ColumnHint`` for the given column header.

    Empty list when no rule matches (caller falls back to content-only scan).
    Multiple hints are returned when distinct entities both match.
    """
    if not name:
        return []
    seen: dict[str, int] = {}
    for pat, entity, default_sev in _COMPILED:
        if pat.search(name):
            if entity not in seen:
                seen[entity] = default_sev
    return [ColumnHint(entity=e, severity=sev) for e, sev in seen.items()]


def resolve_severity(entity: str, fallback: int = MEDIUM) -> int:
    """Look up baseline severity for an entity string."""
    return SEVERITY_BY_ENTITY.get(entity, fallback)