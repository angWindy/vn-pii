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
    """A real git repo at tmp_path/repo, with cwd set to it.

    Uses `git init` rather than a hand-rolled `.git` directory so the
    repo is actually exercisable by `git commit` etc. during the E2E
    tests further down.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", str(repo)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "t@t.t"],
        cwd=str(repo), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=str(repo), check=True, capture_output=True,
    )
    monkeypatch.chdir(repo)
    return repo


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
# pii-lint init / uninstall  (per-repo git hook, in <repo>/.git/hooks/)
# ===========================================================================
#
# The previous global install model — ~/.githooks/ + core.hooksPath — was
# replaced with a per-repo opt-in: `cd` into a repo, run `pii-lint init`,
# and the hooks land in that repo's .git/hooks/. Tests below exercise
# every case that matters for the new model. The resolver-script tests
# further down are kept verbatim because the resolver script itself is
# unchanged — only its location moved.


def test_init_writes_hooks_to_dot_git_hooks(fake_repo) -> None:
    """`init` writes into <repo>/.git/hooks/."""
    assert install_git.install() == 0
    pre_commit = fake_repo / ".git" / "hooks" / "pre-commit"
    assert pre_commit.exists()
    assert pre_commit.stat().st_mode & stat.S_IXUSR
    body = pre_commit.read_text()
    assert install_git.MARKER in body
    # The pre-push hook and resolver live next to pre-commit.
    assert (fake_repo / ".git" / "hooks" / "pre-push").exists()
    assert (fake_repo / ".git" / "hooks" / "pii-lint-resolver.sh").exists()


def test_init_does_not_create_githooks_dir(fake_repo) -> None:
    """`init` must not touch ``$HOME/.githooks/`` (the old global dir)."""
    githooks = Path.home() / ".githooks"
    if githooks.exists():
        # If a stale global install is lying around (e.g. from a prior
        # version of pii-lint), snapshot its mtime and verify `init` did
        # not bump it. We do not delete the directory — that is the
        # user's responsibility (`pii-lint uninstall` from any shell).
        before_mtime = githooks.stat().st_mtime
    else:
        before_mtime = None
    assert install_git.install() == 0
    if before_mtime is not None:
        assert githooks.stat().st_mtime == before_mtime, (
            "init modified $HOME/.githooks/ — it must leave global state alone"
        )


def test_init_does_not_touch_global_git_config(fake_repo) -> None:
    """`init` is local to the repo. It must not set core.hooksPath."""
    rc = subprocess.run(
        ["git", "config", "--global", "--get", "core.hooksPath"],
        capture_output=True, text=True,
    )
    assert rc.returncode != 0, (
        "test precondition: the test runner must not have a global "
        "core.hooksPath set, or this test cannot prove `init` is local."
    )
    assert install_git.install() == 0
    rc = subprocess.run(
        ["git", "config", "--global", "--get", "core.hooksPath"],
        capture_output=True, text=True,
    )
    assert rc.returncode != 0, "init must not set core.hooksPath globally"


def test_init_refuses_outside_git_repo(tmp_path, monkeypatch) -> None:
    """`init` in a non-git dir exits 1 with a clear message."""
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    monkeypatch.chdir(not_a_repo)
    rc = install_git.install()
    assert rc == 1


def test_init_idempotent(fake_repo) -> None:
    """Running init twice overwrites our own hook without complaint."""
    assert install_git.install() == 0
    pre_commit = fake_repo / ".git" / "hooks" / "pre-commit"
    first_body = pre_commit.read_text()
    assert install_git.install() == 0
    second_body = pre_commit.read_text()
    # The body text is byte-identical for an idempotent run; the second
    # run did not error out. mtime is bumped by the rewrite, but that
    # is a write concern, not a test concern.
    assert first_body == second_body


def test_init_dry_run_writes_nothing(fake_repo) -> None:
    assert install_git.install(dry_run=True) == 0
    hooks = fake_repo / ".git" / "hooks"
    # Either the hooks dir does not exist, or it is the empty stub git
    # created during `git init`.
    if hooks.exists():
        for p in hooks.iterdir():
            assert p.name.endswith(".sample"), p.name


def test_init_writes_precommit_with_resolver_path(fake_repo) -> None:
    """pre-commit must call the resolver, not a hard-pinned Python."""
    assert install_git.install() == 0
    body = (fake_repo / ".git" / "hooks" / "pre-commit").read_text()
    resolver = str(fake_repo / ".git" / "hooks" / "pii-lint-resolver.sh")
    assert f'RESOLVER="{resolver}"' in body
    assert '"$RESOLVER" -m pii_linter scan --staged' in body
    # No hard-pinned Python and no bare `pii-lint` invocation in the hook.
    assert "$PY" not in body
    assert "python -m" not in body


def test_init_writes_prepush_with_pushed_range_args(fake_repo) -> None:
    """pre-push must use the new --pushed-base / --pushed-head args."""
    assert install_git.install() == 0
    body = (fake_repo / ".git" / "hooks" / "pre-push").read_text()
    assert "scan --pushed-base" in body
    assert "--pushed-head" in body
    assert "EMPTY_TREE=4b825dc642cb6eb9a060e54bf8d69288fbee4904" in body
    # Fails closed if the resolver has vanished.
    assert "exit 2" in body


def test_init_writes_passthrough_shims(fake_repo) -> None:
    """commit-msg, prepare-commit-msg etc. get a passthrough shim."""
    assert install_git.install() == 0
    for name in install_git.PASSTHROUGH_HOOKS:
        shim = fake_repo / ".git" / "hooks" / name
        assert shim.exists(), name
        assert shim.stat().st_mode & stat.S_IXUSR, name
        body = shim.read_text()
        # Shim forwards to the `.real` companion, NOT the bare name
        # (forwarding to the bare name would re-invoke the shim and
        # loop forever — see the regression that motivated this check).
        assert f'"$DIR/hooks/{name}.real"' in body, name


def test_init_chains_existing_precommit(fake_repo) -> None:
    """A foreign pre-commit gets moved to pre-commit.real and chained."""
    foreign = fake_repo / ".git" / "hooks" / "pre-commit"
    foreign.write_text("#!/bin/sh\necho USER_HOOK\n")
    foreign.chmod(0o755)

    assert install_git.install() == 0
    # The original is preserved at .real, untouched.
    real = fake_repo / ".git" / "hooks" / "pre-commit.real"
    assert real.exists()
    assert real.read_text() == "#!/bin/sh\necho USER_HOOK\n"
    # The new pre-commit chains to .real after a clean scan.
    body = foreign.read_text()
    assert install_git.MARKER in body
    assert "pre-commit.real" in body
    assert '"$SCAN_RC" = "0"' in body


def test_init_chains_existing_passthrough_hook(fake_repo) -> None:
    """A foreign commit-msg also chains via .real (regression: a shim
    that forwards to its own name would loop forever)."""
    foreign = fake_repo / ".git" / "hooks" / "commit-msg"
    foreign.write_text("#!/bin/sh\necho USER_COMMIT_MSG\n")
    foreign.chmod(0o755)

    assert install_git.install() == 0
    real = fake_repo / ".git" / "hooks" / "commit-msg.real"
    assert real.exists()
    assert real.read_text() == "#!/bin/sh\necho USER_COMMIT_MSG\n"
    shim = foreign.read_text()
    assert install_git.MARKER in shim
    assert "commit-msg.real" in shim
    # The shim must NOT forward to the bare name (would loop).
    assert '"$DIR/hooks/commit-msg"' not in shim


def test_uninstall_removes_pii_lint_hooks(fake_repo) -> None:
    assert install_git.install() == 0
    assert install_git.uninstall() == 0
    # Every file we wrote must be gone.
    for name in install_git.FULL_HOOKS:
        assert not (fake_repo / ".git" / "hooks" / name).exists(), name
    for name in install_git.PASSTHROUGH_HOOKS:
        assert not (fake_repo / ".git" / "hooks" / name).exists(), name
    assert not (fake_repo / ".git" / "hooks" / "pii-lint-resolver.sh").exists()


def test_uninstall_restores_chained_precommit(fake_repo) -> None:
    """After uninstall, pre-commit.real becomes pre-commit again."""
    foreign = fake_repo / ".git" / "hooks" / "pre-commit"
    foreign.write_text("#!/bin/sh\necho USER_HOOK\n")
    foreign.chmod(0o755)
    install_git.install()
    assert (fake_repo / ".git" / "hooks" / "pre-commit.real").exists()
    install_git.uninstall()
    # .real was renamed back to the bare name with the original content.
    assert (fake_repo / ".git" / "hooks" / "pre-commit").exists()
    assert (fake_repo / ".git" / "hooks" / "pre-commit").read_text() == "#!/bin/sh\necho USER_HOOK\n"
    assert not (fake_repo / ".git" / "hooks" / "pre-commit.real").exists()


def test_uninstall_never_deletes_foreign_hook(fake_repo) -> None:
    """A hook the user installed by hand must survive uninstall."""
    # A non-pii foreign pre-commit, with no .real companion: the move
    # step should set up the chain, then uninstall should restore.
    foreign = fake_repo / ".git" / "hooks" / "pre-commit"
    foreign.write_text("#!/bin/sh\n# hand-rolled, not ours\n")
    foreign.chmod(0o755)
    install_git.install()
    # Sanity: we are now chained (so .real exists).
    assert (fake_repo / ".git" / "hooks" / "pre-commit.real").exists()
    install_git.uninstall()
    # The hand-rolled hook is back in place untouched.
    assert foreign.read_text() == "#!/bin/sh\n# hand-rolled, not ours\n"


def test_uninstall_noop_when_nothing_installed(fake_repo) -> None:
    """`uninstall` in a clean repo exits 0, prints a no-op message."""
    assert install_git.uninstall() == 0


def test_uninstall_outside_git_repo(tmp_path, monkeypatch) -> None:
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    monkeypatch.chdir(not_a_repo)
    assert install_git.uninstall() == 0


def test_init_in_worktree(fake_repo, tmp_path, monkeypatch) -> None:
    """Init inside a `git worktree` lands in the worktree's own hooks dir.

    `git worktree add` puts a `.git` *file* (not dir) in the worktree
    whose contents is `gitdir: <main>/.git/worktrees/<name>`. Hooks
    written there are picked up by git when run from the worktree.
    """
    # `git worktree add` requires at least one commit in the main repo.
    (fake_repo / "README.md").write_text("# test\n")
    subprocess.run(["git", "add", "README.md"], cwd=str(fake_repo), check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"],
        cwd=str(fake_repo), check=True, capture_output=True,
    )
    wt = tmp_path / "wt"
    subprocess.run(
        ["git", "worktree", "add", "-q", str(wt), "HEAD"],
        cwd=str(fake_repo), check=True, capture_output=True,
    )
    monkeypatch.chdir(wt)
    assert install_git.install() == 0
    # The hooks must land in the worktree's private git dir, not the
    # main repo's .git/hooks/. Git's own lookup for a worktree goes
    # through the per-worktree dir, so the hooks must live there to
    # fire when committing from the worktree.
    wt_git_file = wt / ".git"
    assert wt_git_file.is_file()
    wt_git_dir = Path(
        wt_git_file.read_text().strip().split(":", 1)[1].strip()
    )
    assert wt_git_dir.is_dir()
    pre_commit = wt_git_dir / "hooks" / "pre-commit"
    assert pre_commit.exists(), f"expected hook at {pre_commit}"
    assert install_git.MARKER in pre_commit.read_text()


def test_cli_init_and_uninstall_roundtrip(fake_repo) -> None:
    """`pii-lint init` / `uninstall` are wired to the module."""
    from pii_linter import cli

    assert cli.main(["init"]) == 0
    assert (fake_repo / ".git" / "hooks" / "pre-commit").exists()
    assert cli.main(["uninstall"]) == 0
    assert not (fake_repo / ".git" / "hooks" / "pre-commit").exists()


def test_cli_init_refuses_outside_git_repo(tmp_path, monkeypatch) -> None:
    from pii_linter import cli

    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    monkeypatch.chdir(not_a_repo)
    assert cli.main(["init"]) == 1


def test_cli_init_is_not_rewritten_to_scan(fake_repo) -> None:
    """Regression: _normalise_argv must not turn `init` into `scan init`."""
    from pii_linter import cli

    assert cli._normalise_argv(["init"]) == ["init"]
    assert cli._normalise_argv(["uninstall"]) == ["uninstall"]
    assert cli._normalise_argv([]) == ["scan", "."]


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


def test_init_hook_fails_closed_when_resolver_missing() -> None:
    """If the resolver vanishes the hook must not silently approve."""
    # precommit_body default placeholder is __PII_RESOLVER_PATH__; replace
    # it with a path that definitely does not exist on disk.
    body = install_git.precommit_body().replace(
        "__PII_RESOLVER_PATH__", "/nonexistent/pii-lint-resolver.sh"
    )
    assert '[ ! -x "$RESOLVER" ]' in body
    assert "exit 1" in body
    assert "did NOT run" in body


def test_init_hook_unstages_pii_files() -> None:
    """On a HIGH+ finding the pre-commit hook unstages the offending file.

    The hook parses the JSON scan output, collects every file that has
    at least one HIGH/CRITICAL finding, and runs ``git reset HEAD --``
    for each one before exiting non-zero. The point is that a user who
    runs ``git add . && git commit`` on a workspace full of mixed
    data wants to know *which file* tripped the scan, not have it
    sit silently in the index ready to leak on the next commit.
    """
    body = install_git.precommit_body()
    # Capture the scan as JSON so we can read the file list back out.
    assert "scan --staged --format json" in body
    # Parse the JSON and unstage every file that has a HIGH+ finding.
    assert "json.load" in body
    assert '"findings"' in body
    # Severity threshold: HIGH=3 per pii_linter/severity.py.
    assert "HIGH = 3" in body
    # The actual unstage step: `git reset HEAD -- <file>`.
    assert "git reset HEAD -- \"$f\"" in body
    # The hook must preserve the scan's exit code so the commit is
    # still blocked after the unstage.
    assert "exit $SCAN_RC" in body


def test_init_hook_renders_markdown_report_in_block_message() -> None:
    """On a HIGH+ finding the pre-commit hook also prints the same
    Markdown report that ``pii-lint scan --staged`` would print, so
    the user sees file:line + masked evidence inline without having
    to re-invoke the CLI to inspect the leak.

    The hook feeds the JSON scan output back into the same
    ``render_markdown`` helper ``pii_linter.report`` exposes, so the
    output is byte-identical to the standalone command.
    """
    body = install_git.precommit_body()
    # Render via the shared helper so the formatter stays in sync.
    assert "from pii_linter.report import render_markdown" in body
    # Reconstruct Finding + ScanResult from the JSON, then render.
    assert "ScanResult(" in body
    assert "render_markdown(result)" in body
    # The rendered report must go to stderr, not stdout, so git's
    # commit message machinery is not corrupted.
    assert "sys.stderr.write(render_markdown(result))" in body


def test_init_hook_report_uses_only_masked_evidence() -> None:
    """The report rendered in the block message must never read
    ``evidence_raw`` — only ``evidence_masked``, which is the
    display-safe form. Printing raw PII to the terminal would be a
    privacy regression for a tool whose whole job is to block leaks.
    """
    body = install_git.precommit_body()
    # The rebuilder must pull `evidence_masked` from JSON, never
    # `evidence_raw`. The Finding constructor argument must be empty.
    assert 'item.get("evidence_masked", "")' in body
    assert 'evidence_raw=""' in body
    # And the JSON key we read back must be the masked one.
    assert '"evidence_masked"' in body


def test_prepush_body_default_placeholder() -> None:
    """`prepush_body()` is a no-arg factory: the resolver path gets
    patched in by install() so the file is portable until then."""
    body = install_git.prepush_body()
    assert "__PII_RESOLVER_PATH__" in body
    assert "scan --pushed-base" in body


# ---------------------------------------------------------------------------
# End-to-end tests: invoke the agent hook scripts as Claude Code / Codex
# would invoke them, with real JSON on stdin, and verify PII is actually
# blocked. These tests do NOT mock `pii-lint` — they use the real binary
# the editable install dropped into the test env.
# ---------------------------------------------------------------------------


def _write_repo_with_files(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a git repo under tmp_path with the given file→content map.

    All files are pre-staged. The repo is configured to disable the
    test runner's user-level PII hook (so this test only sees the
    agent hook under test, not anything in ~/.githooks).
    """
    import subprocess as sp
    repo = tmp_path / "repo"
    repo.mkdir()
    sp.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    sp.run(["git", "config", "user.email", "t@t.t"], cwd=repo, check=True)
    sp.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    # Disable any inherited PII pre-commit hook for this repo only.
    sp.run(
        ["git", "config", "core.hooksPath", "/dev/null"],
        cwd=repo, check=True, capture_output=True,
    )
    for rel, content in files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return repo


