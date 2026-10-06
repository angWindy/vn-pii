#!/bin/sh
# PII linter - one-command installer.
#
#   curl -fsSL https://raw.githubusercontent.com/angWindy/vn-pii/main/install.sh | sh
#
# Installs the package and enables the global git hook, so afterwards a plain
# `git commit` in any repo blocks HIGH/CRITICAL PII with no per-repo setup.
# Run `pii-lint uninstall` to remove the hook again.
#
# POSIX sh, no bashisms. Override the source with REPO_URL=... sh install.sh.
set -eu

REPO_URL="${REPO_URL:-git+https://github.com/angWindy/vn-pii}"

die() { echo "install.sh: $*" >&2; exit 1; }

# --- 1. a Python 3.11+ interpreter (tomllib is stdlib from 3.11) ----------
# Prefer the interpreter the user's shell already has on PATH. When the user
# has run `conda activate pii`, the `python` symlink in that env is on PATH
# first, and conda envs often lack `python3` -- so we must test `python` before
# `python3.N` to avoid grabbing the system 3.12 by accident.
PY=""
for cand in python python3 python3.11 python3.12 python3.13; do
    if command -v "$cand" >/dev/null 2>&1; then
        if "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
            PY="$cand"
            break
        fi
    fi
done
[ -n "$PY" ] || die "need Python 3.11+ on PATH (tomllib is stdlib from 3.11).
  On Debian/Ubuntu: apt install python3.11, or use pyenv/uv/conda."

echo "==> Using $("$PY" -c 'import sys; print(sys.executable, sys.version.split()[0])')"

# --- 2. install the package, preferring an isolated pipx install ----------
# Isolation order: pipx -> our own venv -> in-env pip. We never fall back to
# `pip install --user` on a bare system interpreter: Debian/Ubuntu mark it
# externally managed (PEP 668) and that blocks --user too, so the "safe"
# fallback is exactly the one that fails.
if command -v pipx >/dev/null 2>&1; then
    echo "==> Installing with pipx"
    pipx install --force "$REPO_URL" >/dev/null \
        || die "pipx install failed. Try: pipx install --force $REPO_URL"
elif
    # Already inside a managed environment (venv or conda). The conda shell
    # hook does not export VIRTUAL_ENV, and a Python running *inside* a conda
    # env has sys.base_prefix equal to sys.prefix (conda re-points base_prefix
    # to itself when the env is active), so the sys.prefix check alone misses
    # it. Test the conda env-var first, then venv, then the prefix-mismatch
    # fallback for pyenv-virtualenv and friends.
    [ -n "${CONDA_DEFAULT_ENV:-}" ] || \
    [ -n "${VIRTUAL_ENV:-}" ] || \
    "$PY" -c 'import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)' 2>/dev/null
then
    # Already inside a venv/conda env: that env is ours to modify.
    if [ -n "${CONDA_DEFAULT_ENV:-}" ]; then
        CONDA_PREFIX_SHOWN="${CONDA_PREFIX:-$(conda info --envs 2>/dev/null | awk -v env="$CONDA_DEFAULT_ENV" '$1==env {print $NF}')}"
        echo "==> Installing into conda env: $CONDA_DEFAULT_ENV ($CONDA_PREFIX_SHOWN/bin/python)"
    elif [ -n "${VIRTUAL_ENV:-}" ]; then
        echo "==> Installing into venv: $VIRTUAL_ENV"
    else
        # Active interpreter reports a different prefix but neither env var is
        # set — covers `python -m venv .venv && ./venv/bin/python -m pip install`
        # without sourcing activate, and any Pyenv-virtualenv setup.
        ACTIVE_PREFIX="$("$PY" -c 'import sys; print(sys.prefix)')"
        echo "==> Installing into active virtualenv: $ACTIVE_PREFIX"
    fi
    "$PY" -m pip install --upgrade "$REPO_URL" >/dev/null \
        || die "pip install failed. Try: $PY -m pip install $REPO_URL"
