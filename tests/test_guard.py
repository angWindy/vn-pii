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


def test_guard_dashdash_separator_is_stripped(tmp_path, monkeypatch) -> None:
    """Bug 3: `pa1-lint guard -- <cmd>` must not pass `--` to subprocess.

    Before the fix, argparse.REMAINDER swallowed the `--` separator
    and subprocess tried to exec it as argv[0], raising FileNotFoundError.
    The aider template relies on this syntax, so the breakage also nuked
    every `pa1-lint-aider` invocation.
    """
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = guard_run(["--", "echo", "ok"])
    assert rc == 0
    rc = guard_run(["echo", "ok"])
    assert rc == 0


def test_guard_blocks_post_commit_introduced_pii(tmp_path, monkeypatch) -> None:
    """Bug 4: post-scan must catch PII the wrapped command committed.

    Before the fix, post-scan ran `git diff HEAD` — after the inner
    command committed, staged content became part of HEAD, the diff
    came back empty, and PII the agent just committed slipped through.
    """
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    script = tmp_path / "plant.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'sdt,email\\n0912345678,real.person@example.com\\n' > leak.csv\n"
        "git add leak.csv\n"
        "git -c user.name=t -c user.email=t@t.test commit -q -m 'agent leak'\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    rc = guard_run([str(script)])
    assert rc == 2, "post-scan must catch PII the wrapped command committed"


def test_guard_only_scans_documented_formats(tmp_path, monkeypatch) -> None:
    """Guard must honour the documented CSV/JSONL/Markdown scope.

    It used to collect `+` lines from every file in the diff, so a `.py`
    or `.sh` file that merely mentioned a phone number blocked the commit
    even though the tool only claims to cover three formats.
    """
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    (repo / "data.py").write_text('phone = "0912345678"\n', encoding="utf-8")
    (repo / "run.sh").write_text("echo 0912345678\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
    assert guard_run(["echo", "ok"]) == 0


def test_guard_still_scans_csv_and_md(tmp_path, monkeypatch) -> None:
    """The same PII in an in-scope format must still be caught."""
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    (repo / "leak.csv").write_text(
        "sdt\n0912345678\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
    assert guard_run(["echo", "should-not-run"]) == 2

    subprocess.run(["git", "rm", "-q", "--cached", "leak.csv"], cwd=str(repo), check=True)
    subprocess.run(["git", "reset", "-q", "--hard"], cwd=str(repo), check=True)
    (repo / "notes.md").write_text("# notes\ncall 0912345678\n", encoding="utf-8")
    subprocess.run(["git", "add", "notes.md"], cwd=str(repo), check=True)
    assert guard_run(["echo", "should-not-run"]) == 2


def test_scan_diff_text_honours_suppressions() -> None:
    """Guard's diff scanner must accept suppressions, matching `scan`.

    A synthetic value carried by a diff line should be suppressible even
    though the diff gives no column header to match against.
    """
    from datetime import date

    from pii_linter.detectors.free_text import apply_combo
    from pii_linter.detectors.content_regex import scan_value
    from pii_linter.guard import _scan_diff_text
    from pii_linter.suppressions import Suppression

    line = "dummy_0912345678 is fine"
    assert _scan_diff_text(line), "sanity: unsuppressed line is flagged"
    sups = [
        Suppression(
            column_pattern=".*",
            value_prefix="dummy",
            owner="test",
            expires_at=date(2099, 1, 1),
            reason="synthetic",
        )
    ]
    assert _scan_diff_text(line, sups) == []
    # And a non-suppressed line still gets scanned when sups are loaded.
    assert _scan_diff_text("0912345678 raw", sups)


def test_scan_diff_text_masks_every_entity_in_the_line() -> None:
    """The guard's report must not print a co-located PAN beside a masked phone.

    `guard` used to run the card and regex detectors independently, so the
    PHONE finding rendered `4111111111111111,***` -- a real card number in
    clear text, in the very output shown to a user whose commit was blocked.
    """
    from pii_linter.guard import _scan_diff_text

    findings = _scan_diff_text("4111111111111111,0912345678")
    assert {f.entity for f in findings} >= {"CARD_NO", "PHONE"}
    for f in findings:
        assert "4111111111111111" not in f.evidence_masked
        assert "0912345678" not in f.evidence_masked


def test_guard_report_contains_no_raw_pii(tmp_path, monkeypatch, capsys) -> None:
    """End-to-end: the blocked-commit report carries no unredacted PII."""
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    (repo / "cards.csv").write_text(
        "pan,phone\n4111111111111111,0912345678\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
    assert guard_run(["echo", "should-not-run"]) == 2
    err = capsys.readouterr().err
    assert "4111111111111111" not in err
    assert "0912345678" not in err
