# Worklog Index

> **Every working session on this repo creates one file `Worklog/YYYY-MM-DD_<topic>.md`**
> and appends one row to the catalog below.
>
> Purpose: the next agent session reads this catalog to learn **what was fixed, why, and what is still outstanding**.

## Entry template

```markdown
# YYYY-MM-DD — <short topic, ≤6 words>

## Context
- Session: <initial objective>
- Why: <trigger — bug report / plan todo / user request>

## What was done
- **commit/file**: short description
- **commit/file**: short description

## Findings / decisions
- Found X → decided Y because Z.

## Acceptance
- [x] `pii-lint scan fixtures/gold/leads_50.csv` → exit 1
- [x] `pytest tests/ -v` → N tests pass

## Outstanding
- Bug #2 not yet fixed.
- Need user decision on approach v2 (option 1 / option 2).

## Links
- PLAN.md §Completion criteria
- docs/architecture.md §X
- PR #N / commit <hash>
```

## How to use the Worklog

| Agent needs | Read |
|---|---|
| See what the latest session changed | The newest entry in the catalog below |
| Find a previously fixed bug (avoid re-investigating) | `grep -ri "fix" tags/title/ Worklog/` |
| See what is still outstanding | Filter the catalog — `Status` column |
| Create a new entry | Copy the template above, save as `YYYY-MM-DD_<topic>.md`, append one row to the catalog below |

## Catalog

| Date | Topic | Status | File |
|---|---|---|---|
| 2026-10-02 | Fix `_list_files` to handle single-file paths | ✅ done | [`2026-10-02_bugfix-scan-single-file.md`](2026-10-02_bugfix-scan-single-file.md) |
| 2026-10-02 | Slice 3 — commit-time diff scan (`--staged`, pre-commit hook, `file:line` locations) | ✅ done | [`2026-10-02_commit-time-diff-scan.md`](2026-10-02_commit-time-diff-scan.md) |
| 2026-10-02 | Review pass — relative path key, dedupe free_text scan, email mask | ✅ done | [`2026-10-02_review-pass-fixes.md`](2026-10-02_review-pass-fixes.md) |
| 2026-10-05 | Bug sweep — pre-commit `types_or`, `guard --`, md prose, guard post-scan, exit codes | ✅ done | [`2026-10-05_bug-sweep-5-bugs.md`](2026-10-05_bug-sweep-5-bugs.md) |