def test_claude_pretooluse_blocks_pii_in_new_file_write(tmp_path: Path, pii_lint_on_path) -> None:
    """Simulate Claude Code calling PreToolUse for a Write tool call.

    Claude sends a JSON blob on stdin like:
        {"tool_name": "Write", "tool_input": {"file_path": "...", "content": "..."}}
    We feed a CSV with a phone number. The hook must extract the path,
    write content to a temp file, run pii-lint, and exit 2 to block.
    """
    import json as _json
    import subprocess as sp

    # Install hooks in user-scope so the script lands at
    # <fake_home>/.claude/hooks/pii-lint-pretooluse.sh.
    fake_home = tmp_path / "home"
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env.pop("GIT_CONFIG_GLOBAL", None)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    rc = subprocess.run(
        [sys.executable, "-m", "pii_linter", "install-hooks", "claude-code"],
        env=env, capture_output=True, text=True,
    )
    assert rc.returncode == 0, rc.stderr
    pretooluse = fake_home / ".claude" / "hooks" / "pii-lint-pretooluse.sh"
    assert pretooluse.exists()
    assert pretooluse.stat().st_mode & stat.S_IXUSR

    # Build the tool call Claude would emit.
    target_csv = "/tmp/sandbox/contacts.csv"
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": target_csv,
            "content": "name,phone\neve,0912345678\n",
        },
    }
    proc = sp.run(
        ["bash", str(pretooluse)],
        input=_json.dumps(payload), capture_output=True, text=True, env=env,
    )
    # PreToolUse contract: HIGH+ PII -> exit 2, stderr has the
    # "blocked" message so Claude sees why.
    assert proc.returncode == 2, (
        f"expected exit 2 (block), got {proc.returncode}\n"
        f"stdout: {proc.stdout!r}\nstderr: {proc.stderr!r}"
    )
    assert "blocked" in proc.stderr.lower()
    assert target_csv in proc.stderr


