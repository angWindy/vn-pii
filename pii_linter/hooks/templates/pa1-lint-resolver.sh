#!/usr/bin/env bash
# pa1-lint — Python resolver.
#
# The pre-commit hook calls this script, NOT a hard-pinned Python, so
# that switching conda envs / re-installing into a different env does
# not silently break the PII scan.
#
# Strategy: probe a list of candidate Python interpreters. For each,
# try `import pii_linter`; the first one that succeeds gets the args
# this script received, re-execed. None succeeding -> exit 1 with an
# actionable message (the hook fails closed).
#
# Probed in order:
#   1. Whatever Python is on PATH (often `python3` symlink to a conda
#      env the shell has sourced).
#   2. Well-known conda env names: pa1, test, base — the user can add
#      more by editing this list. Each is checked at $HOME/miniconda3
#      first, then anaconda3, then /opt/conda.
#   3. Repo-local .venv (covers projects that ship a dev venv).
#   4. The conda env currently active in this shell, if any (read
#      from $CONDA_PREFIX).
#
# Adding a new env: append a `cand_conda "<name>"` entry under step 4
# below and reinstall (`pa1-lint init`).

set -u

probe() {
    # probe PY -> exit 0 if `import pii_linter` works, else 1
    "$1" -c "import pii_linter" >/dev/null 2>&1
}

run() {
    # run PY ARGS... -> exec PY with ARGS
    exec "$@"
}

# Step 1: PATH python. Cheap, frequently the right answer in an
# activated conda env.
for cand in python3 python; do
    py="$(command -v "$cand" || true)"
    if [ -n "${py:-}" ] && probe "$py"; then
        run "$py" "$@"
    fi
done

# Step 2: well-known conda envs. The user typically maintains 1-3 of
# these (pa1 for dev, test for fixtures, base for everything else).
cand_conda() {
    for prefix in "${HOME}/miniconda3" "${HOME}/anaconda3" "/opt/conda" \
                  "${HOME}/.local/share/mamba/envs"; do
        p="$prefix/envs/$1/bin/python3.11"
        if [ -x "$p" ] && probe "$p"; then
            run "$p" "$@"
        fi
        p="$prefix/envs/$1/bin/python3"
        if [ -x "$p" ] && probe "$p"; then
            run "$p" "$@"
        fi
    done
}
cand_conda pa1
cand_conda test

# Step 3: repo-local .venv (project venv). Walk up from cwd because
# the hook runs inside the repo whose pre-commit just fired.
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -n "${repo_root:-}" ]; then
    for cand in .venv/bin/python .venv/bin/python3 .venv/Scripts/python.exe; do
        p="$repo_root/$cand"
        if [ -x "$p" ] && probe "$p"; then
            run "$p" "$@"
        fi
    done
fi

# Step 4: the conda env currently active in this shell. Cheap and
# often the best guess for terminal-driven commits.
if [ -n "${CONDA_PREFIX:-}" ]; then
    for cand in "$CONDA_PREFIX/bin/python3.11" "$CONDA_PREFIX/bin/python3" \
                "$CONDA_PREFIX/bin/python"; do
        if [ -x "$cand" ] && probe "$cand"; then
            run "$cand" "$@"
        fi
    done
fi

echo "pa1-lint: no Python interpreter with pa1_linter installed was found." >&2
echo "pa1-lint: tried PATH python, conda envs {pa1,test}, repo .venv, and \$CONDA_PREFIX." >&2
echo "pa1-lint: install pa1-lint into any of those, e.g.:" >&2
echo "pa1-lint:   pipx install pa1-pii-linter" >&2
echo "pa1-lint: or bypass this commit once with: git commit --no-verify" >&2
exit 1