"""Tests for pii_linter.detectors.content_regex."""

from pii_linter import ColumnHint
from pii_linter.detectors.content_regex import scan_value
from pii_linter.detectors.luhn_card import detect_card
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


# ---------------------------------------------------------------------------
# Cross-entity evidence leaks. `AGENTS.md` forbids printing raw evidence, and
# a masked phone sitting in the tail of an EMAIL finding printed the phone in
# the clear -- into the report a *blocked commit* shows the user.
# ---------------------------------------------------------------------------


def test_mask_hides_other_entities_in_same_value() -> None:
    """Every finding must mask every span, not only its own."""
    value = "Nam,0912345678,nam@x.com"
    findings = scan_value(value, [])
    entities = {f.entity for f in findings}
    assert {"PHONE", "EMAIL"} <= entities
    for f in findings:
        assert "0912345678" not in f.evidence_masked
        assert "nam@x.com" not in f.evidence_masked


def test_card_finding_does_not_leak_neighbouring_phone() -> None:
    """detect_card must redact co-located PII, not just the PAN."""
    card = detect_card("4111111111111111,0912345678")
    assert card is not None
    assert "4111111111111111" not in card.evidence_masked
    assert "0912345678" not in card.evidence_masked
    # The network is metadata, not PII, and stays readable.
    assert "[Visa]" in card.evidence_masked


def test_overlapping_spans_do_not_double_mask() -> None:
    """Adjacent PII must merge into one *** rather than nested replacements."""
    for f in scan_value("0912345678 x 012345678901 y", []):
        assert "0912345678" not in f.evidence_masked
        assert "012345678901" not in f.evidence_masked


def test_dispatch_masks_card_and_phone_identically() -> None:
    """cli._dispatch_value merges detector spans, so no finding leaks a PAN.

    Each detector only knows its own span: run independently, PHONE reported
    ``4111111111111111,***`` because the PAN fell in its unmasked tail.
    """
    from pii_linter.cli import _dispatch_value

    findings = _dispatch_value("4111111111111111,0912345678", [])
    entities = {f.entity for f in findings}
    assert "CARD_NO" in entities
    assert "PHONE" in entities
    for f in findings:
        assert "4111111111111111" not in f.evidence_masked
        assert "0912345678" not in f.evidence_masked