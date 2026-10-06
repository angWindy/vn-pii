#!/usr/bin/env bash
# PII linter — Claude Code PreToolUse hook.
#
# Reads the tool-call JSON from stdin (Claude injects it on stdin, NOT
# in environment variables). Extracts the file path, scans it if it
# looks like a PII-risk extension, and exits 2 on HIGH+ so Claude
# re-prompts itself to redact before the file is written.
#
# Why a separate file: PreToolUse is fire-and-forget; the matcher only
# chooses which tool calls trigger it. The hook has to live in a path
# the agent can execute, so we ship a small wrapper that owns the JSON
# parsing instead of inlining fragile bash into settings.json.
#
# Args passed by Claude: ignored. The real input is on stdin.
#
# Exit codes:
#   0  = OK to proceed (no PII, or non-PII file)
#   2  = block (HIGH/CRITICAL PII detected) — Claude will redact and retry
#   64 = EX_USAGE / broken config (NOT a PII finding) — surfaces as
#        a config error so nobody chases a phantom PII incident.

set -u

input="$(cat)"

# Prefer the on-PATH pii-lint (user-wide install), fall back to
# `python -m pii_linter` so this also works in venv/conda envs that
# did not put the console script on PATH.
pii_lint_cmd=()
if command -v pii-lint >/dev/null 2>&1; then
    pii_lint_cmd=(pii-lint)
else
    pii_lint_cmd=(python3 -m pii_linter)
fi

# Pull the file path out of the JSON. All three of Write / Edit /
# MultiEdit name the file `file_path` under `tool_input`, so a single
# extraction works for all of them. python3 is stdlib everywhere we
# care about and parses JSON reliably.
fpath="$(python3 - "$input" <<'PY' || true
import json
import sys

raw = sys.argv[1]
try:
    payload = json.loads(raw)
except Exception:
    sys.exit(0)
ti = payload.get("tool_input") or {}
if not isinstance(ti, dict):
    sys.exit(0)
fp = ti.get("file_path") or ti.get("notebook_path") or ""
if fp:
    print(fp)
PY
)"

# Nothing parseable, or no path -> nothing to scan.
if [ -z "${fpath:-}" ]; then
    exit 0
fi

# Only scan PII-risk extensions. Everything else (Python, JS, etc.) is
# out of documented scope; pii-lint scan is whole-file and would be
# overkill on a 5000-line source file.
case "$fpath" in
    *.csv|*.jsonl|*.md) ;;
    *) exit 0 ;;
esac

# If the file does not exist yet (Write to a new path), we still want
# to block. Write sends the new body in `content`; Edit in `new_string`.
# MultiEdit sends `edits` (list of {old_string, new_string}) — scan
# every new_string so a MultiEdit that smuggles PII in any sub-edit
# gets caught.
if [ ! -f "$fpath" ]; then
    content="$(python3 - "$input" <<'PY' || true
import json
import sys

raw = sys.argv[1]
try:
    payload = json.loads(raw)
except Exception:
    sys.exit(0)
ti = payload.get("tool_input") or {}
if not isinstance(ti, dict):
    sys.exit(0)
parts = []
c = ti.get("content")
if c:
    parts.append(c)
n = ti.get("new_string")
if n:
    parts.append(n)
edits = ti.get("edits")
if isinstance(edits, list):
    for e in edits:
        if isinstance(e, dict) and e.get("new_string"):
            parts.append(e["new_string"])
if parts:
    print("\n".join(parts), end="")
PY
)"
    if [ -z "${content:-}" ]; then
        exit 0
    fi
    # Scan via tmp file. pii-lint scan reads positional paths.
    tmp="$(mktemp --suffix=.$(basename "$fpath"))"
    trap 'rm -f "$tmp"' EXIT
    printf '%s' "$content" > "$tmp"
    "${pii_lint_cmd[@]}" scan -- "$tmp"
    rc=$?
    rm -f "$tmp"
    trap - EXIT
else
    # Existing file: scan directly. (PostToolUse would do this too,
    # but PreToolUse gives Claude a chance to redact without ever
    # writing the bad bytes.)
    "${pii_lint_cmd[@]}" scan -- "$fpath"
    rc=$?
fi

if [ "$rc" -eq 64 ]; then
    echo "[pii-lint] PreToolUse: pii-lint was invoked incorrectly (exit 64). Fix the hook/CLI config; this is NOT a PII finding." >&2
    exit 64
fi
if [ "$rc" -ge 1 ] && [ "$rc" -le 3 ]; then
    echo "[pii-lint] PreToolUse blocked: HIGH/CRITICAL PII detected in $fpath (exit $rc). Redact (e.g. dummy_<n>, REDACTED) before writing." >&2
    exit 2
fi
exit 0
