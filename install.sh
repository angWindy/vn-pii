#!/bin/sh
# PA1 PII linter - one-command installer.
#
#   curl -fsSL https://raw.githubusercontent.com/angWindy/vn-pii/main/install.sh | sh
#
# Installs the package and enables the global git hook, so afterwards a plain
# `git commit` in any repo blocks HIGH/CRITICAL PII with no per-repo setup.
# Run `pa1-lint uninstall` to remove the hook again.
#
# POSIX sh, no bashisms. Override the source with REPO_URL=... sh install.sh.
set -eu

REPO_URL="${REPO_URL:-git+https://github.com/angWindy/vn-pii}"

die() { echo "install.sh: $*" >&2; exit 1; }

# --- 1. a Python 3.11+ interpreter (tomllib is stdlib from 3.11) ----------
PY=""
for cand in python3.13 python3.12 python3.11 python3 python; do
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
if command -v pipx >/dev/null 2>&1; then
    echo "==> Installing with pipx"
    pipx install --force "$REPO_URL" >/dev/null \
        || die "pipx install failed. Try: pipx install --force $REPO_URL"
else
    echo "==> pipx not found, falling back to pip --user"
    echo "    (install pipx for a cleaner setup: pipx install pipx)"
    if [ -n "${VIRTUAL_ENV:-}" ] || "$PY" -c 'import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)' 2>/dev/null; then
        "$PY" -m pip install --upgrade "$REPO_URL" >/dev/null \
            || die "pip install failed. Try: $PY -m pip install $REPO_URL"
    else
        "$PY" -m pip install --user --upgrade "$REPO_URL" >/dev/null \
            || die "pip install failed. Try: $PY -m pip install --user $REPO_URL"
    fi
fi

# --- 3. locate the CLI (a pipx bin dir is often off a non-login PATH) -----
PA1=""
if command -v pa1-lint >/dev/null 2>&1; then
    PA1="pa1-lint"
elif [ -x "$HOME/.local/bin/pa1-lint" ]; then
    PA1="$HOME/.local/bin/pa1-lint"
else
    PA1="$PY -m pii_linter"   # same program, same exit codes
fi

# --- 4. enable the global git hook ----------------------------------------
# No sudo: the hook must be written for the invoking user, not for root.
echo "==> Enabling the git hook"
if ! "$PA1" init; then
    die "the hook was not installed; the package itself is fine.
  Retry with: \$PA1 init --dry-run   (prints what it would do, changes nothing)
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

Undo: pa1-lint uninstall
EOF
