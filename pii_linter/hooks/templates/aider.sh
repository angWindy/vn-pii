#!/usr/bin/env bash
# PA1 PII linter — Aider wrapper.
#
# Aider has no native hook system. The recommended pattern is to wrap
# the `aider` command with `pa1-lint guard`, which:
#   1. pre-scans `git diff HEAD` and refuses to run aider if HIGH+ PII exists.
#   2. runs aider.
#   3. post-scans `git diff HEAD` and blocks if new HIGH+ PII appeared.
#
# Usage (after `pa1-lint install-hooks aider`, which drops a wrapper
# next to the pa1-lint binary called `pa1-lint-aider`):
#   pa1-lint-aider --model claude-3-5-sonnet --message "refactor csv parser"
#
# Or alias it in your shell:
#   alias aider-safe='pa1-lint-aider'

set -e
exec pa1-lint guard -- aider "$@"