"""Install the PII-blocking ``pre-commit`` and ``pre-push`` git hooks
**in the current repo only**.

The model is opt-in per repo: ``cd`` into a repo and run ``pii-lint init``.
Every repo where the user runs ``init`` gets the hooks; every repo they do
not is left alone. This is a deliberate break from the previous global
``core.hooksPath`` model, which forced the PII scan on every repository on
the machine — including personal/scratch repos that have nothing to do with
PII.

Per-repo install writes into the repo's own ``.git/hooks/`` and never
touches ``core.hooksPath`` or ``$HOME``. When the repo already has a
``pre-commit`` (or any other hook we are about to write) that was not
authored by us, we move it aside to ``<name>.real`` and write our hook on
top, which then chains to ``.real`` only after a clean PII scan — the
same pattern the previous implementation used for ``pre-push``.

Two safety properties this module is built around, both verified against
git 2.43:
1. A hook that cannot start is a hook that silently lets PII through. The
   generated ``pre-commit`` and ``pre-push`` fail *closed* with an
   actionable message rather than skipping the scan.
2. A foreign hook in ``.git/hooks/`` is never silently overwritten:
   collision check refuses to clobber, and the chain-to-``.real`` step
   only fires when the existing file is provably not ours.
"""

from __future__ import annotations

import os
import shutil
import stat
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

# Hooks we do not implement, but whose repo-local versions we must not
# orphan once we write our own on top.
PASSTHROUGH_HOOKS = (
    "commit-msg",
    "prepare-commit-msg",
    "post-commit",
    "post-checkout",
    "post-merge",
    "pre-rebase",
)
# Hooks we *implement* (not pass through). Listed separately so install()
# can pick the right generator for each.
FULL_HOOKS = (
    "pre-commit",
    "pre-push",
)


# ---------------------------------------------------------------------------
# git plumbing
# ---------------------------------------------------------------------------

def _git(*args: str):
    """Wrapper around the ``git`` binary on PATH. Returns CompletedProcess."""
    import subprocess

    exe = shutil.which("git")
    if exe is None:
        raise FileNotFoundError("git is not on PATH")
    return subprocess.run(
        [exe, *args], capture_output=True, text=True, check=False
    )


def _repo_git_dir(cwd: Path) -> Path | None:
    """Return the absolute path of the git dir for the repo at ``cwd``,
    or ``None`` if ``cwd`` is not inside a git working tree.

    Handles both the regular case (``<cwd>/.git`` is a directory) and
    the worktree case (``<cwd>/.git`` is a file containing
    ``gitdir: <path>``). In the worktree case we follow the indirection
    to the worktree's own private git dir, which is where git itself
    looks for hooks when run from that worktree.
    """
    dot_git = cwd / ".git"
    if dot_git.is_dir():
        return dot_git.resolve()
    if dot_git.is_file():
        # Worktree (or linked worktree): the .git file points at
        # `<main>/.git/worktrees/<name>/`. We resolve to that path so
        # hooks written there match git's own lookup.
        try:
            content = dot_git.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not content.startswith("gitdir:"):
            return None
        target = Path(content[len("gitdir:") :].strip())
        if not target.is_absolute():
            target = (dot_git.parent / target).resolve()
        if not target.exists():
            return None
        return target
    return None


def _repo_hooks_dir(cwd: Path) -> Path | None:
    """Return the absolute hooks dir for the repo at ``cwd``, or ``None``.

    Convenience wrapper around :func:`_repo_git_dir` so callers do not
    have to append ``/hooks`` themselves. The returned path may or may
    not exist yet — callers must ``mkdir`` before writing into it.
    """
    git_dir = _repo_git_dir(cwd)
    if git_dir is None:
        return None
    return git_dir / "hooks"


def _home() -> Path:
    return Path(os.environ.get("HOME") or Path.home())


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

    On a HIGH+ finding the hook now also **unstages the offending file**
    via ``git reset HEAD -- <file>`` before exiting non-zero. Rationale:
    a user who runs ``git add .`` and then ``git commit`` on a
    workspace full of mixed data wants to know *which file* tripped the
    scan so they can redact and re-add it, not have it sit silently in
    the index ready to leak on the next attempt. Unstaging is
    recoverable (the file is still on disk in the working tree) and
    idempotent (``git reset`` on an unstaged file is a no-op).
    """
    return f"""#!/bin/sh
