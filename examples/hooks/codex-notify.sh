#!/usr/bin/env bash
# PA1 PII linter — Codex CLI notify wrapper.
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
#   0 = clean
#   1 = HIGH finding
#   2 = CRITICAL finding (also guard refusal)
# Anything >= 1 means PII was introduced — bubble up as a notify message.
pa1-lint scan --staged
rc=$?
if [ "$rc" -ge 1 ]; then
    echo "[pa1-lint] CRITICAL/HIGH PII detected in staged diff (exit $rc). Ask Codex to redact before continuing."
    exit 2
fi
exit 0