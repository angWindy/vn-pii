"""Severity model for PII.

Severity is a discrete 4-level scale. Each entity type has a baseline
severity in :data:`SEVERITY_BY_ENTITY`. The :data:`COMBO_BOOST` rule
escalates a row that carries multiple high-severity entities together.

The scale intentionally matches exit codes in :mod:`pii_linter.cli`:

    LOW=1          (exit 0 = clean)
    MEDIUM=2       (exit 0 = clean)
    HIGH=3         (exit 1 = block commit)
    CRITICAL=4      (exit 2 = block commit)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


LOW = 1
MEDIUM = 2
HIGH = 3
CRITICAL = 4


# Baseline severity per entity. Edit here to raise/lower a whole category.
SEVERITY_BY_ENTITY: dict[str, int] = {
    "PERSON":     HIGH,
    "PHONE":      HIGH,
    "EMAIL":      MEDIUM,
    "ID_NUMBER":  HIGH,       # CCCD, CMND, passport
    "ACCOUNT_NO": HIGH,       # STK
    "CARD_NO":    CRITICAL,   # PAN Luhn-valid
    "ASSET":      MEDIUM,     # VIN, plate, engine number
    "NOTE":       MEDIUM,     # free-text blob flagged as note (base; raised by combo)
    "URL_HANDLE": MEDIUM,     # zalo.me/<id>
}


# How many HIGH+ findings on the same row trigger a bump?
COMBO_THRESHOLD = 2

# How many levels to add when threshold is met (cap at CRITICAL).
COMBO_BUMP = 1


@dataclass(frozen=True)
class SeverityCount:
    """A histogram of severities for one row.

    Used by the orchestrator to compute a row-level max and apply combo boost.
    """

    by_entity: dict[str, int]  # entity -> severity

    def max_severity(self) -> int:
        return max(self.by_entity.values()) if self.by_entity else LOW

    def num_high_plus(self) -> int:
        return sum(1 for s in self.by_entity.values() if s >= HIGH)


def apply_combo_boost(by_entity: dict[str, int]) -> int:
    """Return the row-level severity after combo boost.

    If there are at least :data:`COMBO_THRESHOLD` distinct entities at HIGH or
    above, bump the maximum severity by :data:`COMBO_BUMP` (cap at CRITICAL).
    """
    if not by_entity:
        return LOW
    base = max(by_entity.values())
    high_plus = sum(1 for s in by_entity.values() if s >= HIGH)
    if high_plus >= COMBO_THRESHOLD:
        return min(base + COMBO_BUMP, CRITICAL)
    return base


def entities_at_least(by_entity: dict[str, int], level: int) -> Iterable[str]:
    """Yield entities whose severity is >= ``level``."""
    return (e for e, s in by_entity.items() if s >= level)