# {MARKER} pre-commit hook. Generated by `{MARKER} init`; re-run to update.
#
# Scans only the lines this commit adds (.csv/.jsonl/.md) and blocks on
# HIGH/CRITICAL findings. Preexisting PII on untouched lines is ignored.
# On a HIGH+ finding the offending file(s) are unstaged from the index
# so the user can see which file tripped the scan and re-add after
# redaction, instead of finding the same leak in the index next commit.
#
# The hook calls a resolver script, NOT a hard-pinned Python, so it
# follows the user across re-installs into different conda envs. If the
# resolver cannot find a Python with pii_linter installed it fails
# closed with an actionable message - never silently passes.
RESOLVER="{resolver_path}"

if [ ! -x "$RESOLVER" ]; then
    echo "{MARKER}: resolver missing at $RESOLVER - the PII scan did NOT run." >&2
    echo "{MARKER}: reinstall with '{MARKER} init', or bypass once with 'git commit --no-verify'." >&2
    exit 1
fi

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || ROOT=.
SUPS=""
if [ -f "$ROOT/suppressions.toml" ]; then
    SUPS="--suppressions $ROOT/suppressions.toml"
fi

# Run the scan and capture the JSON report. Exit code is preserved so
# the post-parse unstage step still aborts the commit on HIGH+.
JSON=$("$RESOLVER" -m pii_linter scan --staged --format json $SUPS 2>/dev/null)
SCAN_RC=$?

