"""Tests for pii_linter.detectors.column_name."""

from pii_linter.detectors.column_name import resolve_severity, score_column
from pii_linter.severity import CRITICAL, HIGH, MEDIUM


def test_customer_phone_is_high() -> None:
    hints = score_column("customer_phone")
    assert any(h.entity == "PHONE" and h.severity == HIGH for h in hints)


def test_email_is_medium() -> None:
    hints = score_column("customer_email")
    assert any(h.entity == "EMAIL" and h.severity == MEDIUM for h in hints)


def test_qty_is_empty() -> None:
    assert score_column("qty") == []


def test_card_no_is_critical() -> None:
    hints = score_column("card_no")
    assert any(h.entity == "CARD_NO" and h.severity == CRITICAL for h in hints)


def test_unknown_returns_empty() -> None:
    assert score_column("") == []
    assert score_column("foobar_unknown") == []


def test_resolve_severity_falls_back() -> None:
    assert resolve_severity("UNKNOWN") == MEDIUM
    assert resolve_severity("PERSON") == HIGH