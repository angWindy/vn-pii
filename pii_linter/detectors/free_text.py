"""Free-text detector for PA1.

Activated only for "note" columns (column hint NOTE) or values longer than
30 characters. Runs :func:`content_regex.scan_value` then applies combo
boost when ≥2 HIGH-severity entities co-occur in the same value.
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
    apply_combo_boost,
)


_MIN_LEN = 30


def scan(
    value: str,
    column_hints: Iterable[ColumnHint] = (),
) -> list[Finding]:
    """Run all content regex detectors; apply combo boost at HIGH+ threshold."""
    hints = list(column_hints)
    is_note = any(h.entity == "NOTE" for h in hints)
    if not is_note and len(value) < _MIN_LEN:
        return []
    findings = _scan_value(value, hints)
    if not findings:
        return []
    # Apply combo boost: aggregate by_entity then bump.
    by_entity: dict[str, int] = {}
    for f in findings:
        by_entity[f.entity] = max(by_entity.get(f.entity, 0), f.severity)
    high_plus = sum(1 for s in by_entity.values() if s >= HIGH)
    if high_plus >= COMBO_THRESHOLD:
        base = max(by_entity.values())
        target = min(base + COMBO_BUMP, CRITICAL)
        bumped_findings = [
            Finding(
                entity=f.entity,
                severity=target if f.severity >= HIGH else f.severity,
                evidence_raw=f.evidence_raw,
                evidence_masked=f.evidence_masked,
                span=f.span,
            )
            for f in findings
        ]
        bumped_findings.append(
            Finding(
                entity="COMBO",
                severity=target,
                evidence_raw="",
                evidence_masked=f"<combo boost: {high_plus} HIGH+ entities>",
                span=None,
            )
        )
        return bumped_findings
    return findings