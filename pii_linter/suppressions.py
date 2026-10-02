"""Suppressions loader for PA1.

A suppression is a YAML record that says: "values matching this column
pattern and starting with this synthetic prefix on or before ``expires_at``
should not trigger findings". This is for clearly-synthetic datasets that
look like PII columns but contain Faker-seeded IDs.

Example ``suppressions.yaml``::

    suppressions:
        - column_pattern: customer_id
          value_prefix: "id_"
          owner: synth-data-team
          expires_at: 2027-12-31
          reason: Faker seed 42; verified by /tests/test_smoke.py

If the file is missing or empty, no suppression is applied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import yaml


@dataclass(frozen=True)
class Suppression:
    column_pattern: str  # regex (case-insensitive) matched against column header
    value_prefix: str    # literal string the value must start with
    owner: str
    expires_at: date
    reason: str

    def matches(self, column: str, value: str, today: date) -> bool:
        if today > self.expires_at:
            return False
        if not re.search(self.column_pattern, column, re.IGNORECASE):
            return False
        return value.startswith(self.value_prefix)


def load_suppressions(path: Path | str) -> list[Suppression]:
    """Load and validate a ``suppressions.yaml`` file.

    Returns an empty list if the file does not exist. Raises ``ValueError``
    on malformed entries so the caller can decide to fail-loud.
    """
    p = Path(path)
    if not p.exists():
        return []

    with p.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    entries = raw.get("suppressions", [])
    if not isinstance(entries, list):
        raise ValueError(f"{path}: top-level 'suppressions' must be a list")

    out: list[Suppression] = []
    for i, e in enumerate(entries):
        try:
            out.append(_parse_entry(e))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{path}: entry #{i} invalid: {exc}") from exc
    return out


def _parse_entry(e: dict) -> Suppression:
    expires = e["expires_at"]
    if isinstance(expires, date):
        expires_at = expires
    elif isinstance(expires, datetime):
        expires_at = expires.date()
    elif isinstance(expires, str):
        expires_at = date.fromisoformat(expires)
    else:
        raise TypeError(f"expires_at must be ISO date string, got {type(expires).__name__}")
    return Suppression(
        column_pattern=str(e["column_pattern"]),
        value_prefix=str(e["value_prefix"]),
        owner=str(e["owner"]),
        expires_at=expires_at,
        reason=str(e.get("reason", "")),
    )


def is_suppressed(
    column: str,
    value: str,
    suppressions: Iterable[Suppression],
    today: date | None = None,
) -> bool:
    """Return True if any active suppression matches this column/value pair."""
    today = today or date.today()
    return any(s.matches(column, value, today) for s in suppressions)