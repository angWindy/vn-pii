"""Tests for ``pa1-lint install-hooks`` and ``pa1-lint init``/``uninstall``.

We exercise both install paths against a sandboxed HOME and an isolated
``--project`` target. The tests do NOT touch the real ``$HOME`` or the real
``~/.gitconfig``: ``GIT_CONFIG_GLOBAL`` is redirected into ``tmp_path``.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from pii_linter.hooks import install_hooks, install_git


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


@pytest.fixture
def sandbox_gitconfig(tmp_path, monkeypatch) -> Path:
    """Redirect global git config into tmp_path so the real one is safe."""
    cfg = tmp_path / "gitconfig-sandbox"
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    return cfg


@pytest.fixture
def isolated_git_env(fake_home, sandbox_gitconfig) -> Path:
    """HOME + global git config both sandboxed, for `init`/`uninstall`."""
    return fake_home


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


# ===========================================================================
# pa1-lint init / uninstall  (global git hook)
# ===========================================================================


def test_init_sets_hooks_path_and_writes_hook(isolated_git_env) -> None:
    assert install_git.install() == 0
    hook = isolated_git_env / ".githooks" / "pre-commit"
    assert hook.exists()
    assert hook.stat().st_mode & stat.S_IXUSR
    assert install_git.current_hooks_path() == str(isolated_git_env / ".githooks")


def test_init_hook_uses_absolute_interpreter_not_bare_pa1(isolated_git_env) -> None:
    """A hook that needs PATH is a hook that silently approves everything."""
    install_git.install()
    body = (isolated_git_env / ".githooks" / "pre-commit").read_text()
    py = str(Path(sys.executable).resolve())
    # Pinned to an absolute interpreter, invoked via the $PY variable.
    assert f'PY="{py}"' in body
    assert '"$PY" -m pii_linter scan --staged' in body
    # No bare `pa1-lint` or bare `python` call, either of which is a PATH dep.
    assert "pa1-lint scan" not in body
    assert "\npa1-lint" not in body
    assert 'python -m' not in body


def test_init_hook_fails_closed_when_interpreter_missing(
    isolated_git_env, monkeypatch
) -> None:
    """If the interpreter vanishes the hook must block, not skip the scan."""
    body = install_git.precommit_body().replace(
        str(Path(sys.executable).resolve()), "/nonexistent/python"
    )
    assert '[ ! -x "$PY" ]' in body
    assert "exit 1" in body
    assert "did NOT run" in body


def test_init_writes_passthrough_shims(isolated_git_env) -> None:
    """core.hooksPath replaces .git/hooks, so repo hooks need forwarding."""
    install_git.install()
    for name in install_git.PASSTHROUGH_HOOKS:
        shim = isolated_git_env / ".githooks" / name
        assert shim.exists(), name
        assert shim.stat().st_mode & stat.S_IXUSR, name
        body = shim.read_text()
        assert f'"$DIR/hooks/{name}"' in body, name


def test_init_dry_run_changes_nothing(isolated_git_env) -> None:
    assert install_git.install(dry_run=True) == 0
    assert not (isolated_git_env / ".githooks").exists()
    assert install_git.current_hooks_path() is None


def test_init_refuses_to_clobber_foreign_hook(isolated_git_env) -> None:
    """Overwriting a hook manager (husky) would break every commit."""
    hooks = isolated_git_env / ".githooks"
    hooks.mkdir(parents=True)
    foreign = hooks / "pre-commit"
    foreign.write_text('#!/bin/sh\n# husky-managed\necho husky\n')
    foreign.chmod(0o755)

    assert install_git.install() == 1
    # Untouched: still husky's file, byte for byte.
    assert foreign.read_text() == '#!/bin/sh\n# husky-managed\necho husky\n'
    assert install_git.current_hooks_path() is None


def test_init_adopts_existing_hooks_path_without_resetting(
    isolated_git_env, tmp_path
) -> None:
    """If the user already set core.hooksPath we use it and do not re-set it."""
    existing = tmp_path / "user-hooks"
    existing.mkdir()
    subprocess.run(
        ["git", "config", "--global", "core.hooksPath", str(existing)],
        check=True,
        capture_output=True,
    )
    assert install_git.install() == 0
    assert (existing / "pre-commit").exists()
    assert install_git.current_hooks_path() == str(existing)
    # We did not set it, so uninstall must leave the config alone.
    state = json.loads((existing / install_git.STATE_FILE).read_text())
    assert state["set_hooks_path"] is False


def test_init_is_idempotent(isolated_git_env) -> None:
    assert install_git.install() == 0
    assert install_git.install() == 0  # second run overwrites our own hook
    assert (isolated_git_env / ".githooks" / "pre-commit").exists()


def test_uninstall_removes_hooks_and_unsets_config(isolated_git_env) -> None:
    install_git.install()
    assert install_git.uninstall() == 0
    assert not (isolated_git_env / ".githooks" / "pre-commit").exists()
    assert not (isolated_git_env / ".githooks" / install_git.STATE_FILE).exists()
    assert install_git.current_hooks_path() is None


def test_uninstall_keeps_config_it_did_not_set(isolated_git_env, tmp_path) -> None:
    existing = tmp_path / "user-hooks"
    existing.mkdir()
    subprocess.run(
        ["git", "config", "--global", "core.hooksPath", str(existing)],
        check=True,
        capture_output=True,
    )
    install_git.install()
    install_git.uninstall()
    assert install_git.current_hooks_path() == str(existing)


def test_uninstall_never_deletes_foreign_hook(isolated_git_env) -> None:
    hooks = isolated_git_env / ".githooks"
    hooks.mkdir(parents=True)
    foreign = hooks / "commit-msg"
    foreign.write_text("#!/bin/sh\n# not ours\n")
    foreign.chmod(0o755)
    install_git.install()
    install_git.uninstall()
    assert foreign.exists()
    assert foreign.read_text() == "#!/bin/sh\n# not ours\n"


def test_uninstall_is_a_noop_when_not_installed(isolated_git_env) -> None:
    assert install_git.uninstall() == 0


def test_init_records_state(isolated_git_env) -> None:
    install_git.install()
    state = json.loads(
        (isolated_git_env / ".githooks" / install_git.STATE_FILE).read_text()
    )
    assert state == {"marker": "pa1-lint", "set_hooks_path": True}


def test_init_survives_git_config_failure(isolated_git_env, monkeypatch) -> None:
    """A git that cannot be configured must not lose the written hook."""
    install_git.install()
    # Point git config at an unwritable path: writing files still succeeds,
    # the config write is what fails.
    broken = isolated_git_env / "no-such-dir" / "cfg"
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(broken))
    assert install_git.install() == 1  # reports the failure
    assert (isolated_git_env / ".githooks" / "pre-commit").exists()  # still there


def test_hook_passthrough_actually_runs_repo_commit_msg(tmp_path) -> None:
    """End-to-end: a repo's own commit-msg hook survives core.hooksPath.

    This is the regression that matters. core.hooksPath *replaces* the hook
    lookup dir, so without the shim a repo silently loses its commit-msg.
    """
    if not shutil_which("git"):
        pytest.skip("git not on PATH")

    home = tmp_path / "home"
    hooks = home / ".githooks"
    hooks.mkdir(parents=True)
    (home / ".pa1-state").write_text("{}")  # unused; keeps dir non-empty
    cfg = tmp_path / "gitconfig"
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["GIT_CONFIG_GLOBAL"] = str(cfg)
    env["GIT_CONFIG_NOSYSTEM"] = "1"

    # Write the shims the way install() does.
    (hooks / "pre-commit").write_text(install_git.precommit_body())
    (hooks / "pre-commit").chmod(0o755)
    for name in install_git.PASSTHROUGH_HOOKS:
        p = hooks / name
        p.write_text(install_git.passthrough_body(name))
        p.chmod(0o755)
    subprocess.run(
        ["git", "config", "--global", "core.hooksPath", str(hooks)],
        check=True, capture_output=True, env=env,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    (repo / ".git" / "hooks").mkdir(exist_ok=True)
    marker = repo / "MARKER"
    (repo / ".git" / "hooks" / "commit-msg").write_text(
        f'#!/bin/sh\ntouch "{marker}"\n'
    )
    (repo / ".git" / "hooks" / "commit-msg").chmod(0o755)
    for k, v in (("user.email", "t@t.t"), ("user.name", "t")):
        subprocess.run(
            ["git", "config", k, v], cwd=repo, check=True,
            capture_output=True, env=env,
        )

    (repo / "clean.csv").write_text("name,note\nalpha,ok\n")
    subprocess.run(["git", "add", "clean.csv"], cwd=repo, check=True, env=env)
    proc = subprocess.run(
        ["git", "commit", "-q", "-m", "x"],
        cwd=repo, capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    # The PA1 hook ran (clean, exit 0) *and* the repo's own hook still ran.
    assert marker.exists(), "repo commit-msg hook was orphaned by core.hooksPath"


def test_cli_init_and_uninstall_roundtrip(isolated_git_env) -> None:
    """`pa1-lint init` / `uninstall` are wired to the module."""
    from pii_linter import cli

    assert cli.main(["init"]) == 0
    assert (isolated_git_env / ".githooks" / "pre-commit").exists()
    assert cli.main(["uninstall"]) == 0
    assert not (isolated_git_env / ".githooks" / "pre-commit").exists()


def test_cli_init_is_not_rewritten_to_scan(isolated_git_env) -> None:
    """Regression: _normalise_argv must not turn `init` into `scan init`."""
    from pii_linter import cli

    assert cli._normalise_argv(["init"]) == ["init"]
    assert cli._normalise_argv(["uninstall"]) == ["uninstall"]
    assert cli._normalise_argv([]) == ["scan", "."]


def shutil_which(name: str) -> str | None:
    """Local helper: avoid importing shutil just for `which` in one test."""
    from shutil import which

    return which(name)