else
    VENV="$HOME/.local/share/pii-lint/venv"
    echo "==> No pipx and no active venv; creating a private one at"
    echo "    $VENV"
    # A plain venv: its pip is what installs the package, and the venv path is
    # outside the externally-managed tree, so PEP 668 never applies here.
    "$PY" -m venv "$VENV" >/dev/null 2>&1 \
        || die "could not create a venv at $VENV. Install one with:
  $PY -m venv $VENV
or install pipx (recommended): pipx install pipx"
    VPY="$VENV/bin/python"
    [ -x "$VPY" ] || VPY="$VENV/bin/python3"
    [ -x "$VPY" ] || die "venv at $VENV has no interpreter."

    # `python -m venv` either seeds pip via ensurepip or fails outright, so
    # there is no "venv without pip" state to recover from here. Check anyway:
    # a distro missing python3-venv can produce a directory with no pip, and
    # the install below would then fail with a confusing "No module named pip".
    "$VPY" -m pip --version >/dev/null 2>&1 \
        || die "created $VENV but it has no pip (Debian/Ubuntu: apt install python3-venv).
  Or install pipx instead: pipx install $REPO_URL"
    "$VPY" -m pip install --upgrade "$REPO_URL" >/dev/null \
        || die "pip install into the private venv failed. Try:
  $VPY -m pip install $REPO_URL"
fi

# --- 3. locate the CLI ---------------------------------------------------
# Order matters: a CLI already on PATH is the user's deliberate choice, then
# the private venv we just created, then ~/.local/bin. The system interpreter
# is the last resort *only* when the package really is installed there —
# otherwise `python -m pii_linter` would import nothing and `init` would
# report a confusing failure instead of a real one.
PII=""
if command -v pii-lint >/dev/null 2>&1; then
    PII="pii-lint"
elif [ -n "${VPY:-}" ] && [ -x "$VPY" ]; then
    PII="$VPY -m pii_linter"
elif [ -x "$HOME/.local/bin/pii-lint" ]; then
    PII="$HOME/.local/bin/pii-lint"
elif "$PY" -c 'import pii_linter' >/dev/null 2>&1; then
    PII="$PY -m pii_linter"   # same program, same exit codes
else
    die "installed the package but cannot find its CLI.
  pipx:    export PATH=\"\$HOME/.local/bin:\$PATH\"
  private: export PATH=\"\$HOME/.local/share/pii-lint/venv/bin:\$PATH\"
  then re-run: sh -c \"\$(command -v pii-lint || echo '$HOME/.local/share/pii-lint/venv/bin/python') -m pii_linter init\""
fi

# --- 4. enable the global git hook ----------------------------------------
# No sudo: the hook must be written for the invoking user, not for root.
echo "==> Enabling the git hook"
if ! "$PII" init; then
    die "the hook was not installed; the package itself is fine.
  Retry with: \$PII init --dry-run   (prints what it would do, changes nothing)
  If you use husky or another hook manager, see docs/user-guide.md."
fi

cat <<'EOF'

Done. From now on, in any git repo on this machine:

  git add data.csv && git commit -m "..."   # scans the staged lines
  # HIGH/CRITICAL PII -> commit is blocked and the report prints to your terminal

Try it:
  printf 'name,phone\nNguyen,0912345678\n' > /tmp/t.csv
  cd "$(mktemp -d)" && git init -q . && cp /tmp/t.csv . \
    && git add t.csv && git commit -m test     # <- blocked

EOF

if [ -n "${VPY:-}" ]; then
    # The venv's bin dir is usually not on PATH, so tell them how to undo it.
    echo "The CLI lives in a private venv, which is probably not on your PATH:"
    echo "  export PATH=\"$HOME/.local/share/pii-lint/venv/bin:\$PATH\""
    echo "  # add that line to ~/.bashrc to make it permanent"
    echo
    echo "Undo: $VPY -m pii_linter uninstall"
else
    echo "Undo: pii-lint uninstall"
fi
