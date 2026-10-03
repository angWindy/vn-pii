"""Tests for pii_linter.detectors.content_regex."""

from pii_linter import ColumnHint
from pii_linter.detectors.content_regex import scan_value
from pii_linter.severity import HIGH, MEDIUM


def _h(*entities_with_sev) -> list[ColumnHint]:
    return [ColumnHint(entity=e, severity=s) for e, s in entities_with_sev]


def test_phone_matches() -> None:
    findings = scan_value("Số điện thoại: 0912345678", [])
    assert any(f.entity == "PHONE" for f in findings)


def test_cccd_matches() -> None:
    findings = scan_value("CCCD: 012345678901", [])
    assert any(f.entity == "ID_NUMBER" for f in findings)


def test_email_matches() -> None:
    findings = scan_value("Email: test@example.com", [])
    assert any(f.entity == "EMAIL" for f in findings)


def test_vin_matches() -> None:
    findings = scan_value("VIN 1HGCM82633A004352 here", [])
    assert any(f.entity == "ASSET" for f in findings)


def test_plate_matches() -> None:
    findings = scan_value("Bien so 30A-123.45", [])
    assert any(f.entity == "ASSET" for f in findings)


def test_cmnd_requires_id_hint_or_keyword() -> None:
    # No ID_NUMBER hint, no keyword → 9-digit run must NOT be flagged.
    assert scan_value("order 123456789 today", []) == []
    # ID_NUMBER hint still unlocks CMND (legacy path).
    findings = scan_value("CMND 123456789", _h(("ID_NUMBER", HIGH)))
    assert any(f.entity == "ID_NUMBER" for f in findings)
    # Keyword in free-text unlocks CMND even without column hint.
    findings = scan_value("CCCD: 123456789 xin chao", [])
    assert any(f.entity == "ID_NUMBER" for f in findings)
    # Keyword case-insensitive.
    findings = scan_value("cmnd 123456789", [])
    assert any(f.entity == "ID_NUMBER" for f in findings)
    # Vietnamese keyword variant.
    findings = scan_value("căn cước 123456789", [])
    assert any(f.entity == "ID_NUMBER" for f in findings)


def test_empty_value_returns_empty() -> None:
    assert scan_value("", []) == []


def test_severity_matches_severity_table() -> None:
    findings = scan_value("phone 0912345678", [])
    phone = next(f for f in findings if f.entity == "PHONE")
    assert phone.severity == HIGH


def test_email_severity_is_medium() -> None:
    findings = scan_value("e test@example.com", [])
    email = next(f for f in findings if f.entity == "EMAIL")
    assert email.severity == MEDIUM