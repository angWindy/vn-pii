# 2026-10-02 — Fix `_list_files` single-file path

## Context

- **Session:** Verify Slice 1 completion and fix a bug discovered during verification.
- **Trigger:** User said "what to do next" → reviewed plan v3 → found that one of the four acceptance tests in §Completion criteria (`pii-lint scan fixtures/gold/leads_50.csv`) was failing with `exit 0, files_scanned: 0`.

## What was done

- **Verify**: ran `pii-lint scan fixtures/gold/leads_50.csv` → exit 0, zero findings (expected: exit 1, at least one PHONE).
- **Root cause**: `_list_files(root)` in `pii_linter/cli.py:55–63` called `root.rglob('*')`; when `root` is a file (not a directory), `rglob` returns zero items, so the CLI sees nothing to scan.
- **Patch**: added four lines of early-return when `root.is_file()` (only yield if the suffix is in `{csv,jsonl,md}`). The `rglob` logic for directories is unchanged.

```python
# pii_linter/cli.py — _list_files()
if root.is_file():
    if root.suffix.lower() in _TARGET_EXTS:
        yield root
    return
base_depth = len(root.parts) - 1
...
```

- **Bonus discovery**: the five docs files (`docs/architecture.md`, `contributing.md`, `detectors.md`, `spec.md`, `user-guide.md`) already existed from earlier → §10 of plan v3 was effectively complete. Only the navigation layer (PLAN/Worklog/Index) was missing.
- **Created the navigation layer**: `PLAN.md`, `Worklog/INDEX.md`, this file, `Index.md` (at root).

## Findings / decisions

- **`rglob` does not yield the root file**: Python's `Path.rglob('*')` on a file path is empty — this is a well-documented behaviour but easy to miss. We should add an edge-case test.
- **Plan v3 `pending` status did not reflect reality**: most of the 17 todos were already done in earlier sessions; only the navigation layer was missing. Do not trust plan status blindly; always `ls` first.
- **Bug is in the CLI layer, not the detector layer**: detectors were correct (the JSONL scan produced 364 findings); only the CLI failed to enumerate a single file. That is why only `_list_files` was patched; `detectors/` was left untouched.

## Acceptance

- [x] `pii-lint scan fixtures/gold/leads_50.csv` → exit 1, 100 findings (50 PHONE + 50 EMAIL)
- [x] `pii-lint scan fixtures/gold/notes_50.jsonl` → exit 2, 364 findings (CRITICAL)
- [x] `pii-lint scan fixtures/negative/aggregate_50.csv` → exit 0, zero findings
- [x] `pii-lint scan fixtures/gold/` (directory) → still runs `rglob` as before
- [x] `pytest tests/test_smoke.py -v` → 4 passed
- [x] Plan v3 §Completion criteria: 7/7 pass

## Outstanding

- None — Slice 1 is complete. The out-of-scope items remain (cross-file, Presidio, SARIF, PyPI).

## Links

- [`PLAN.md`](../../PLAN.md) §Completion criteria
- [`docs/architecture.md`](../../docs/architecture.md) §Layered design
- Patched file: `pii_linter/cli.py` `_list_files()` (line 55–63)