"""Tests for ``pa1-lint install-hooks``.

We exercise the install path against a sandboxed HOME and an isolated
``--project`` target. The test does NOT touch the real ``$HOME``.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from pii_linter.hooks import install_hooks


@pytest.fixture
def fake_home(tmp_path, monkeypatch) -> Path:
    h = tmp_path / "fake-home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    return h


@pytest.fixture
def fake_repo(tmp_path, monkeypatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()  # marker only; git itself is not exercised
    monkeypatch.chdir(repo)
    return repo


# ---- plans_for --------------------------------------------------------------


def test_plans_for_claude_code_user(fake_home) -> None:
    plans = install_hooks.plans_for(["claude-code"], "user")
    assert len(plans) == 1
    p = plans[0]
    assert p.target == fake_home / ".claude" / "settings.json"
    assert p.kind == "json"
    assert p.template_name == "claude-code.json"


def test_plans_for_cursor_user(fake_home) -> None:
    plans = install_hooks.plans_for(["cursor"], "user")
    assert plans[0].target == fake_home / ".cursor" / "hooks.json"


def test_plans_for_cody_user(fake_home) -> None:
    plans = install_hooks.plans_for(["cody"], "user")
    assert plans[0].target == fake_home / ".config" / "sourcegraph" / "cody.json"


def test_plans_for_codex_user_has_two_entries(fake_home) -> None:
    plans = install_hooks.plans_for(["codex"], "user")
    targets = {p.target for p in plans}
    assert fake_home / ".codex" / "config.toml" in targets
    assert fake_home / ".codex" / "hooks" / "codex-notify.sh" in targets


def test_plans_for_project_uses_repo_root(fake_home, fake_repo) -> None:
    plans = install_hooks.plans_for(["claude-code"], "project")
    assert plans[0].target == fake_repo / ".claude" / "settings.json"


# ---- install ---------------------------------------------------------------


def test_install_claude_code_creates_settings(fake_home) -> None:
    rc = install_hooks.install(["claude-code"], "user")
    assert rc == 0
    path = fake_home / ".claude" / "settings.json"
    assert path.exists()
    payload = json.loads(path.read_text())
    assert "hooks" in payload
    assert "PostToolUse" in payload["hooks"]
    assert "Stop" in payload["hooks"]


def test_install_merges_existing_user_prompt_submit(fake_home) -> None:
    """A pre-existing UserPromptSubmit must survive install."""
    cfg = fake_home / ".claude" / "settings.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        json.dumps(
            {
                "model": "claude-sonnet-4-5",
                "hooks": {
                    "UserPromptSubmit": [
                        {"matcher": "", "hooks": [{"type": "command", "command": "echo hi"}]}
                    ],
                },
                "theme": "dark",
            }
        )
    )
    rc = install_hooks.install(["claude-code"], "user")
    assert rc == 0
    payload = json.loads(cfg.read_text())
    assert payload["model"] == "claude-sonnet-4-5"
    assert payload["theme"] == "dark"
    assert "UserPromptSubmit" in payload["hooks"]
    assert "PostToolUse" in payload["hooks"]
    assert "Stop" in payload["hooks"]


def test_install_invalid_json_exits_non_zero(fake_home) -> None:
    cfg = fake_home / ".claude" / "settings.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("{ not valid json")
    with pytest.raises(SystemExit):
        install_hooks.install(["claude-code"], "user")


def test_install_force_replace_drops_existing_keys(fake_home) -> None:
    cfg = fake_home / ".claude" / "settings.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"model": "x", "theme": "dark"}))
    install_hooks.install(["claude-code"], "user", force_replace=True)
    payload = json.loads(cfg.read_text())
    assert "model" not in payload
    assert "theme" not in payload
    assert "hooks" in payload


def test_install_dry_run_writes_nothing(fake_home) -> None:
    rc = install_hooks.install(["claude-code"], "user", dry_run=True)
    assert rc == 0
    assert not (fake_home / ".claude" / "settings.json").exists()


def test_install_codex_writes_script_and_absolute_path(fake_home) -> None:
    rc = install_hooks.install(["codex"], "user")
    assert rc == 0
    cfg = fake_home / ".codex" / "config.toml"
    script = fake_home / ".codex" / "hooks" / "codex-notify.sh"
    assert cfg.exists()
    assert script.exists()
    body = cfg.read_text()
    assert str(script) in body
    assert "__PA1_NOTIFY_PATH__" not in body
    mode = script.stat().st_mode
    assert mode & stat.S_IXUSR  # executable for owner


def test_install_aider_drops_wrapper_next_to_pa1_lint(fake_home, monkeypatch) -> None:
    """When pa1-lint is on PATH, wrapper goes in the same dir."""
    fake_bin = fake_home / "bin"
    fake_bin.mkdir()
    fake_pa1 = fake_bin / "pa1-lint"
    fake_pa1.write_text("#!/bin/sh\necho pa1-lint stub\n")
    fake_pa1.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ.get("PATH", ""))

    rc = install_hooks.install(["aider"], "user")
    assert rc == 0
    wrapper = fake_bin / "pa1-lint-aider"
    assert wrapper.exists()
    assert wrapper.stat().st_mode & stat.S_IXUSR


def test_install_unknown_agent_returns_one(fake_home) -> None:
    rc = install_hooks.install(["bogus"], "user")
    assert rc == 1


def test_install_all_writes_four_configs(fake_home) -> None:
    rc = install_hooks.install(
        ["claude-code", "cursor", "cody", "codex"], "user"
    )
    assert rc == 0
    assert (fake_home / ".claude" / "settings.json").exists()
    assert (fake_home / ".cursor" / "hooks.json").exists()
    assert (fake_home / ".config" / "sourcegraph" / "cody.json").exists()
    assert (fake_home / ".codex" / "config.toml").exists()


# ---- templates are accessible from installed package ------------------------


def test_templates_loadable() -> None:
    for name in (
        "claude-code.json",
        "cursor.json",
        "cody.json",
        "codex.toml",
        "codex-notify.sh",
        "aider.sh",
    ):
        body = install_hooks._read_text(name)
        assert len(body) > 0, name