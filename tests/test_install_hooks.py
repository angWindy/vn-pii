"""Tests for ``pii-lint install-hooks`` and ``pii-lint init``/``uninstall``.

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
    # 1 settings.json + 1 pretooluse script (PreToolUse needs JSON parsing
    # in a real shell, not a one-liner — so we ship a sibling script).
    assert len(plans) == 2
    p = plans[0]
    assert p.target == fake_home / ".claude" / "settings.json"
    assert p.kind == "json"
    assert p.template_name == "claude-code.json"
    s = plans[1]
    assert s.target == fake_home / ".claude" / "hooks" / "pii-lint-pretooluse.sh"
    assert s.kind == "bash_wrapper"
    assert s.template_name == "claude-pretooluse.sh"


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
    assert "PreToolUse" in payload["hooks"]
    assert "PostToolUse" in payload["hooks"]
    assert "Stop" in payload["hooks"]


def test_install_claude_code_writes_pretooluse_script(fake_home) -> None:
    """PreToolUse needs a sibling bash script for JSON parsing."""
    rc = install_hooks.install(["claude-code"], "user")
    assert rc == 0
    script = fake_home / ".claude" / "hooks" / "pii-lint-pretooluse.sh"
    assert script.exists()
    assert script.stat().st_mode & stat.S_IXUSR
    body = script.read_text()
    assert "__PII_PRETOOLUSE_PATH__" not in body  # no placeholder left
    # And the JSON must point at the script's absolute path.
    settings = json.loads(
        (fake_home / ".claude" / "settings.json").read_text()
    )
    pre = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert str(script) in pre
    assert "__PII_PRETOOLUSE_PATH__" not in pre


def test_install_claude_code_pretooluse_blocks_known_bad_payload(
    tmp_path, fake_home
) -> None:
    """End-to-end: feeding the script a Write call with a phone number
    must exit 2 so Claude re-prompts. Uses a stub pii-lint via PATH."""
    install_hooks.install(["claude-code"], "user")
    script = fake_home / ".claude" / "hooks" / "pii-lint-pretooluse.sh"
    # Drop a stub pii-lint into a fake bin, point PATH at it.
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "pii-lint"
    stub.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"scan\" ]; then echo 'PHONE HIGH 0912345678'; exit 1; fi\n"
        "exit 0\n"
    )
    stub.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
    payload = json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "test.csv",
                "content": "name,phone\nA,0912345678\n",
            },
        }
    )
    proc = subprocess.run(
        ["bash", str(script)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "PreToolUse blocked" in proc.stderr


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
    assert "__PII_NOTIFY_PATH__" not in body
    mode = script.stat().st_mode
    assert mode & stat.S_IXUSR  # executable for owner


def test_install_aider_drops_wrapper_next_to_pii_lint(fake_home, monkeypatch) -> None:
    """When pii-lint is on PATH, wrapper goes in the same dir."""
    fake_bin = fake_home / "bin"
    fake_bin.mkdir()
    fake_pa1 = fake_bin / "pii-lint"
    fake_pa1.write_text("#!/bin/sh\necho pii-lint stub\n")
    fake_pa1.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ.get("PATH", ""))

    rc = install_hooks.install(["aider"], "user")
    assert rc == 0
    wrapper = fake_bin / "pii-lint-aider"
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
# pii-lint init / uninstall  (global git hook)
# ===========================================================================


def test_init_sets_hooks_path_and_writes_hook(isolated_git_env) -> None:
    assert install_git.install() == 0
    hook = isolated_git_env / ".githooks" / "pre-commit"
    assert hook.exists()
    assert hook.stat().st_mode & stat.S_IXUSR
    assert install_git.current_hooks_path() == str(isolated_git_env / ".githooks")


def test_init_hook_uses_resolver_not_hard_pinned_python(isolated_git_env) -> None:
    """Hook must call the resolver script, NOT a hard-pinned Python.

    A hard-pinned path silently breaks when the user reinstalls pii-lint
    into a different conda env. The resolver locates a working Python at
    hook-time so the hook survives env switches.
    """
    install_git.install()
    body = (isolated_git_env / ".githooks" / "pre-commit").read_text()
    resolver = str(isolated_git_env / ".githooks" / "pii-lint-resolver.sh")
    # Hook must reference the resolver by absolute path, not sys.executable.
    assert f'RESOLVER="{resolver}"' in body
    assert '"$RESOLVER" -m pii_linter scan --staged' in body
    # No hard-pinned $PY, no bare `pii-lint` or `python -m` call — both
    # are PATH/explicit-Python deps that the resolver exists to remove.
    assert "$PY" not in body
    assert "pii-lint scan" not in body
    assert "\npii-lint" not in body
    assert 'python -m' not in body


def test_init_writes_resolver_script(isolated_git_env) -> None:
    """The resolver script is a sibling file the hook calls."""
    install_git.install()
    resolver = isolated_git_env / ".githooks" / "pii-lint-resolver.sh"
    assert resolver.exists()
    assert resolver.stat().st_mode & stat.S_IXUSR
    body = resolver.read_text()
    # The resolver auto-scans — no env names should be hard-coded.
    assert "import pii_linter" in body
    assert "python3" in body
    assert "scan_conda_root" in body  # auto-scan helper
    # Sanity: no per-name probe left over from the old design.
    assert "cand_conda pii" not in body
    assert "cand_conda test" not in body


def test_resolver_finds_python_in_conda_env(tmp_path) -> None:
    """Resolver auto-discovers conda envs without hard-coded names.

    We create a conda-style layout with a *non-standard* env name
    (e.g. ``team_venv``) and verify the resolver picks it. The point
    is to prove the resolver does not depend on the names pii or test;
    it scans every env under each search root.
    """
    test_py = str(Path(sys.executable).resolve())
    if not Path(test_py).exists():
        pytest.skip(f"test interpreter not present: {test_py}")
    # Sanity: the candidate env must actually have pii_linter importable.
    sanity = subprocess.run(
        [test_py, "-c", "import pii_linter"],
        capture_output=True, text=True,
    )
    if sanity.returncode != 0:
        pytest.skip(f"real interpreter cannot import pii_linter: {sanity.stderr}")
    # Build a fake $HOME/miniconda3 with a *non-standard* env name.
    fake_home = tmp_path / "home"
    envs = fake_home / "miniconda3" / "envs" / "team_venv" / "bin"
    envs.mkdir(parents=True)
    (envs / "python3.11").symlink_to(test_py)
    # No PATH, no CONDA_PREFIX — only the auto-scan under fake_home/miniconda3
    # can find this. Keep bash on PATH so the resolver can launch itself.
    bash = "/usr/bin/bash" if Path("/usr/bin/bash").exists() else shutil_which("bash")
    assert bash, "bash required for resolver test"
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["PATH"] = str(Path(bash).parent)  # bash's dir, nothing else
    env.pop("CONDA_PREFIX", None)
    resolver = fake_home / "resolver.sh"
    import shutil as _shutil
    _shutil.copy(
        "/home/tts/Dev/Personal/vn-pii/pii_linter/hooks/templates/pii-lint-resolver.sh",
        resolver,
    )
    resolver.chmod(0o755)
    proc = subprocess.run(
        [str(resolver), "-c", "import pii_linter; print('resolver-pick')"],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert "resolver-pick" in proc.stdout


def test_resolver_skips_broken_envs_and_picks_working_one(tmp_path) -> None:
    """A stub Python that fails `import pii_linter` must be skipped.

    When multiple envs exist, the resolver walks them in order; the
    first one that probes successfully wins. Broken envs (env exists
    but lib missing) must not block or crash.
    """
    test_py = str(Path(sys.executable).resolve())
    if not Path(test_py).exists():
        pytest.skip(f"test interpreter not present: {test_py}")
    sanity = subprocess.run(
        [test_py, "-c", "import pii_linter"],
        capture_output=True, text=True,
    )
    if sanity.returncode != 0:
        pytest.skip("real interpreter cannot import pii_linter")
    fake_home = tmp_path / "home"
    # Broken env: stub that always exits 1.
    broken_bin = fake_home / "miniconda3" / "envs" / "broken" / "bin"
    broken_bin.mkdir(parents=True)
    (broken_bin / "python3.11").write_text("#!/bin/sh\nexit 1\n")
    (broken_bin / "python3.11").chmod(0o755)
    # Working env: symlink to the running test interpreter.
    good_bin = fake_home / "miniconda3" / "envs" / "good" / "bin"
    good_bin.mkdir(parents=True)
    (good_bin / "python3.11").symlink_to(test_py)
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    bash = "/usr/bin/bash" if Path("/usr/bin/bash").exists() else shutil_which("bash")
    assert bash, "bash required for resolver test"
    env["PATH"] = str(Path(bash).parent)
    env.pop("CONDA_PREFIX", None)
    resolver = fake_home / "resolver.sh"
    import shutil as _shutil
    _shutil.copy(
        "/home/tts/Dev/Personal/vn-pii/pii_linter/hooks/templates/pii-lint-resolver.sh",
        resolver,
    )
    resolver.chmod(0o755)
    proc = subprocess.run(
        [str(resolver), "-c", "import pii_linter; print('good-pick')"],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert "good-pick" in proc.stdout


def test_resolver_fails_closed_when_no_python_has_lib(tmp_path) -> None:
    """No candidate interpreter has pii_linter -> resolver exits 1.

    Each candidate is replaced with a stub Python that always fails the
    ``import pii_linter`` probe. We also force PATH to a dir with no
    Python at all so the system interpreter is not picked up.
    """
    bash = "/usr/bin/bash" if Path("/usr/bin/bash").exists() else shutil_which("bash")
    assert bash, "bash required for resolver test"
    fake_home = tmp_path / "empty_home"
    fake_home.mkdir()
    # Provide a bare-bones bin dir on PATH that has bash but no python.
    bare_bin = tmp_path / "bare_bin"
    bare_bin.mkdir()
    (bare_bin / "bash").symlink_to(bash)
    # Stub every well-known conda root with a "no lib" Python.
    fake_mini = fake_home / "miniconda3" / "envs"
    fake_mini.mkdir(parents=True)
    for env_name in ("myenv_a", "myenv_b"):
        env_bin = fake_mini / env_name / "bin"
        env_bin.mkdir(parents=True)
        stub = env_bin / "python3.11"
        stub.write_text("#!/bin/sh\nexit 1\n")
        stub.chmod(0o755)
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["PATH"] = str(bare_bin)  # bash only, no python
    env.pop("CONDA_PREFIX", None)
    resolver = fake_home / "resolver.sh"
    import shutil as _shutil
    _shutil.copy(
        "/home/tts/Dev/Personal/vn-pii/pii_linter/hooks/templates/pii-lint-resolver.sh",
        resolver,
    )
    resolver.chmod(0o755)
    proc = subprocess.run(
        [str(resolver), "-c", "import pii_linter"],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "no Python interpreter" in proc.stderr


def test_init_hook_fails_closed_when_resolver_missing(
    isolated_git_env, monkeypatch
) -> None:
    """If the resolver vanishes the hook must not silently approve."""
    # precommit_body default placeholder is __PII_RESOLVER_PATH__; replace
    # it with a path that definitely does not exist on disk.
    body = install_git.precommit_body().replace(
        "__PII_RESOLVER_PATH__", "/nonexistent/pii-lint-resolver.sh"
    )
    assert '[ ! -x "$RESOLVER" ]' in body
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
    assert state == {"marker": "pii-lint", "set_hooks_path": True}


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
    (home / ".pii-state").write_text("{}")  # unused; keeps dir non-empty
    cfg = tmp_path / "gitconfig"
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["GIT_CONFIG_GLOBAL"] = str(cfg)
    env["GIT_CONFIG_NOSYSTEM"] = "1"

    # Write the shims the way install() does. The pre-commit needs the
    # resolver script present so it does not fail closed on resolver-missing.
    (hooks / "pii-lint-resolver.sh").write_text(
        install_git._read_template("pii-lint-resolver.sh")
    )
    (hooks / "pii-lint-resolver.sh").chmod(0o755)
    (hooks / "pre-commit").write_text(
        install_git.precommit_body(str(hooks / "pii-lint-resolver.sh"))
    )
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
    # The PII hook ran (clean, exit 0) *and* the repo's own hook still ran.
    assert marker.exists(), "repo commit-msg hook was orphaned by core.hooksPath"


def test_cli_init_and_uninstall_roundtrip(isolated_git_env) -> None:
    """`pii-lint init` / `uninstall` are wired to the module."""
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