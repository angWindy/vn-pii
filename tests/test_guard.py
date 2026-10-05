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


def test_guard_post_scan_passes_when_nothing_new_is_introduced(
    tmp_path, monkeypatch
) -> None:
    """Bug 4 negative: when the inner command only commits benign content, exit 0."""
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    script = tmp_path / "plant_safe.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'col\\nbenign\\n' > safe.csv\n"
        "git add safe.csv\n"
        "git -c user.name=t -c user.email=t@t.test commit -q -m 'safe'\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    rc = guard_run([str(script)])
    assert rc == 0
