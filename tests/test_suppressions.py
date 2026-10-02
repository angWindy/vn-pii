"""Tests for pii_linter.suppressions."""

from datetime import date

import pytest

from pii_linter.suppressions import Suppression, is_suppressed, load_suppressions


def test_load_missing_file_returns_empty(tmp_path) -> None:
    assert load_suppressions(tmp_path / "missing.yaml") == []


def test_load_and_match(tmp_path) -> None:
    f = tmp_path / "sup.yaml"
    f.write_text(
        "suppressions:\n"
        "  - column_pattern: 'customer_id'\n"
        "    value_prefix: 'id_'\n"
        "    owner: test\n"
        "    expires_at: '2030-01-01'\n"
        "    reason: fake\n"
    )
    sups = load_suppressions(f)
    assert len(sups) == 1
    s = sups[0]
    assert s.matches("customer_id", "id_001", date.today()) is True
    assert s.matches("customer_id", "abc", date.today()) is False
    assert s.matches("other", "id_001", date.today()) is False
    assert s.matches("customer_id", "id_001", date(2031, 1, 1)) is False


def test_is_suppressed_helper() -> None:
    sups = [
        Suppression(
            column_pattern=r"customer_id",
            value_prefix="id_",
            owner="x",
            expires_at=date(2030, 1, 1),
            reason="r",
        )
    ]
    assert is_suppressed("customer_id", "id_001", sups) is True
    assert is_suppressed("customer_id", "abc", sups) is False


def test_invalid_top_level(tmp_path) -> None:
    f = tmp_path / "bad.yaml"
    f.write_text("suppressions: not-a-list\n")
    with pytest.raises(ValueError):
        load_suppressions(f)


def test_invalid_entry(tmp_path) -> None:
    f = tmp_path / "bad.yaml"
    f.write_text("suppressions:\n  - column_pattern: x\n")
    with pytest.raises(ValueError):
        load_suppressions(f)