# Parse the JSON and list every file that has at least one HIGH/CRITICAL
# finding (severity >= 3). Stdlib json only, no jq dependency.
LEAKED_FILES=$(printf '%s' "$JSON" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
HIGH = 3
seen = []
for f in data.get("findings", []):
    if (f.get("severity") or 0) >= HIGH and f.get("file"):
        if f["file"] not in seen:
            seen.append(f["file"])
for p in seen:
    print(p)
')

if [ -n "$LEAKED_FILES" ]; then
    echo "{MARKER}: HIGH/CRITICAL PII found. Unstaging from the index:" >&2
    for f in $LEAKED_FILES; do
        echo "  $f" >&2
        # `git reset HEAD -- <file>` works for both newly-added and
        # modified files: it moves the entry out of the index and back
        # to the working tree (or untracked for a new file). The file
        # itself is not deleted.
        git reset HEAD -- "$f" 2>/dev/null || true
    done
    echo >&2
    echo "{MARKER}: re-run \\`git status\\` to see the remaining staged files, redact, and re-add." >&2
fi

exit $SCAN_RC
"""


def precommit_body_with_chain(
    resolver_path: str = "__PII_RESOLVER_PATH__",
) -> str:
    """Like :func:`precommit_body` but chains to a previously-existing
    ``pre-commit.real`` after a clean scan.

    Used when the repo already had a ``pre-commit`` (from husky,
    simple-git-hooks, or a hand-rolled hook) at the time ``init`` ran.
    We move the original aside to ``pre-commit.real`` and write our own
    ``pre-commit`` on top, which runs the PII scan first and only
    forwards to ``.real`` when the scan came back clean.
    """
    base = precommit_body(resolver_path)
    chain = """

# Chain to the repo's original pre-commit hook (moved aside by
# `pii-lint init`) only when our scan was clean. If SCAN_RC != 0
# we have already unstaged the offending file(s) and the commit
# must abort, so the user hook does not run on a half-staged tree.
if [ "$SCAN_RC" = "0" ] && [ -x "$ROOT/.git/hooks/pre-commit.real" ]; then
    "$ROOT/.git/hooks/pre-commit.real" "$@"
    exit $?
fi
exit $SCAN_RC
"""
    # The base body ends with `exit $SCAN_RC`; replace it with the chain.
    return base.rstrip().removesuffix("exit $SCAN_RC") + chain.lstrip("\n")


def prepush_body(resolver_path: str = "__PII_RESOLVER_PATH__") -> str:
    """The pre-push hook. Second wall after pre-commit.

    ``pre-commit`` is bypassed by editors that override ``core.hooksPath``
    (Cursor's bundled git extension does this for every subprocess it
    spawns, including the integrated terminal, the Source Control button,
    and the AI agent's shell). ``pre-push`` runs in the user's *real*
    shell when ``git push`` is invoked, so the per-repo hook is honored
    and PII that slipped through the bypassed pre-commit is still caught
    before it leaves the machine.

    git passes refs on stdin, one line per ref, in the form
    ``<local_ref> <local_sha> <remote_ref> <remote_sha>``. ``remote_sha``
    is all zeros for a brand-new branch; in that case we scan every line
    reachable from ``local_sha`` so the first push of a topic branch is
    still covered.

    Fail-closed semantics: if the resolver is missing, exit 2 so git
    aborts the push. A HIGH+ PII finding exits 1 from the scan, which
    also aborts. No silent passes.
    """
    return f"""#!/bin/sh
# {MARKER} pre-push hook. Generated by `{MARKER} init`; re-run to update.
#
# Scans every line added by the commits being pushed (.csv/.jsonl/.md)
# and blocks the push on HIGH/CRITICAL findings. Preexisting PII on
# untouched lines is ignored.
#
# The hook reads refs from stdin in the format git provides:
#   <local_ref> SP <local_sha> SP <remote_ref> SP <remote_sha> LF
# A brand-new branch has all-zeros ``remote_sha``; we substitute git's
# empty-tree SHA so the diff is well-defined.
#
# The hook calls a resolver script, NOT a hard-pinned Python, so it
# follows the user across re-installs into different conda envs. If the
# resolver cannot find a Python with pii_linter installed it fails
# closed with an actionable message - never silently passes.
RESOLVER="{resolver_path}"

if [ ! -x "$RESOLVER" ]; then
    echo "{MARKER}: resolver missing at $RESOLVER - the PII scan did NOT run." >&2
    echo "{MARKER}: reinstall with '{MARKER} init', or bypass once with 'git push --no-verify'." >&2
    exit 2
fi

EMPTY_TREE=4b825dc642cb6eb9a060e54bf8d69288fbee4904
FAILED=0
while read -r local_ref local_sha remote_ref remote_sha; do
    # Skip deletion pushes (empty local_sha) and "matching" no-op lines.
    case "$local_sha" in
        "") continue ;;
    esac
    if [ -z "$remote_sha" ] || [ "$remote_sha" = "0000000000000000000000000000000000000000" ]; then
        base="$EMPTY_TREE"
    else
        base="$remote_sha"
    fi
    ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || ROOT=.
    SUPS=""
    if [ -f "$ROOT/suppressions.toml" ]; then
        SUPS="--suppressions $ROOT/suppressions.toml"
    fi
    OUT=$("$RESOLVER" -m pii_linter scan --pushed-base "$base" --pushed-head "$local_sha" $SUPS 2>&1)
    RC=$?
    if [ $RC -ne 0 ]; then
        echo "$OUT" >&2
        FAILED=1
    fi
done

# Preserve the repo's own pre-push hook if it exists.
DIR=$(git rev-parse --absolute-git-dir 2>/dev/null) || DIR=""
if [ $FAILED -eq 0 ] && [ -n "$DIR" ] && [ -x "$DIR/hooks/pre-push.real" ]; then
    "$DIR/hooks/pre-push.real" "$@"
    exit $?
fi
exit $FAILED
"""


def passthrough_body(hook_name: str) -> str:
    """A shim that forwards to the repo's own ``<hook_name>.real`` if
    one was moved aside by :func:`_move_aside_if_foreign`, and is a
    no-op otherwise.

    Per-repo install writes our hooks into ``.git/hooks/`` alongside
    the user's. We never overwrite the user's hook — we move it to
    ``<name>.real`` first and write a shim on top that forwards to
    ``.real``. This is the same pattern the FULL_HOOKS use (see
    :func:`precommit_body_with_chain`); we just do not scan first
    because these hooks are not the PII gate.

    Forwarding to ``.real`` (not the bare name) is critical: if we
    forwarded to the bare name, the shim would re-invoke itself and
    loop forever. The shim and the chained user hook must live at
    different names.
    """
    return f"""#!/bin/sh
# {MARKER} passthrough shim. Generated by `{MARKER} init`; re-run to update.
#
# Forwards to the repo's own <hook_name> hook (moved aside to
# <hook_name>.real by `pii-lint init`). If no such hook exists,
# this is a no-op. We forward to `.real` (not the bare name) so the
# shim does not re-invoke itself in an infinite loop.
DIR=$(git rev-parse --absolute-git-dir 2>/dev/null) || DIR=""
if [ -n "$DIR" ] && [ -x "$DIR/hooks/{hook_name}.real" ]; then
    "$DIR/hooks/{hook_name}.real" "$@"
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


def _move_aside_if_foreign(hooks_dir: Path, hook_name: str) -> bool:
    """If ``<hooks_dir>/<hook_name>`` exists and was not written by us,
    move it to ``<hook_name>.real`` so our hook can take its place.

    Returns ``True`` if a move happened (the caller should write a chain
    hook that invokes ``.real`` after a clean scan), ``False`` if no
    move was needed (no existing hook, or the existing one is already
    ours and will be overwritten).
    """
    target = hooks_dir / hook_name
    real = hooks_dir / f"{hook_name}.real"
    if not target.exists():
        return False
    if _is_ours(target):
        # Our own hook: safe to overwrite in place.
        return False
    if real.exists():
        # A previous install already moved a foreign hook aside. Refuse
        # to clobber; the user must sort it out manually.
        raise OSError(
            f"{real} already exists. `pii-lint init` will not overwrite a "
            f"previously-chained foreign hook. Remove it manually, or "
            f"merge its logic into your workflow before re-running init."
        )
    target.rename(real)
    return True


def _restore_chained_hook(hooks_dir: Path, hook_name: str) -> bool:
    """If ``<hooks_dir>/<hook_name>.real`` exists, rename it back to
    ``<hook_name>`` to undo a chain. Used by ``uninstall`` to put the
    repo back the way it was before ``init`` ran.
    """
    real = hooks_dir / f"{hook_name}.real"
    target = hooks_dir / hook_name
    if not real.exists():
        return False
    # If the user has independently installed a hook in the meantime,
    # we should not overwrite it. That is an edge case best handled
    # by the user; we just refuse to clobber.
    if target.exists() and not _is_ours(target):
        return False
    if target.exists():
        target.unlink()
    real.rename(target)
    return True


def install(dry_run: bool = False) -> int:
    """Install the per-repo PII hooks. Returns 0 on success, 1 on refusal.

    Writes ``pre-commit`` and ``pre-push`` (with a ``.real`` chain if the
    repo already had them), plus passthrough shims for the other
    commit-time hooks, plus a ``pii-lint-resolver.sh`` sibling script.
    All files land in the current repo's ``.git/hooks/`` and nowhere
    else. Does **not** touch ``core.hooksPath`` or anything under
    ``$HOME``.
    """
    try:
        cwd = Path.cwd()
        hooks_dir = _repo_hooks_dir(cwd)
    except OSError as e:
        print(f"FAILED to resolve hooks dir: {e}", file=sys.stderr)
        return 1
    if hooks_dir is None:
        print(
            "Not in a git repository. `cd` into the repo you want to "
            "protect and run `pii-lint init` again.",
            file=sys.stderr,
        )
        return 1

    # The resolver is a sibling bash script that the hook calls instead
    # of a hard-pinned Python. It lives in the same dir as pre-commit so
    # the hook can find it via an absolute path that we patch in.
    resolver_path = hooks_dir / "pii-lint-resolver.sh"
    resolver_body = _read_template("pii-lint-resolver.sh")

    # Decide which hooks need a `.real` chain. We do this BEFORE the
    # collision check below so the user gets a clear message about
    # foreign hooks even when the chain setup is the issue. Every hook
    # we are about to write goes through this step: pre-commit and
    # pre-push chain via their own dedicated bodies (which run the PII
    # scan and only then call `.real`), while the passthrough hooks
    # chain via the shim itself (which simply forwards to `.real`).
    # Without this step, a shim at `commit-msg` would forward to
    # `commit-msg` and re-invoke itself in an infinite loop.
    chains: dict[str, bool] = {}
    try:
        for name in (*FULL_HOOKS, *PASSTHROUGH_HOOKS):
            chains[name] = _move_aside_if_foreign(hooks_dir, name)
    except OSError as e:
        print(str(e), file=sys.stderr)
        return 1

    files: list[tuple[Path, str]] = [
        (
            hooks_dir / "pre-commit",
            (
                precommit_body_with_chain(str(resolver_path))
                if chains["pre-commit"]
                else precommit_body(str(resolver_path))
            ),
        ),
        (
            hooks_dir / "pre-push",
            (
                prepush_body(str(resolver_path))  # body already chains to .real
            ),
        ),
    ]
    for name in PASSTHROUGH_HOOKS:
        files.append((hooks_dir / name, passthrough_body(name)))
    files.append((resolver_path, resolver_body))

    collisions = [p for p, _ in files if p.exists() and not _is_ours(p)]
    if collisions:
        listed = "\n".join(f"  {p}" for p in collisions)
        print(
            f"REFUSED: these files exist and were not written by {MARKER}:\n"
            f"{listed}\n"
            f"`pii-lint init` writes its hooks into the repo's .git/hooks/ "
            f"and refuses to clobber a foreign file. Move the foreign "
            f"hook aside, or run `pii-lint init` in a different repo.",
            file=sys.stderr,
        )
        return 1

    if dry_run:
        print(f"[dry-run] repo hooks dir: {hooks_dir}")
        for path, _ in files:
            state = "overwrite (ours)" if path.exists() else "create"
            print(f"[dry-run] would {state}: {path}")
        chained_names = [n for n, c in chains.items() if c]
        if chained_names:
            print(
                "[dry-run] would chain to: "
                + ", ".join(f"{hooks_dir / (n + '.real')}" for n in chained_names)
            )
        print("[dry-run] core.hooksPath: not touched (per-repo install)")
        return 0

    try:
        for path, body in files:
            _write_executable(path, body)
    except OSError as e:
        print(f"FAILED to write hook: {e}", file=sys.stderr)
        return 1

    # The pre-commit hook is files[0]; the messages below name it by path.
    target = files[0][0]
    print(f"PII hook installed: {target}")
    print("Applies to this repo only. Run `pii-lint init` in another repo to enable there too.")
    print("Every `git commit` here now scans staged .csv/.jsonl/.md lines.")
    chained_names = [n for n, c in chains.items() if c]
    if chained_names:
        print(
            f"Existing {', '.join(chained_names)} moved aside to *.real "
            f"and chained (pre-commit/pre-push chain after a clean scan; "
            f"the rest chain immediately)."
        )
    print(f"Remove with: {MARKER} uninstall")
    return 0


def uninstall(dry_run: bool = False) -> int:
    """Remove the per-repo PII hooks and restore any chained original."""
    try:
        cwd = Path.cwd()
        hooks_dir = _repo_hooks_dir(cwd)
    except OSError as e:
        print(f"FAILED to resolve hooks dir: {e}", file=sys.stderr)
        return 1
    if hooks_dir is None:
        print("Not in a git repository. Nothing to uninstall here.")
        return 0

    candidates = [hooks_dir / name for name in FULL_HOOKS]
    candidates += [hooks_dir / name for name in PASSTHROUGH_HOOKS]
    candidates.append(hooks_dir / "pii-lint-resolver.sh")
    # Never delete a hook we did not write: a foreign file in this dir is
    # someone else's (husky, or a hand-rolled hook), not ours to remove.
    victims = [p for p in candidates if p.exists() and _is_ours(p)]

    if not victims:
        print(f"No {MARKER} hooks in {hooks_dir}.")
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

    # Restore any chained `.real` files back to their original names.
    # Both FULL_HOOKS (pre-commit, pre-push) and PASSTHROUGH_HOOKS go
    # through the same chain-via-`.real` dance on install, so both
    # kinds of `.real` files may need restoring on uninstall.
    restored: list[str] = []
    for hook_name in (*FULL_HOOKS, *PASSTHROUGH_HOOKS):
        if _restore_chained_hook(hooks_dir, hook_name):
            restored.append(hook_name)

    print(f"Removed {len(victims)} file(s) from {hooks_dir}.")
    if restored:
        print(
            "Restored: " + ", ".join(f"{n}.real -> {n}" for n in restored)
        )
    return 0
