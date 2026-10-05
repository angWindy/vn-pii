"""Tests for pii_linter.suppressions."""

from datetime import date

import pytest

from pii_linter.suppressions import Suppression, is_suppressed, load_suppressions


_TOML_SINGLE = (
    "[[suppressions]]\n"
    "column_pattern = 'customer_id'\n"
    "value_prefix = 'id_'\n"
    "owner = 'test'\n"
    "expires_at = 2030-01-01\n"
    "reason = 'fake'\n"
)


def test_load_missing_file_returns_empty(tmp_path) -> None:
    assert load_suppressions(tmp_path / "missing.toml") == []


def test_load_and_match(tmp_path) -> None:
    f = tmp_path / "sup.toml"
    f.write_text(_TOML_SINGLE)
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


def test_load_three_entries(tmp_path) -> None:
    f = tmp_path / "sup.toml"
    f.write_text(
        "[[suppressions]]\n"
        "column_pattern = 'a'\nvalue_prefix = 'x'\n"
        "owner = 'o'\nexpires_at = 2030-01-01\nreason = 'r'\n"
        "[[suppressions]]\n"
        "column_pattern = 'b'\nvalue_prefix = 'y'\n"
        "owner = 'o'\nexpires_at = 2030-01-01\nreason = 'r'\n"
        "[[suppressions]]\n"
        "column_pattern = 'c'\nvalue_prefix = 'z'\n"
        "owner = 'o'\nexpires_at = 2030-01-01\nreason = 'r'\n"
    )
    sups = load_suppressions(f)
    assert [s.column_pattern for s in sups] == ["a", "b", "c"]
    assert [s.value_prefix for s in sups] == ["x", "y", "z"]


def test_invalid_top_level(tmp_path) -> None:
    f = tmp_path / "bad.toml"
    f.write_text("suppressions = 'not-a-list'\n")
    with pytest.raises(ValueError):
        load_suppressions(f)


def test_invalid_entry(tmp_path) -> None:
    f = tmp_path / "bad.toml"
    f.write_text("[[suppressions]]\ncolumn_pattern = 'x'\n")
    with pytest.raises(ValueError):
        load_suppressions(f)


def test_repo_root_suppressions_loads() -> None:
    """The committed suppressions.toml at the repo root must load cleanly."""
    sups = load_suppressions("suppressions.toml")
    assert len(sups) == 4
    assert sups[0].column_pattern == "customer_id"
    assert sups[0].value_prefix == "id_"