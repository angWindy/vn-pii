"""End-to-end smoke test against synthetic fixtures."""

from pathlib import Path

import pytest

from pii_linter.cli import scan_path


FIX_ROOT = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture(scope="module", autouse=True)
def ensure_fixtures() -> None:
    """Generate fixtures if not present (when running from a fresh clone)."""
    if not (FIX_ROOT / "gold" / "leads_50.csv").exists():
        import subprocess
        import sys
        subprocess.run(
            [sys.executable, "fixtures/generators/make_synthetic.py",
             "--out", "gold", "negative"],
            check=True,
            cwd=str(FIX_ROOT.parent),
        )


def test_gold_leads_has_phone_findings() -> None:
    result = scan_path(FIX_ROOT / "gold",
                       suppressions_path=FIX_ROOT.parent / "suppressions.yaml")
    assert any(f.entity == "PHONE" for f in result.findings)


def test_gold_finance_has_card_findings() -> None:
    result = scan_path(FIX_ROOT / "gold",
                       suppressions_path=FIX_ROOT.parent / "suppressions.yaml")
    assert any(f.entity == "CARD_NO" for f in result.findings)


def test_negative_aggregate_is_clean() -> None:
    result = scan_path(FIX_ROOT / "negative",
                       suppressions_path=FIX_ROOT.parent / "suppressions.yaml")
    assert result.findings == []


def test_negative_crm_pipeline_is_clean() -> None:
    result = scan_path(FIX_ROOT / "negative",
                       suppressions_path=FIX_ROOT.parent / "suppressions.yaml")
    assert result.findings == []