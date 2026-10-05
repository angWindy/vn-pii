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


def test_single_file_path_uses_filename_as_key() -> None:
    """`scan_path(file.csv)` must key `by_file` by the filename, not '.'."""
    result = scan_path(FIX_ROOT / "gold" / "leads_50.csv")
    assert list(result.by_file.keys()) == ["leads_50.csv"]


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


# ---------------------------------------------------------------------------
# Regressions for the 2026-10-05 bug sweep.
# ---------------------------------------------------------------------------


def test_md_prose_is_scanned_not_just_tables(tmp_path: Path) -> None:
    """Bug 1: PII in Markdown prose (outside any table) must be flagged.

    Before the fix, `_scan_md` skipped every line that was not a table
    row, so `scan notes.md` reported 0 findings for a file that
    `scan --staged` and `guard` both flagged. Same file, three answers.
    """
    notes = tmp_path / "notes.md"
    notes.write_text(
        "# Contact notes\n"
        "\n"
        "Reach out to Nguyễn Văn An at 0912345678 or an.nguyen@example.com.\n"
        "\n"
        "| col | col |\n"
        "|---|---|\n"
        "| ok | fine |\n",
        encoding="utf-8",
    )
    result = scan_path(notes)
    entities = {f.entity for f in result.findings}
    assert "PHONE" in entities
    assert "EMAIL" in entities


def test_md_prose_matches_staged_path(tmp_path: Path) -> None:
    """Bug 1: `scan <file>.md` and `scan --staged` must agree on the same content."""
    if shutil.which("git") is None:
        pytest.skip("git is not on PATH; cannot exercise --staged mode")

    body = "Call 0912345678 or mail real.person@example.com\n"
    md = tmp_path / "notes.md"
    md.write_text(f"# Notes\n\n{body}", encoding="utf-8")
    direct = {f.entity for f in scan_path(md).findings}

    _make_git_repo(tmp_path, FIX_ROOT / "negative" / "aggregate_50.csv")
    md.write_text(f"# Notes\n\n{body}", encoding="utf-8")
    subprocess.run(["git", "add", "notes.md"], cwd=str(tmp_path), check=True)
    staged = {f.entity for f in scan_staged(cwd=tmp_path).findings}

    assert direct == staged
    assert "PHONE" in direct


def test_md_table_still_uses_column_heuristics(tmp_path: Path) -> None:
    """Bug 1 must not regress the table path: cells keep col<N> hints."""
    md = tmp_path / "table.md"
    md.write_text(
        "| name | phone |\n|---|---|\n| Nam | 0912345678 |\n",
        encoding="utf-8",
    )
    result = scan_path(md)
    assert any(f.entity == "PHONE" for f in result.findings)
