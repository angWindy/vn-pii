"""End-to-end smoke test against synthetic fixtures."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pii_linter.cli import scan_path, scan_staged


FIX_ROOT = Path(__file__).resolve().parent.parent / "fixtures"
SUPPRESSIONS = FIX_ROOT.parent / "suppressions.toml"


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
    result = scan_path(FIX_ROOT / "gold", suppressions_path=SUPPRESSIONS)
    assert any(f.entity == "PHONE" for f in result.findings)


def test_gold_finance_has_card_findings() -> None:
    result = scan_path(FIX_ROOT / "gold", suppressions_path=SUPPRESSIONS)
    assert any(f.entity == "CARD_NO" for f in result.findings)


def test_negative_aggregate_is_clean() -> None:
    result = scan_path(FIX_ROOT / "negative", suppressions_path=SUPPRESSIONS)
    assert result.findings == []


def test_negative_crm_pipeline_is_clean() -> None:
    result = scan_path(FIX_ROOT / "negative", suppressions_path=SUPPRESSIONS)
    assert result.findings == []


# ---------------------------------------------------------------------------
# Staged-diff scan (Slice 3: pre-commit hook).
# ---------------------------------------------------------------------------


def _make_git_repo(tmp: Path, planted_csv: Path) -> Path:
    """Init a temp git repo at ``tmp``, commit it once, plant a new line."""
    exe = shutil.which("git")
    if exe is None:
        pytest.skip("git is not on PATH; cannot exercise --staged mode")
    env = {
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@t.test",
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@t.test",
        "PATH": "/usr/bin:/usr/local/bin",
        "HOME": "/tmp",
    }
    subprocess.run([exe, "init", "-q"], cwd=str(tmp), env=env, check=True)
    # Copy existing CSV (becomes the HEAD revision).
    (tmp / "leads.csv").write_bytes(planted_csv.read_bytes())
    subprocess.run([exe, "add", "leads.csv"], cwd=str(tmp), env=env, check=True)
    subprocess.run(
        [exe, "commit", "-q", "-m", "initial"], cwd=str(tmp), env=env, check=True
    )
    return tmp


def test_staged_scan_blocks_on_planted_phone(tmp_path: Path) -> None:
    planted = FIX_ROOT / "gold" / "leads_50.csv"
    _make_git_repo(tmp_path, planted)

    # Append a new line with raw PII and stage it.
    with (tmp_path / "leads.csv").open("a", encoding="utf-8") as fh:
        fh.write("planted,0123456789,foo@bar.com\n")
    subprocess.run(
        ["git", "add", "leads.csv"], cwd=str(tmp_path), check=True
    )

    result = scan_staged(cwd=tmp_path)
    assert result.files_scanned >= 1
    assert any(f.entity == "PHONE" and f.line_no > 0 for f in result.findings)
    # Each finding carries a file path and a line number.
    assert all(f.file and f.line_no for f in result.findings)


def test_staged_scan_passes_on_clean(tmp_path: Path) -> None:
    planted = FIX_ROOT / "negative" / "aggregate_50.csv"
    _make_git_repo(tmp_path, planted)

    result = scan_staged(cwd=tmp_path)
    assert result.findings == []


def test_cli_scan_staged_exit_code_1(tmp_path: Path) -> None:
    """End-to-end: `pa1-lint scan --staged` exits 1 on planted PII."""
    planted = FIX_ROOT / "gold" / "leads_50.csv"
    _make_git_repo(tmp_path, planted)
    with (tmp_path / "leads.csv").open("a", encoding="utf-8") as fh:
        fh.write("planted,0123456789,foo@bar.com\n")
    subprocess.run(
        ["git", "add", "leads.csv"], cwd=str(tmp_path), check=True
    )
    proc = subprocess.run(
        [sys.executable, "-m", "pii_linter.cli", "scan", "--staged"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "leads.csv" in proc.stdout
    assert "PHONE" in proc.stdout