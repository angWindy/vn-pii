"""Free-text detector for PA1.

Activated only for "note" columns (column hint NOTE) or values longer than
30 characters. Runs :func:`content_regex.scan_value` then applies combo
boost when ≥2 HIGH-severity entities co-occur in the same value.

Two entry points:
- :func:`scan` — convenience wrapper that runs the regex then applies combo.
- :func:`apply_combo` — pure transform on an existing list of findings,
  used by the orchestrator when it already has a findings list (avoids
  scanning the same value twice).
"""

from __future__ import annotations

from typing import Iterable

from pii_linter import Finding
from pii_linter.detectors.column_name import ColumnHint
from pii_linter.detectors.content_regex import scan_value as _scan_value
from pii_linter.severity import (
    COMBO_BUMP,
    COMBO_THRESHOLD,
    CRITICAL,
    HIGH,
)


_MIN_LEN = 30


def scan(
    value: str,
    column_hints: Iterable[ColumnHint] = (),
) -> list[Finding]:
    """Run content regex and apply combo boost when ≥2 HIGH+ entities co-occur."""
    hints = list(column_hints)
    is_note = any(h.entity == "NOTE" for h in hints)
    if not is_note and len(value) < _MIN_LEN:
        return []
    findings = _scan_value(value, hints)
    return apply_combo(findings)


def apply_combo(findings: list[Finding]) -> list[Finding]:
    """Apply combo boost to an existing list of findings (no re-scan).

    If the input has ≥ :data:`COMBO_THRESHOLD` HIGH+ entities, bump the max
    severity by :data:`COMBO_BUMP` (cap at :data:`CRITICAL`) and append a
    COMBO marker. Returns the input unchanged otherwise.
    """
    if not findings:
        return findings
    by_entity: dict[str, int] = {}
    for f in findings:
        by_entity[f.entity] = max(by_entity.get(f.entity, 0), f.severity)
    high_plus = sum(1 for s in by_entity.values() if s >= HIGH)
    if high_plus < COMBO_THRESHOLD:
        return findings
    base = max(by_entity.values())
    target = min(base + COMBO_BUMP, CRITICAL)
    bumped: list[Finding] = [
        Finding(
            entity=f.entity,
            severity=target if f.severity >= HIGH else f.severity,
            evidence_raw=f.evidence_raw,
            evidence_masked=f.evidence_masked,
            span=f.span,
        )
        for f in findings
    ]
    bumped.append(
        Finding(
            entity="COMBO",
            severity=target,
            evidence_raw="",
            evidence_masked=f"<combo boost: {high_plus} HIGH+ entities>",
            span=None,
        )
    )
    return bumped