"""Tests for pii_linter.detectors.luhn_card."""

from pii_linter.detectors.luhn_card import detect_card, luhn_check
from pii_linter.severity import CRITICAL


def test_luhn_valid_visa() -> None:
    assert luhn_check("4111111111111111") is True


def test_luhn_invalid() -> None:
    assert luhn_check("1234567890123456") is False
    assert luhn_check("4111111111111112") is False


def test_luhn_too_short() -> None:
    assert luhn_check("4111") is False
    assert luhn_check("") is False


def test_detect_visa_pan() -> None:
    f = detect_card("Card: 4111-1111-1111-1111 expires soon")
    assert f is not None
    assert f.entity == "CARD_NO"
    assert f.severity == CRITICAL
    assert "Visa" in f.evidence_masked


def test_detect_returns_none_for_non_luhn() -> None:
    assert detect_card("Card 1234567890123456") is None


def test_detect_returns_none_for_unknown_bin() -> None:
    # 16-digit Luhn-valid but BIN not in table (starts with 9).
    f = detect_card("9999-9999-9999-9995")
    assert f is None


def test_detect_empty() -> None:
    assert detect_card("") is None