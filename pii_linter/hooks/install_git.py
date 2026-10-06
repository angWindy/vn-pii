"""Install the PII-blocking ``pre-commit`` git hook for every repo on the box.

Why a global hook instead of per-repo config: the goal is one install command
and zero per-repo setup. Git reads hooks from ``core.hooksPath`` when that is
set and from ``.git/hooks/`` otherwise, so a global hooks dir is the only
placement that covers every existing repo *and* every repo created later.

Two safety properties this module is built around, both verified against
git 2.43:

1. ``core.hooksPath`` **replaces** the hook lookup directory. Pointing it at
   our dir does not add to ``.git/hooks/``; it orphans every hook already
   there. We therefore write passthrough shims for the common commit-time
   hooks so a repo's own ``commit-msg`` (and friends) keep running.
2. A hook that cannot start is a hook that silently lets PII through. The
   generated ``pre-commit`` fails *closed* with an actionable message rather
   than skipping the scan.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from importlib import resources
from pathlib import Path

_TEMPLATES = resources.files("pii_linter.hooks.templates")


def _read_template(name: str) -> str:
    """Read a template file shipped inside the wheel via importlib.resources.

    Used for the resolver bash script, which lives in the templates dir
    alongside the agent hook scripts (``codex-notify.sh`` etc.).
    """
    return (_TEMPLATES / name).read_text(encoding="utf-8")

# Marker used to recognise files this module owns. Uninstall and the
# collision check both key off it, so it must appear in every file we write.
MARKER = "pii-lint"

# State file inside the hooks dir. Records whether *we* set core.hooksPath,
# so uninstall can restore the user's git config instead of leaving it
# pointed at a dir we are about to gut.
STATE_FILE = ".pii-lint-state.json"

# Hooks we do not implement, but whose repo-local versions we must not
# orphan once core.hooksPath redirects git's lookup.
PASSTHROUGH_HOOKS = (
    "commit-msg",
    "prepare-commit-msg",
    "post-commit",
    "pre-push",
    "post-checkout",
    "post-merge",
    "pre-rebase",
)


# ---------------------------------------------------------------------------
# git plumbing
# ---------------------------------------------------------------------------

def _git(*args: str) -> subprocess.CompletedProcess[str]:
    exe = shutil.which("git")
    if exe is None:
        raise FileNotFoundError("git is not on PATH")
    return subprocess.run(
        [exe, *args], capture_output=True, text=True, check=False
    )


def current_hooks_path() -> str | None:
    """Return the configured ``core.hooksPath``, or None if unset."""
    try:
        proc = _git("config", "--global", "--get", "core.hooksPath")
    except (FileNotFoundError, OSError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _home() -> Path:
    return Path(os.environ.get("HOME") or Path.home())


def _resolve_hooks_dir() -> tuple[Path, bool]:
    """Pick the dir to install into, and whether we must set config for it.

    If the user already points ``core.hooksPath`` somewhere we adopt that dir
    rather than fighting them for it. Otherwise we use ``~/.githooks`` and
    will set the config ourselves (second element True).
    """
    configured = current_hooks_path()
    if configured:
        return Path(configured).expanduser(), False
    return _home() / ".githooks", True


def _interpreter() -> str:
    """Absolute path to the resolver script that locates a working pii-lint.

    Why a resolver instead of a hard-pinned Python:
      The hook must run from any shell context — terminal, VSCode Source
      Control panel, Cursor Git panel, Aider — and each can have a
      different ``PATH`` and active conda/venv. Hard-pinning to whatever
      ``sys.executable`` happened to be at ``init`` time works *until*
      the user reinstalls pii-lint into a different env, at which point
      the hook is stuck pointing at an interpreter whose import of
      pii_linter is now stale or missing.

    The resolver is a small bash script that walks several candidate
    interpreters and picks the first one that has ``pii_linter`` on its
    import path. The hook calls the resolver, the resolver re-execs the
    actual scan with the chosen Python.

    The resolver lives next to ``pre-commit`` in the global hooks dir,
    so we ship it as a sibling file in the same install() call.
    """
    return "bash __PII_RESOLVER_PATH__"


# ---------------------------------------------------------------------------
# file bodies
# ---------------------------------------------------------------------------

def precommit_body(resolver_path: str = "__PII_RESOLVER_PATH__") -> str:
    """The PII scan hook. Fails closed if the resolver has vanished.

    The hook does not pin a Python interpreter: instead it invokes the
    ``pii-lint-resolver.sh`` script (sibling file written by
    :func:`install`), which locates the right Python at runtime. This
    lets the same hook work after a user switches conda envs or
    reinstalls pii-lint into a different one.
    """
    return f"""#!/bin/sh
