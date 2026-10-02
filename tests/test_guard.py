"""Tests for pii_linter.guard."""

import subprocess
from pathlib import Path

from pii_linter.guard import run as guard_run


def _init_repo(tmp_path: Path) -> Path:
    """Initialise a git repo at tmp_path with one empty commit."""
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(tmp_path),
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=str(tmp_path),
        check=True,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-q", "-m", "init"],
        cwd=str(tmp_path),
        check=True,
    )
    return tmp_path


def test_guard_blocks_when_staged_diff_has_pii(tmp_path, monkeypatch) -> None:
    _init_repo(tmp_path)
    (tmp_path / "leads.csv").write_text(
        "customer_id,phone\nid_0001,0912345678\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "leads.csv"], cwd=str(tmp_path), check=True)
    monkeypatch.chdir(tmp_path)
    rc = guard_run(["echo", "should-not-run"])
    assert rc == 2


def test_guard_passes_on_clean_diff(tmp_path, monkeypatch) -> None:
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("# empty\n", encoding="utf-8")
    subprocess.run(["git", "add", "notes.md"], cwd=str(tmp_path), check=True)
    monkeypatch.chdir(tmp_path)
    rc = guard_run(["echo", "ok"])
    assert rc == 0


def test_guard_skipped_outside_git(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    rc = guard_run(["echo", "ok"])
    assert rc == 0