def test_claude_pretooluse_passes_clean_csv(tmp_path: Path, pii_lint_on_path) -> None:
    """Same harness, but the Write content has no PII -> exit 0."""
    import json as _json
    import subprocess as sp

    fake_home = tmp_path / "home"
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env.pop("GIT_CONFIG_GLOBAL", None)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    rc = subprocess.run(
        [sys.executable, "-m", "pii_linter", "install-hooks", "claude-code"],
        env=env, capture_output=True, text=True,
    )
    assert rc.returncode == 0, rc.stderr
    pretooluse = fake_home / ".claude" / "hooks" / "pii-lint-pretooluse.sh"
    target_csv = "/tmp/sandbox/clean.csv"
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": target_csv,
            "content": "name,note\nalpha,ok\n",
        },
    }
    proc = sp.run(
        ["bash", str(pretooluse)],
        input=_json.dumps(payload), capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, (
        f"expected exit 0, got {proc.returncode}\nstderr: {proc.stderr}"
    )


def test_claude_pretooluse_skips_non_pii_extensions(tmp_path: Path, pii_lint_on_path) -> None:
    """PreToolUse should be a no-op for .py/.js/etc — those are out of scope."""
    import json as _json
    import subprocess as sp

    fake_home = tmp_path / "home"
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env.pop("GIT_CONFIG_GLOBAL", None)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    subprocess.run(
        [sys.executable, "-m", "pii_linter", "install-hooks", "claude-code"],
        env=env, capture_output=True, text=True, check=True,
    )
    pretooluse = fake_home / ".claude" / "hooks" / "pii-lint-pretooluse.sh"
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/tmp/x.py",
            # Even if this content were PII, .py is not in scope, so the
            # hook must short-circuit (exit 0) without scanning.
            "content": "phone = '0912345678'\n",
        },
    }
    proc = sp.run(
        ["bash", str(pretooluse)],
        input=_json.dumps(payload), capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr


def test_claude_pretooluse_blocks_existing_csv_via_edit(tmp_path: Path, pii_lint_on_path) -> None:
    """Edit tool on an existing CSV: scan the file on disk, block on PII."""
    import json as _json
    import subprocess as sp

    fake_home = tmp_path / "home"
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env.pop("GIT_CONFIG_GLOBAL", None)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    subprocess.run(
        [sys.executable, "-m", "pii_linter", "install-hooks", "claude-code"],
        env=env, capture_output=True, text=True, check=True,
    )
    pretooluse = fake_home / ".claude" / "hooks" / "pii-lint-pretooluse.sh"
    # Existing file containing PII — the Edit path scans the file as-is.
    target = tmp_path / "leak.csv"
    target.write_text("name,phone\neve,0912345678\n")
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(target),
            "old_string": "alpha,ok",
            "new_string": "mallory,0900000000",
        },
    }
    proc = sp.run(
        ["bash", str(pretooluse)],
        input=_json.dumps(payload), capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 2, proc.stderr
    assert str(target) in proc.stderr


def test_claude_posttooluse_blocks_via_environment_variable(tmp_path: Path, pii_lint_on_path) -> None:
    """PostToolUse command string uses $CLAUDE_TOOL_FILE_PATH.

    The PostToolUse command lives in settings.json as a shell snippet.
    Run that snippet directly (it's a `bash -c '...'` invocation) and
    verify it scans the file Claude just wrote and blocks on PII.
    """
    import json as _json
    import subprocess as sp
    import shlex

    fake_home = tmp_path / "home"
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env.pop("GIT_CONFIG_GLOBAL", None)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    rc = subprocess.run(
        [sys.executable, "-m", "pii_linter", "install-hooks", "claude-code"],
        env=env, capture_output=True, text=True, check=True,
    )
    settings = fake_home / ".claude" / "settings.json"
    assert settings.exists()
    body = _json.loads(settings.read_text())
    cmd_str = body["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    # Sanity: the command reads $CLAUDE_TOOL_FILE_PATH and dispatches
    # on extension. Run it directly.
    target = tmp_path / "leak.csv"
    target.write_text("name,phone\neve,0912345678\n")
    proc = sp.run(
        ["bash", "-c", cmd_str], capture_output=True, text=True,
        env={**env, "CLAUDE_TOOL_FILE_PATH": str(target)},
    )
    # PostToolUse contract: HIGH+ -> exit 2 (the command appends
    # `|| exit 2` so the wrapper's exit code propagates).
    assert proc.returncode == 2, (
        f"expected exit 2, got {proc.returncode}\nstdout: {proc.stdout!r}\n"
        f"stderr: {proc.stderr!r}"
    )


def test_codex_notify_blocks_pii_in_staged_diff(tmp_path: Path, pii_lint_on_path) -> None:
    """Codex notify: a real git repo with PII staged -> exit 2."""
    import subprocess as sp

    fake_home = tmp_path / "home"
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env.pop("GIT_CONFIG_GLOBAL", None)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    rc = subprocess.run(
        [sys.executable, "-m", "pii_linter", "install-hooks", "codex"],
        env=env, capture_output=True, text=True,
    )
    assert rc.returncode == 0, rc.stderr
    notify = fake_home / ".codex" / "hooks" / "codex-notify.sh"
    assert notify.exists()
    assert notify.stat().st_mode & stat.S_IXUSR

    repo = _write_repo_with_files(
        tmp_path,
        {"leak.csv": "name,phone\neve,0912345678\n"},
    )
    sp.run(["git", "add", "leak.csv"], cwd=repo, check=True, capture_output=True)
    proc = sp.run(["bash", str(notify)], cwd=repo, capture_output=True, text=True, env=env)
    # Contract: HIGH+ in staged diff -> exit 2 so Codex re-prompts.
    assert proc.returncode == 2, (
        f"expected exit 2, got {proc.returncode}\nstdout: {proc.stdout!r}\n"
        f"stderr: {proc.stderr!r}"
    )
    # The notify script prints the blocking reason to stdout (Codex
    # captures notify stdout and feeds it back into the conversation).
    combined = (proc.stdout + proc.stderr).lower()
    assert "staged diff" in combined
    assert "pii" in combined or "high" in combined or "critical" in combined


def test_codex_notify_passes_clean_staged_diff(tmp_path: Path, pii_lint_on_path) -> None:
    """Codex notify: clean staged diff -> exit 0."""
    import subprocess as sp

    fake_home = tmp_path / "home"
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env.pop("GIT_CONFIG_GLOBAL", None)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    subprocess.run(
        [sys.executable, "-m", "pii_linter", "install-hooks", "codex"],
        env=env, capture_output=True, text=True, check=True,
    )
    notify = fake_home / ".codex" / "hooks" / "codex-notify.sh"
    repo = _write_repo_with_files(
        tmp_path,
        {"clean.csv": "name,note\nalpha,ok\n"},
    )
    sp.run(["git", "add", "clean.csv"], cwd=repo, check=True, capture_output=True)
    proc = sp.run(["bash", str(notify)], cwd=repo, capture_output=True, text=True, env=env)
    assert proc.returncode == 0, (
        f"expected exit 0, got {proc.returncode}\nstderr: {proc.stderr}"
    )


def test_codex_notify_is_noop_outside_git_repo(tmp_path: Path) -> None:
    """Codex notify outside a git repo -> exit 0 (no scan, no error)."""
    fake_home = tmp_path / "home"
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env.pop("GIT_CONFIG_GLOBAL", None)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    subprocess.run(
        [sys.executable, "-m", "pii_linter", "install-hooks", "codex"],
        env=env, capture_output=True, text=True, check=True,
    )
    notify = fake_home / ".codex" / "hooks" / "codex-notify.sh"
    # tmp_path is not a git repo.
    proc = subprocess.run(
        ["bash", str(notify)], cwd=tmp_path,
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr


def test_codex_notify_uses_real_pii_lint_binary(tmp_path: Path, pii_lint_on_path) -> None:
    """The notify script invokes pii-lint via PATH (not -m), so verify
    the binary is on PATH and is the one install-hooks just installed.

    This protects against a future refactor that switches to
    `python -m pii_linter` and silently breaks users on systems where
    the console script was not symlinked (e.g. pipx --global).
    """
    import subprocess as sp

    fake_home = tmp_path / "home"
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env.pop("GIT_CONFIG_GLOBAL", None)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    # Provide a fake bin dir on PATH so the script's `pii-lint` lookup
    # is forced to use whatever `pii-lint` the test env shipped — that
    # is the editable-install console script this repo's tests depend on.
    sandbox_bin = tmp_path / "sandbox_bin"
    sandbox_bin.mkdir()
    real_pii_lint = shutil_which("pii-lint")
    assert real_pii_lint, "test env missing pii-lint on PATH"
    # Symlink the console script on PATH so the agent hooks' bare
    # `pii-lint` lookup resolves to it, but wrap it in a tiny shim
    # that injects the user-site-packages path the editable install
    # registered. Without this, the shebang in the console script
    # points at /usr/bin/python3, which has no `pii_linter` importable
    # and the hooks fail with `ModuleNotFoundError`.
    wrapper = sandbox_bin / "pii-lint"
    wrapper.write_text(
        "#!/bin/sh\n"
        f'exec /usr/bin/env PYTHONPATH="{Path(__file__).resolve().parent.parent}" '
        f'"{real_pii_lint}" "$@"\n'
    )
    wrapper.chmod(0o755)
    env["PATH"] = str(sandbox_bin) + os.pathsep + env.get("PATH", "")
    subprocess.run(
        [sys.executable, "-m", "pii_linter", "install-hooks", "codex"],
        env=env, capture_output=True, text=True, check=True,
    )
    notify = fake_home / ".codex" / "hooks" / "codex-notify.sh"
    # Confirm the script literally calls `pii-lint` (not `python -m`).
    body = notify.read_text()
    assert "pii-lint scan --staged" in body
    # And run it end-to-end against a real git repo.
    repo = _write_repo_with_files(
        tmp_path, {"clean.csv": "name,note\nalpha,ok\n"},
    )
    sp.run(["git", "add", "clean.csv"], cwd=repo, check=True, capture_output=True)
    proc = sp.run(["bash", str(notify)], cwd=repo, capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr


def test_install_hooks_preserves_existing_user_settings(tmp_path: Path) -> None:
    """Merging must not clobber unrelated keys in an existing settings.json.

    Reproduce a realistic case: the user already has a UserPromptSubmit
    hook, then they run `pii-lint install-hooks claude-code`. The new
    PreToolUse/PostToolUse/Stop hooks must be added; the pre-existing
    UserPromptSubmit must survive.
    """
    import json as _json
    fake_home = tmp_path / "home"
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env.pop("GIT_CONFIG_GLOBAL", None)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    settings = fake_home / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    existing = {
        "permissions": {"allow": ["Bash(npm:*)"]},
        "hooks": {
            "UserPromptSubmit": [
                {"matcher": "", "hooks": [{"type": "command", "command": "echo hi"}]}
            ]
        },
    }
    settings.write_text(_json.dumps(existing))
    rc = subprocess.run(
        [sys.executable, "-m", "pii_linter", "install-hooks", "claude-code"],
        env=env, capture_output=True, text=True,
    )
    assert rc.returncode == 0, rc.stderr
    merged = _json.loads(settings.read_text())
    # Pre-existing keys preserved.
    assert merged["permissions"] == {"allow": ["Bash(npm:*)"]}
    assert "UserPromptSubmit" in merged["hooks"]
    # New keys added.
    assert "PreToolUse" in merged["hooks"]
    assert "PostToolUse" in merged["hooks"]
    assert "Stop" in merged["hooks"]


def test_precommit_hook_prints_markdown_report_in_block_message(
    tmp_path: Path, pii_lint_on_path, monkeypatch
) -> None:
    """End-to-end: a planted PHONE in a staged CSV triggers the
    pre-commit hook, the hook un-stages the file, and the same
    Markdown report `pii-lint scan --staged` would print is rendered
    inline in stderr. The user gets file:line + masked evidence in
    the block message, with no need to re-invoke the CLI.

    This is the regression guard for the "show report without
    re-running pii-lint" UX requirement.
    """
    # Set up a real git repo with pii-lint pre-commit installed.
    # `install_git.install()` reads `Path.cwd()`, so we have to
    # chdir into the repo before calling it.
    repo = _write_repo_with_files(
        tmp_path,
        {"clean.csv": "name,note\nalpha,ok\n"},
    )
    # _write_repo_with_files disables the in-repo hook by pinning
    # `core.hooksPath=/dev/null` for the duration of agent-hook
    # tests. Undo that so the pre-commit we install is the one
    # under test.
    subprocess.run(
        ["git", "config", "--unset", "core.hooksPath"],
        cwd=repo, check=True, capture_output=True,
    )
    monkeypatch.chdir(repo)
    assert install_git.install() == 0
    # Plant a phone number in a new staged file and try to commit.
    (repo / "leak.csv").write_text("name,phone\neve,0912345678\n", encoding="utf-8")
    subprocess.run(["git", "add", "leak.csv"], cwd=repo, check=True)
    proc = subprocess.run(
        ["git", "commit", "-m", "plant"],
        cwd=repo, capture_output=True, text=True,
    )
    # Commit is blocked, exit non-zero, file un-staged.
    assert proc.returncode != 0, (
        f"expected commit to be blocked, got rc={proc.returncode}\n"
        f"stdout: {proc.stdout!r}\nstderr: {proc.stderr!r}"
    )
    staged_after = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert staged_after == "", f"expected un-staged, got: {staged_after!r}"
    # The Markdown report rendered by `pii-lint scan --staged` shows
    # the same header; assert it appears in the hook's stderr so the
    # user sees it inline.
    combined = proc.stdout + proc.stderr
    assert "# PII scan report" in combined, (
        f"expected in-line markdown report, got:\n{combined!r}"
    )
    # And the per-file heading for the planted file.
    assert "leak.csv" in combined
    # Phone entity label, plus a masked phone fragment (only the
    # middle 4 digits are dropped — we just check the prefix is masked).
    assert "PHONE" in combined


def shutil_which(name: str) -> str | None:
    """Local helper: avoid importing shutil just for `which` in one test."""
    from shutil import which

    return which(name)