# {MARKER} pre-commit hook. Generated by `{MARKER} init`; re-run to update.
#
# Scans only the lines this commit adds (.csv/.jsonl/.md) and blocks on
# HIGH/CRITICAL findings. Preexisting PII on untouched lines is ignored.
#
# The hook calls a resolver script, NOT a hard-pinned Python, so it
# follows the user across re-installs into different conda envs. If
# the resolver cannot find a Python with pii_linter installed it
# fails closed with an actionable message — never silently passes.
RESOLVER="{resolver_path}"

if [ ! -x "$RESOLVER" ]; then
    echo "{MARKER}: resolver missing at $RESOLVER - the PII scan did NOT run." >&2
    echo "{MARKER}: reinstall with 'pii-lint init', or bypass once with 'git commit --no-verify'." >&2
    exit 1
fi

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || ROOT=.
if [ -f "$ROOT/suppressions.toml" ]; then
    exec "$RESOLVER" -m pii_linter scan --staged --suppressions "$ROOT/suppressions.toml"
fi
exec "$RESOLVER" -m pii_linter scan --staged
"""


def passthrough_body(hook_name: str) -> str:
    """A shim that forwards to the repo's own hook of the same name.

    Setting ``core.hooksPath`` makes git stop reading ``.git/hooks/``. Without
    this shim a repo that customised e.g. ``commit-msg`` silently loses it.
    """
    return f"""#!/bin/sh
# {MARKER} passthrough shim. Generated by `{MARKER} init`; re-run to update.
#
# core.hooksPath replaces git's hook lookup dir, so this forwards to the
# repo's own hook of the same name to stop it being orphaned.
DIR=$(git rev-parse --absolute-git-dir 2>/dev/null) || DIR=""
if [ -n "$DIR" ] && [ -x "$DIR/hooks/{hook_name}" ]; then
    "$DIR/hooks/{hook_name}" "$@"
    exit $?
