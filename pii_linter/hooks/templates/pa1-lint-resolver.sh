#!/usr/bin/env bash
# pa1-lint — Python resolver.
#
# The pre-commit hook calls this script, NOT a hard-pinned Python, so
# that switching conda envs / re-installing into a different env does
# not silently break the PII scan.
#
# Strategy: walk a list of "search roots" (each is a directory that
# contains Python interpreters, either directly under `bin/` or under
# `envs/<name>/bin/` for conda). For every Python we find, probe
# `import pii_linter`; the first one that succeeds gets the args this
# script received, re-execed. None succeeding -> exit 1 with an
# actionable message (the hook fails closed).
#
# What gets searched, in order:
#   1. Whatever Python is on PATH (often `python3` symlink to an
#      activated conda env — frequent winner for terminal commits).
#   2. The conda env currently active in this shell ($CONDA_PREFIX).
#   3. The repo-local .venv (project venv).
#   4. Every env under each "conda-style search root" — conda, mamba,
#      and micromamba install all use the same `<root>/envs/<name>/bin`
#      layout. The base env is at `<root>/bin/`.
#   5. pyenv (`~/.pyenv/versions/*`) and pipenv / virtualenvwrapper
#      (`~/.local/share/virtualenvs/*`, `~/.virtualenvs/*`).
#
# No env names are hard-coded. Adding a new conda env, pyenv version,
# or venv anywhere under those roots is picked up automatically on
# the next commit — no `pa1-lint init` needed.
#
# To add a brand-new search root (e.g. your company ships Python
# under /opt/pyenv): edit `SEARCH_ROOTS` below.

set -u

# ----------------------------------------------------------------------------
# Configuration: search roots. Add a path here and reinstall the hook if you
# need to look in a directory we don't already check.
# ----------------------------------------------------------------------------
# Each entry is checked as both a direct bin dir (for the env at that root)
# AND a parent of envs/ (for conda-style sub-envs under it).
SEARCH_ROOTS=(
    "${HOME}/miniconda3"
    "${HOME}/anaconda3"
    "${HOME}/micromamba"
    "/opt/conda"
    "/opt/anaconda3"
    "/usr/local/anaconda3"
    "${HOME}/.local/share/mamba/envs"   # mamba-only env dir
)
PYENV_ROOT="${PYENV_ROOT:-${HOME}/.pyenv}"
VENV_ROOTS=(
    "${HOME}/.local/share/virtualenvs"  # pipenv
    "${HOME}/.virtualenvs"              # virtualenvwrapper
)

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

probe() {
    # probe PY -> exit 0 if `import pii_linter` works, else 1
    "$1" -c "import pii_linter" >/dev/null 2>&1
}

run() {
    # run PY ARGS... -> exec PY with ARGS
    exec "$@"
}

# try_py PY_PATH ARGS... -> if probe succeeds, exec PY_PATH with ARGS
try_py() {
    local py="$1"
    shift
    if [ -x "$py" ] && probe "$py"; then
        run "$py" "$@"
    fi
}

# scan a single bin dir: try every python* in it. The remaining
# positional args (after $1) are the args to pass to the picked Python.
scan_bin() {
    local dir="$1"
    shift
    [ -d "$dir" ] || return 0
    # Sorted so 3.11 wins over 3 (preferred) but anything goes.
    for py in "$dir"/python3.[0-9][0-9] "$dir"/python3 "$dir"/python; do
        [ -x "$py" ] || continue
        try_py "$py" "$@"
    done
}

# scan a conda-style search root: probe <root>/bin (base env) and every
# <root>/envs/*/bin (sub-envs). Remaining positional args are forwarded
# to the picked Python.
scan_conda_root() {
    local root="$1"
    shift
    [ -d "$root" ] || return 0
    # Base env.
    scan_bin "$root/bin" "$@"
    # Sub-envs. Globs naturally no-op on missing dirs; set -u is fine
    # because we explicitly test -d.
    for env_dir in "$root/envs"/*; do
        [ -d "$env_dir" ] || continue
        scan_bin "$env_dir/bin" "$@"
    done
}

# ----------------------------------------------------------------------------
# Search
# ----------------------------------------------------------------------------

# Step 1: PATH python. Cheap, frequently the right answer in an
# activated conda env.
for cand in python3 python; do
    py="$(command -v "$cand" || true)"
    if [ -n "${py:-}" ]; then
        try_py "$py" "$@"
    fi
done

# Step 2: the conda env currently active in this shell. Cheap and
# often the best guess for terminal-driven commits.
if [ -n "${CONDA_PREFIX:-}" ]; then
    scan_bin "$CONDA_PREFIX/bin" "$@"
fi

# Step 3: repo-local .venv. Walk up from cwd because the hook runs
# inside the repo whose pre-commit just fired.
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -n "${repo_root:-}" ]; then
    for cand in .venv/bin .venv/Scripts; do
        scan_bin "$repo_root/$cand" "$@"
    done
fi

# Step 4: every well-known conda/mamba install location. Quét cả
# base env lẫn mọi sub-env, không cần biết tên.
for root in "${SEARCH_ROOTS[@]}"; do
    scan_conda_root "$root" "$@"
done

# mamba có thể cài env thẳng dưới ~/.local/share/mamba/envs/<n>/bin
# mà không có base ở parent. Đã cover qua vòng lặp SEARCH_ROOTS
# nếu root có envs/; nếu root trỏ thẳng vào env dir thì scan_bin
# cũng xử lý được nhờ scan_conda_root kiểm tra cả <root>/bin.

# Step 5: pyenv + pipenv/virtualenvwrapper.
if [ -d "$PYENV_ROOT/versions" ]; then
    for ver_dir in "$PYENV_ROOT/versions"/*; do
        [ -d "$ver_dir" ] || continue
        scan_bin "$ver_dir/bin" "$@"
    done
fi
for vroot in "${VENV_ROOTS[@]}"; do
    if [ -d "$vroot" ]; then
        for venv in "$vroot"/*; do
            [ -d "$venv" ] || continue
            scan_bin "$venv/bin" "$@"
        done
    fi
done

# Step 6: user-defined additions via PA1_LINT_EXTRA_PYTHONS. Comma-
# separated list of absolute paths to try. Useful for one-off
# interpreter paths that don't fit any of the conventions above.
if [ -n "${PA1_LINT_EXTRA_PYTHONS:-}" ]; then
    IFS=',' read -ra extras <<< "$PA1_LINT_EXTRA_PYTHONS"
    for extra in "${extras[@]}"; do
        try_py "$extra" "$@"
    done
fi

# ----------------------------------------------------------------------------
# Fallthrough: no candidate had pii_linter installed. Fail closed with
# an actionable message.
# ----------------------------------------------------------------------------

echo "pa1-lint: no Python interpreter with pa1_linter installed was found." >&2
echo "pa1-lint: searched PATH python, \$CONDA_PREFIX, repo .venv, and every" >&2
echo "pa1-lint: env under:" >&2
for root in "${SEARCH_ROOTS[@]}"; do
    [ -d "$root" ] && echo "pa1-lint:   $root" >&2
done
echo "pa1-lint: also looked in $PYENV_ROOT/versions, ${VENV_ROOTS[*]}." >&2
echo "pa1-lint: install pa1-lint into any of those, e.g.:" >&2
echo "pa1-lint:   pipx install pa1-pii-linter" >&2
echo "pa1-lint: or PA1_LINT_EXTRA_PYTHONS=/abs/path/to/python to point at one" >&2
echo "pa1-lint: or bypass this commit once with: git commit --no-verify" >&2
exit 1