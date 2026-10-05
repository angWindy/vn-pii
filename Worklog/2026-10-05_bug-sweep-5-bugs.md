# 2026-10-05 — Bug sweep: pre-commit config, guard `--`, md prose, exit codes

## Context

- **Session:** Fix 5 bugs from an external bug report (all reproduced on a green baseline of 68 tests).
- **Trigger:** User supplied a bug report titled "Báo cáo bug — pa1-lint" with severity ratings, reproduction commands and a suggested fix order (Bug 2 → 3 → 1 → 4 → 5).
- **Environment:** `pre-commit` 4.6.2, Python 3.12, `pa1-pii-linter` installed from source (not editable).

## What was done

Seven commits, one fix each, so any of them can be reverted independently.

- **`22c9032` fix(pre-commit): drop invalid `types_or`**
  - `.pre-commit-hooks.yaml` + `examples/pre-commit-config.yaml` declared `types_or: [csv, jsonl, markdown]`. `identify` has no `jsonl` tag, so pre-commit raised `InvalidConfigError` and refused to load the config — **every** `git commit` failed, even for files with no PII at all.
  - The gate was redundant: `scan --staged` runs `git diff --cached` and filters to `.csv/.jsonl/.md` itself.
  - Verified with pre-commit 4.6.2: clean commit → `Passed`, PII commit → `Failed`.

- **`80c58a1` fix(md): scan prose, not just Markdown tables**
  - `_scan_md` skipped every non-table line, so `pa1-lint scan <file>.md` reported 0 findings for a file that the other two code paths flagged with 5. Same file, same data, three different answers.
  - Prose lines are now scanned with no column hints — the same path `guard` and `scan --staged` take. Table rows keep their `col<N>` heuristics unchanged.

- **`8e0d31c` fix(guard): accept the documented `--` separator**
  - `argparse.REMAINDER` swallowed `--` and passed it to subprocess as `argv[0]` → `FileNotFoundError: '--'`. The bare form worked, which is why it survived.
  - `--` is the documented spelling in 7 files, and the bundled `install-hooks aider` template used it, so every installed `pa1-lint-aider` invocation crashed and never launched aider.
  - Normalised inside `guard.run`, the choke point all callers route through.

- **`45eccf6` fix(guard): anchor post-scan to pre-command HEAD**
  - Post-scan re-ran `git diff HEAD`. After the wrapped command commits, that diff is empty — the staged content is now part of HEAD. `guard` could not detect PII the agent had just committed, which is the exact scenario guard exists for.
  - Measured: before commit `git diff HEAD` → 2 lines; after commit → 2 lines, but `git diff HEAD~1` → 4 lines. The PII was there the whole time, just never inspected.
  - Now records HEAD before running the command and diffs `<old>..<new>` when it moved.

- **`fe7c1d7` fix(guard): restrict diff scanning to documented formats**
  - **Not in the original report — found while implementing the suppression request.**
  - `_diff_added_lines` collected `+` lines from *every* file in the diff, while `cli.scan_staged` filters to `.csv/.jsonl/.md`. The guard scanned files the tool never claimed to cover.
  - Concretely: this repo blocked itself. `tests/test_guard.py` has carried a synthetic phone literal since the guard tests were first written, and once prose scanning landed, the guard started flagging its own test file.
  - `TARGET_EXTS` moved to the package root. It cannot live in `cli.py` — `cli` imports `guard` lazily inside `_cmd_guard`, so `guard` importing back would be circular.
  - Verified 6/6: clean passes, PHONE in CSV / md prose / md table all block, same number in `.py` and `.sh` ignored.

- **`9d4a230` fix(cli): separate bad usage from CRITICAL PII**
  - `docs/spec.md` defines exit 2 as CRITICAL, but argparse also exits 2 on a bad flag. `codex-notify.sh` tested `rc >= 1` so it stayed fail-closed and safe, but logged "CRITICAL/HIGH PII detected" for what was really a broken hook config.
  - Added `EX_USAGE = 64` (sysexits.h) via a `_Parser` subclass used as the root `parser_class`, so subparsers inherit it. Exit 2 now unambiguously means CRITICAL.