fi
exit 0
"""


# ---------------------------------------------------------------------------
# install / uninstall
# ---------------------------------------------------------------------------

def _is_ours(path: Path) -> bool:
    try:
        return MARKER in path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def _write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(
        stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
    )


def _read_state(hooks_dir: Path) -> dict:
    path = hooks_dir / STATE_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def install(dry_run: bool = False) -> int:
    """Install the global PII hook. Returns 0 on success, 1 on refusal."""
    try:
        hooks_dir, must_set_config = _resolve_hooks_dir()
    except OSError as e:
        print(f"FAILED to resolve hooks dir: {e}", file=sys.stderr)
        return 1

    # The resolver is a sibling bash script that the hook calls instead
    # of a hard-pinned Python. It lives in the same dir as pre-commit so
    # the hook can find it via an absolute path that we patch in.
    resolver_path = hooks_dir / "pii-lint-resolver.sh"
    resolver_body = _read_template("pii-lint-resolver.sh")

    # Refuse rather than clobber. The realistic collision is husky, which
    # owns core.hooksPath and its own pre-commit: overwriting that breaks
    # every commit in the user's repos. Per-repo pre-commit framework is
    # the documented way to combine with a hook manager.
    #
    # Check *every* file we are about to write, not just pre-commit. A
    # foreign `commit-msg` sitting in the hooks dir would otherwise be
    # silently replaced by our shim and then deleted by `uninstall`.
    files = [(hooks_dir / "pre-commit", precommit_body(str(resolver_path)))]
    for name in PASSTHROUGH_HOOKS:
        files.append((hooks_dir / name, passthrough_body(name)))
    files.append((resolver_path, resolver_body))

    collisions = [p for p, _ in files if p.exists() and not _is_ours(p)]
    if collisions:
        listed = "\n".join(f"  {p}" for p in collisions)
        print(
            f"REFUSED: these files exist and were not written by {MARKER}:\n"
            f"{listed}\n"
            f"That directory owns your git hooks (husky does this). Installing "
            f"would replace them and `uninstall` would then delete them.\n"
            f"Per repo, merge examples/pre-commit-config.yaml into your "
            f".pre-commit-config.yaml and run `pre-commit install` instead, "
            f"or move the other hook manager's directory first.",
            file=sys.stderr,
        )
        return 1

    if dry_run:
        print(f"[dry-run] hooks dir: {hooks_dir}")
        for path, _ in files:
            state = "overwrite (ours)" if path.exists() else "create"
            print(f"[dry-run] would {state}: {path}")
        action = "set" if must_set_config else "already set"
        print(
            f"[dry-run] core.hooksPath: {action} -> {hooks_dir} "
            f"(current: {current_hooks_path() or 'unset'})"
        )
        return 0

    try:
        for path, body in files:
            _write_executable(path, body)
    except OSError as e:
        print(f"FAILED to write hook: {e}", file=sys.stderr)
        return 1

    # The pre-commit hook is files[0]; the messages below name it by path.
    target = files[0][0]

    if must_set_config:
        try:
            proc = _git("config", "--global", "core.hooksPath", str(hooks_dir))
        except (FileNotFoundError, OSError) as e:
            proc = None
            err = str(e)
        else:
            err = proc.stderr.strip() if proc.returncode != 0 else ""
        if err:
            # The hook file is written either way; tell the user how to finish.
            print(
                f"FAILED to set core.hooksPath: {err}\n"
                f"The hook is written to {target} but git will not run it "
                f"until you run:\n"
                f"  git config --global core.hooksPath {hooks_dir}",
                file=sys.stderr,
            )
            return 1
    else:
        print(f"core.hooksPath already points at {hooks_dir}; left as is.")

    try:
        (hooks_dir / STATE_FILE).write_text(
            json.dumps({"marker": MARKER, "set_hooks_path": must_set_config}, indent=2)
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass  # state file is an uninstall convenience, not load-bearing

    print(f"PII hook installed: {target}")
    print(f"core.hooksPath = {hooks_dir} (applies to every git repo on this machine)")
    print("Every `git commit` now scans staged .csv/.jsonl/.md lines.")
    print(f"Remove with: {MARKER} uninstall")
    return 0


def uninstall(dry_run: bool = False) -> int:
    """Remove the global hook and restore core.hooksPath if we set it."""
    try:
        hooks_dir, _ = _resolve_hooks_dir()
    except OSError as e:
        print(f"FAILED to resolve hooks dir: {e}", file=sys.stderr)
        return 1

    state = _read_state(hooks_dir)
    state_path = hooks_dir / STATE_FILE
    candidates = [hooks_dir / "pre-commit"]
    candidates += [hooks_dir / name for name in PASSTHROUGH_HOOKS]
    candidates.append(hooks_dir / "pii-lint-resolver.sh")
    # Never delete a hook we did not write: a foreign file in this dir is
    # someone else's (husky, or a hand-rolled hook), not ours to remove.
    victims = [p for p in candidates if p.exists() and _is_ours(p)]
    if state_path.exists():
        victims.append(state_path)

    if not victims:
        print(f"Nothing to remove in {hooks_dir}.")
        return 0

    if dry_run:
        for p in victims:
            print(f"[dry-run] would remove: {p}")
        return 0

    for p in victims:
        try:
            p.unlink()
        except OSError as e:
            print(f"FAILED to remove {p}: {e}", file=sys.stderr)
            return 1

    if state.get("set_hooks_path"):
        try:
            proc = _git("config", "--global", "--unset", "core.hooksPath")
            if proc.returncode == 0:
                print("core.hooksPath unset; git is back to .git/hooks/.")
            else:
                print(
                    "core.hooksPath left in place; unset it with:\n"
                    "  git config --global --unset core.hooksPath",
                    file=sys.stderr,
                )
        except (FileNotFoundError, OSError) as e:
            print(f"FAILED to unset core.hooksPath: {e}", file=sys.stderr)

    print(f"Removed {len(victims)} file(s) from {hooks_dir}.")
    return 0
