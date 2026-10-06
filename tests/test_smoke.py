"""End-to-end smoke test against synthetic fixtures."""

from __future__ import annotations

import json
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
    """End-to-end: `pii-lint scan --staged` exits 1 on planted PII."""
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

# ---------------------------------------------------------------------------
# Regressions for the 2026-10-05 bug sweep.
# ---------------------------------------------------------------------------


def test_bad_usage_exits_ex_usage_not_critical() -> None:
    """Bug 5: argparse errors must not masquerade as CRITICAL PII (exit 2)."""
    from pii_linter.cli import EX_USAGE

    proc = subprocess.run(
        [sys.executable, "-m", "pii_linter.cli", "scan", "--no-such-flag"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == EX_USAGE
    assert proc.returncode != 2


def test_critical_pii_still_exits_2(tmp_path: Path) -> None:
    """Bug 5 regression guard: exit 2 still means CRITICAL, not usage."""
    csv = tmp_path / "cards.csv"
    csv.write_text("pan\n4111111111111111\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "pii_linter.cli", "scan", str(csv)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2


# ---------------------------------------------------------------------------
# Zero-friction entry points: `pii-lint <path>`, bare `pii-lint`, and
# `python -m pii_linter` all work without naming the `scan` subcommand.
# ---------------------------------------------------------------------------


def _planted_csv(tmp_path: Path) -> Path:
    """A CSV with a HIGH-severity PHONE, so exit code is 1."""
    csv = tmp_path / "leads.csv"
    csv.write_text("name,phone\nNam,0912345678\n", encoding="utf-8")
    return csv


def test_bare_pii_lint_scans_cwd(tmp_path: Path) -> None:
    """A bare `pii-lint` scans the current directory and finds PII."""
    _planted_csv(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "pii_linter.cli"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "PHONE" in proc.stdout


def test_path_without_scan_subcommand(tmp_path: Path) -> None:
    """`pii-lint data.csv` is the same as `pii-lint scan data.csv`."""
    csv = _planted_csv(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "pii_linter.cli", str(csv)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "PHONE" in proc.stdout


def test_explicit_scan_subcommand_still_works(tmp_path: Path) -> None:
    """The documented `scan <path>` form must not regress."""
    csv = _planted_csv(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "pii_linter.cli", "scan", str(csv)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "PHONE" in proc.stdout


def test_module_entry_point_matches_cli(tmp_path: Path) -> None:
    """`python -m pii_linter` mirrors the console script exactly."""
    csv = _planted_csv(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "pii_linter", str(csv)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "PHONE" in proc.stdout


def test_scan_flag_routes_to_scan_subcommand(tmp_path: Path) -> None:
    """A leading `--format json` must scan, not error as an unknown root flag."""
    csv = _planted_csv(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "pii_linter.cli", "--format", "json", str(csv)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert any(f["entity"] == "PHONE" for f in payload["findings"])


def test_root_help_still_prints_usage() -> None:
    """`pii-lint --help` must show root help, not fall through to a scan."""
    proc = subprocess.run(
        [sys.executable, "-m", "pii_linter.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "usage:" in proc.stdout.lower()
    assert "install-hooks" in proc.stdout


def test_unknown_flag_still_exits_ex_usage(tmp_path: Path) -> None:
    """Normalising argv must not swallow a typo into a PII exit code."""
    from pii_linter.cli import EX_USAGE

    proc = subprocess.run(
        [sys.executable, "-m", "pii_linter.cli", "--no-such-flag"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == EX_USAGE
    assert proc.returncode != 1
    assert proc.returncode != 2


def test_import_scan_from_package_root(tmp_path: Path) -> None:
    """`from pii_linter import scan` works and returns a ScanResult."""
    from pii_linter import ScanResult, scan

    csv = _planted_csv(tmp_path)
    result = scan(str(csv))
    assert isinstance(result, ScanResult)
    assert any(f.entity == "PHONE" for f in result.findings)


def test_lazy_import_does_not_break_plain_import() -> None:
    """`import pii_linter` must stay cycle-free (no cli import at module scope)."""
    proc = subprocess.run(
        [sys.executable, "-c",
         "import pii_linter, sys; assert 'pii_linter.cli' not in sys.modules"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