- **`4ab7c96` fix(guard): load suppressions for the diff scan**
  - `scan` and `scan --staged` both accept `--suppressions`; the guard's diff scanner took no arguments, so a suppression that worked for one entry point was silently ignored by the other.
  - `_scan_diff_text(text, suppressions=None)` — optional, so existing callers are unaffected. `run()` loads the repo-root file once and threads it through both scans; a malformed file degrades to "no suppressions" instead of aborting the guard.

## Findings / decisions

- **`value_prefix` only matches when the *line* starts with the prefix.** A `dummy_` prefix does **not** hide a phone number sitting mid-line — the regex finds the digits wherever they are. This is why adding a suppression alone could not unblock the repo, and why the real fix was the extension filter. Recorded in the commit body so the next session does not retry it.
- **`guard` is not a superset of `scan`.** Three entry points meant three code paths with three different notions of "what to scan". The fixes align them, but the duplication (`_git_diff_text` in guard vs `_git_diff_staged` in cli) is still there and will drift again.
- **Each commit was verified green in isolation** via `git archive <sha> | tar -x` into a scratch dir and running pytest there. Test count climbs monotonically: 68 → 71 → 72 → 74 → 75 → 77 → 78. A bisect on this range lands on a passing commit at every step.
- **`guard` HIGH-only still exits 2** while `scan` exits 1. Left deliberately: `AGENTS.md` §2 and `.claude/rules/pii-guard.md` both document "guard exits 2" as the refusal signal, and those rules govern the agent's own editing. Aligning it is a separate decision that needs a human.
- **Committing per-bug cost real effort.** `cli.py` and `guard.py` each carried 3–4 independent fixes across 11 and 16 hunks; intermediate variants were built by rewriting the HEAD version with just the one change. Not worth automating for one series, but the technique is worth remembering for any future multi-bug sweep.

## Acceptance

- [x] `pa1-lint scan <prose .md>` → 5 findings (was 0)
- [x] `scan <file>.md` and `scan --staged` agree on identical content
- [x] pre-commit 4.6.2: clean commit `Passed`, PII commit `Failed`
- [x] `pa1-lint guard -- echo hi` → exit 0 (was `FileNotFoundError: '--'`)
- [x] `pa1-lint guard <committing cmd>` → exit 2, PII in the new commit caught
- [x] `pa1-lint guard <clean cmd>` → exit 0
- [x] bad flag → exit 64; CRITICAL finding → exit 2
- [x] guard scope matrix 6/6 (csv / md prose / md table block; .py / .sh ignored)
- [x] `pytest tests/` → 78 passed (was 68)
- [x] each of the 7 commits passes the suite independently
- [x] `pa1-lint guard -- echo ok` on this repo's own diff → exit 0 (no HIGH+)
- [x] All 7 commits authored by the repo's configured author (`angwindy`)

## Outstanding

- **Bug 5 part (b), intentionally not fixed:** `guard` returns 2 for HIGH-only findings while `scan` returns 1 for the same severity. Aligning them contradicts `AGENTS.md` §2 and `.claude/rules/pii-guard.md:36-37`, which treat "guard exits 2" as the refusal signal. Needs a human decision on which contract wins.
- **`guard` still does not share `_git_diff_staged` with `cli`.** Two implementations of "added lines in the diff" exist; they now behave the same but will drift again. Worth unifying if a third entry point ever appears.
- `pre-commit` and `identify` are not declared in `pyproject.toml` (dev extras are `Faker` + `pytest` only). The two config-validation tests `importorskip` for them, so they silently stop running if pre-commit is absent. Consider adding it to the dev extra.

## Links

- [`PLAN.md`](../PLAN.md) §Scope — updated `.md (table)` → `.md (tables and prose)`
- [`docs/spec.md`](../docs/spec.md) — exit-code table (`+64`), guard anchoring, scan scope
- [`docs/user-guide.md`](../docs/user-guide.md) — guard wrapper steps 1–4
- [`AGENTS.md`](../AGENTS.md) §2 — why no commit was pushed while the guard was returning 2
- Commits: `22c9032`, `80c58a1`, `8e0d31c`, `45eccf6`, `fe7c1d7`, `9d4a230`, `4ab7c96`
- Patched: `pii_linter/guard.py`, `pii_linter/cli.py`, `pii_linter/__init__.py`, `pii_linter/hooks/templates/codex-notify.sh`, `.pre-commit-hooks.yaml`, `examples/pre-commit-config.yaml`, `suppressions.toml`
