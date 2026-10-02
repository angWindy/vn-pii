#!/usr/bin/env bash
# PA1 PII linter — Aider wrapper.
#
# Aider has no native hook system. The recommended pattern is to wrap
# the `aider` command with `pa1-lint guard`, which:
#   1. pre-scans `git diff HEAD` and refuses to run aider if HIGH+ PII exists.
#   2. runs aider.
#   3. post-scans `git diff HEAD` and blocks if new HIGH+ PII appeared.
#
# Usage:
#   ./examples/hooks/aider.sh --model claude-3-5-sonnet --message "refactor csv parser"
#
# Or alias it in your shell:
#   alias aider-safe='./path/to/vn-pii/examples/hooks/aider.sh'

set -e
exec pa1-lint guard -- aider "$@"