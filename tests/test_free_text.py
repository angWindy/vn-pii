"""Tests for pii_linter.detectors.free_text."""

from pii_linter import ColumnHint, Finding
from pii_linter.detectors.free_text import apply_combo, scan
from pii_linter.severity import CRITICAL, HIGH


def _f(entity: str, sev: int) -> Finding:
    return Finding(
        entity=entity, severity=sev,
        evidence_raw="x", evidence_masked="x", span=None,
    )


def _note_hint() -> list[ColumnHint]:
    return [ColumnHint(entity="NOTE", severity=2)]


def test_short_value_no_hint_returns_empty() -> None:
    """Without NOTE hint and len < 30, scan() short-circuits."""
    assert scan("short", []) == []


def test_long_value_triggers_regex() -> None:
    """A value > 30 chars with a phone match yields a PHONE finding."""
    v = "Customer line 0912345678 with extra text to exceed thirty chars " * 2
    out = scan(v)
    assert any(f.entity == "PHONE" for f in out)


def test_note_hint_short_value_triggers() -> None:
    """NOTE column hint bypasses the 30-char gate."""
    out = scan("CCCD 012345678901", _note_hint())
    assert any(f.entity == "ID_NUMBER" for f in out)


def test_combo_two_high_entities_bumps_to_critical() -> None:
    """Two HIGH+ entities in one row must escalate to CRITICAL + COMBO marker."""
    findings = [_f("PHONE", HIGH), _f("ID_NUMBER", HIGH)]
    out = apply_combo(findings)
    assert any(f.entity == "COMBO" for f in out)
    assert any(f.severity == CRITICAL for f in out)


def test_combo_one_high_returns_unchanged() -> None:
    """Below the threshold, apply_combo is a no-op (same object)."""
    findings = [_f("EMAIL", 2)]
    out = apply_combo(findings)
    assert out is findings


def test_combo_empty_returns_empty() -> None:
    assert apply_combo([]) == []


def test_orchestrator_does_not_duplicate_findings() -> None:
    """`_dispatch_value` must run regex once; combo applied to merged list.

    This guards the regression where `scan_content` and `scan_free_text`
    both ran the regex, doubling every finding in long values.
    """
    from pii_linter.cli import _dispatch_value

    v = "phone 0912345678 and id 012345678901 inside a long free-text value"
    findings = _dispatch_value(v, [])
    # At most one PHONE and one ID_NUMBER finding — not duplicates.
    phone = [f for f in findings if f.entity == "PHONE"]
    idn   = [f for f in findings if f.entity == "ID_NUMBER"]
    assert len(phone) <= 1
    assert len(idn) <= 1