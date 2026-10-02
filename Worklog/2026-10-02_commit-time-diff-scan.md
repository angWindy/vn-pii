# 2026-10-02 — Commit-time diff scan (Slice 3)

## Context

- **Session:** Wire the pre-commit hook to scan only the lines introduced by the staged git diff, surface `file:line` locations with masked evidence, and block the commit on HIGH+ findings.
- **Trigger:** User said *"every `git add` or `git commit` should auto-scan the lines introduced by the diff, show the masked location, and block the whole commit if there is PII."*

## What was done

- **CLI**: added `--staged` flag to `pa1-lint scan`. New helper `_git_diff_staged()` runs `git diff --cached --unified=0 --no-renames` and parses out `(file, line_no, text)` triples. New function `scan_staged(cwd, suppressions_path)` runs the same per-value detector dispatch on each added line.
- **Finding dataclass**: added two optional fields, `file` and `line_no`, both with safe defaults (`""` / `0`). Existing findings are untouched; only staged-mode findings carry values.
- **Reporter**: `render_markdown()` now appends a `location` column when any finding has a `file:line` cursor, and adds `mode: staged-diff` to the report header.
- **JSON output**: includes `file` and `line_no` in finding and per-file maps.
- **Pre-commit hook**: `.pre-commit-hooks.yaml` and `examples/pre-commit-config.yaml` now call `pa1-lint scan --staged` with `pass_filenames: false` (the hook scans the diff, not pre-commit's filename list) and `stages: [pre-commit, manual]`.
- **Tests**: 3 new smoke tests (`test_staged_scan_blocks_on_planted_phone`, `test_staged_scan_passes_on_clean`, `test_cli_scan_staged_exit_code_1`). 39/39 pass.

## Findings / decisions

- **Skip `git add` hook**: Git has no `pre-add` hook stage. Wrapping `git add` would require a shell alias that the user must configure and re-source after every shell. The user agreed to ship pre-commit only.
- **`pass_filenames: false`**: pre-commit framework normally passes the staged filenames into the entry command. We do not want that here — we want to scan the **diff**, which is what `--staged` reads internally.
- **`column_pattern` suppressions do not apply in staged mode**: the diff has no column header context. `value_prefix` suppressions still work because they key off the value text. Documented in `docs/spec.md` and `docs/user-guide.md`.
- **Parser bug fixed mid-implementation**: the first version of `_git_diff_staged` reset `current_file` on `+++ ` and skipped it, so staged mode always reported `file=''`. The fix is to capture `current_file` from the `diff --git a/foo b/foo` header and skip both `+++` and `---` lines.
- **Exit code via `git diff --cached`**: `_exit_for()` already returned `1`/`2` on HIGH/CRITICAL; nothing to add.

## Acceptance

- [x] `pa1-lint scan --staged` in a temp repo with a planted phone line exits 1 with `leads.csv:51 | PHONE | 3 | masked_evidence` in the report.
- [x] `pa1-lint scan --staged` in a temp repo with the clean aggregate fixture exits 0.
- [x] `pa1-lint scan --staged` in a repo with `fixtures/gold/notes_50.jsonl` exits 2 with 364 findings, mode `staged-diff`.
- [x] `.pre-commit-hooks.yaml` and `examples/pre-commit-config.yaml` declare `pa1-lint scan --staged` with the right stages and `pass_filenames: false`.
- [x] `docs/spec.md` lists `pa1-lint scan --staged` as part of the public API.
- [x] `docs/architecture.md` has a "Commit-time data flow" mermaid diagram.
- [x] `docs/PLAN.md` has a Slice 3 row and a Slice 3 acceptance block.
- [x] `README.md` has the top banner "Blocks your commit if HIGH+ PII is staged".
- [x] `docs/user-guide.md` shows the blocking message and a troubleshooting checklist.
- [x] `pytest tests/ -v` → 39/39 pass.

## Outstanding

- None — Slice 3 is complete. The next candidate is per-row performance review on large staged diffs (out of scope).

## Links

- [`PLAN.md`](../../PLAN.md) — top-level project plan
- [`docs/PLAN.md`](../../docs/PLAN.md) — detailed design history
- [`docs/user-guide.md §Pre-commit hook`](../../docs/user-guide.md#pre-commit-hook) — user-facing walkthrough
- Patched files: `pii_linter/__init__.py` (Finding fields), `pii_linter/cli.py` (`_git_diff_staged`, `scan_staged`, `--staged` flag, JSON output), `pii_linter/report.py` (`_row`, `render_markdown` diff columns), `.pre-commit-hooks.yaml`, `examples/pre-commit-config.yaml`, `tests/test_smoke.py` (+3 tests)