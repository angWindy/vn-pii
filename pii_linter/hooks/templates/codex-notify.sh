#!/usr/bin/env bash
# PII linter — Codex CLI notify wrapper.
#
# Codex calls this script every time a turn ends (success or fail).
# We scan the staged/working diff and exit 2 on HIGH+ so Codex surfaces
# the report to the user and forces a re-prompt to clean up.
#
# Args passed by Codex (per docs): ignored.

set -u

# Only meaningful inside a git repo. Outside, silently exit 0.
if ! git rev-parse --git-dir >/dev/null 2>&1; then
    exit 0
fi

# Scan the staged diff. Exit code:
#   0  = clean
#   1  = HIGH finding
#   2  = CRITICAL finding
#   64 = bad usage (EX_USAGE) — broken config, NOT a PII finding
# 1/2 block so we stay fail-closed; 64 is surfaced as a config error so
# nobody chases a PII incident that never happened.
pii-lint scan --staged
rc=$?
if [ "$rc" -eq 64 ]; then
    echo "[pii-lint] pii-lint was invoked incorrectly (exit 64). Fix the hook/CLI config; this is NOT a PII finding."
    exit 64
fi
if [ "$rc" -ge 1 ]; then
    echo "[pii-lint] CRITICAL/HIGH PII detected in staged diff (exit $rc). Ask Codex to redact before continuing."
    exit 2
fi
exit 0