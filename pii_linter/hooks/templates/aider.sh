#!/usr/bin/env bash
# PII linter — Aider wrapper.
#
# Aider has no native hook system. The recommended pattern is to wrap
# the `aider` command with `pii-lint guard`, which:
#   1. pre-scans `git diff HEAD` and refuses to run aider if HIGH+ PII exists.
#   2. runs aider.
#   3. post-scans `git diff HEAD` and blocks if new HIGH+ PII appeared.
#
# Usage (after `pii-lint install-hooks aider`, which drops a wrapper
# next to the pii-lint binary called `pii-lint-aider`):
#   pii-lint-aider --model claude-3-5-sonnet --message "refactor csv parser"
#
# Or alias it in your shell:
#   alias aider-safe='pii-lint-aider'

set -e
exec pii-lint guard -- aider "$@"