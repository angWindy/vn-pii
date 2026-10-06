# 2026-10-02 — Review pass: relative path, dedupe, email mask

## Context

- **Session:** User selected "review_existing" from next-step options; I identified
  three concrete issues in the Slice 1–3 code and the user asked to fix steps 1–3,
  test thoroughly, then commit each separately and push.
- **Trigger:** Pre-Step plan → Step 2 (Ask mode) listed three bugs; user picked
  "review_existing" and then committed to fixing all three.

## What was done

- **Commit `0790de1` — fix(cli): key by_file by filename on single-file scans**
  - `scan_path()`: when `root` is a file, use `p.name` instead of `p.relative_to(root)` (which returned `'.'`).
  - Test: `test_single_file_path_uses_filename_as_key` in `tests/test_smoke.py`.
- **Commit `cca0993` — fix(free_text): apply combo to orchestrator output, stop double-scan**
  - Extracted `apply_combo(findings)` as a pure transform in `pii_linter/detectors/free_text.py`.
  - `cli._dispatch_value` now calls `scan_content` once and `apply_combo` on the merged list (was: `scan_content` + `scan_free_text`, both running the regex → duplicate findings on long free-text values).
  - `guard._scan_diff_text` updated to match the same pattern.
  - Tests: 7 new tests in `tests/test_free_text.py` covering scan short-circuits, NOTE-hint bypass, combo bump, and the orchestrator no-duplicate contract.
- **Commit `cd65b81` — fix(report): keep full email local-part in mask**
  - `_mask_email` previously did `".".join(local[::2])[:1] + "." + ".".join(local[1::2])[:1]` — the `[:1]` silently truncated the local-part to a single character per side for any value longer than 2 chars.
  - Rebuilt as `on = "".join(local[i] for i in range(0, len, 2))`, `off = "".join(local[i] for i in range(1, len, 2))`, joined with `'.'`. `'nguyen' -> 'n.u.e.g.y.n@...'`.
  - Tests: 6 cases in `tests/test_report.py` (short local, long local, no @, domain preservation, regression for other entities).

## Findings / decisions

- **Single file in `cli.py`, two fixes**: `scan_path` (Fix 1) and `_dispatch_value` (Fix 2) live in the same file. Rather than splitting the file or splitting the diff with `git add -p` (interactive-only, no good shell hook), I reverted `cli.py` to HEAD, applied Fix 1 first and committed, then applied Fix 2 in a second commit. Net effect: 3 commits, one per fix.
- **`apply_combo` is the right abstraction**: the orchestrator already knew what hints applied, so the free_text gate (30-char / NOTE) was a duplicate concern. The new transform is pure — input list → output list — which makes it trivially unit-testable and lets the orchestrator stay in charge of dispatch order.
- **Email mask is a security regression**: the prior `[:1]` truncation meant a report for `anthang2003@example.com` showed only `'a.t@example.com'`. While the mask still hides the original, the **shape was misleading** — readers couldn't tell whether the original was two characters or twenty. The new mask preserves on/off positions, which is what a security reviewer expects.
- **Test expectations needed double-checking**: my first pass at `test_mask_email_long_*` had wrong expectations (I mixed up the indices for `'anthang2003'`). Fixed by re-tracing `range(0, 11, 2)` and `range(1, 11, 2)` against the actual string. Lesson: when the spec is "1 on, 1 off", write the trace into a comment in the test.

## Acceptance

- [x] `pii-lint scan fixtures/gold/leads_50.csv` → exit 1, heading is `## leads_50.csv` (not `## .`)
- [x] `pii-lint scan fixtures/gold/notes_50.jsonl` → exit 2
- [x] `pii-lint scan fixtures/negative/aggregate_50.csv` → exit 0
- [x] `pii-lint scan fixtures/gold/` → still runs `rglob` as before
- [x] `python -m pytest tests/ -v` → 53/53 pass (was 39)

## Outstanding

- Other review notes from the prior message that were **not** in the user's
  1–3 scope, and remain in the codebase:
  - `guard._has_high_plus` post-scan uses `evidence_raw` as a set key — collisions
    if two distinct entities share the same raw match (e.g. a 12-digit string
    that matches both PHONE and ID_NUMBER patterns). Defer until a real case
    appears in the wild.

## Links

- Pre-step analysis: Step 2 (Ask mode) message — three findings listed.
- Patched files:
  - `pii_linter/cli.py` (Fix 1 + Fix 2)
  - `pii_linter/detectors/free_text.py` (Fix 2)
  - `pii_linter/guard.py` (Fix 2)
  - `pii_linter/report.py` (Fix 3)
- Test files added:
  - `tests/test_smoke.py` (+1)
  - `tests/test_free_text.py` (new, 7 tests)
  - `tests/test_report.py` (new, 6 tests)
- Commits: `0790de1`, `cca0993`, `cd65b81`