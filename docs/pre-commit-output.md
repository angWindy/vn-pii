# Pre-commit block output

This document pins down what the `pii-lint init` pre-commit hook
prints when a `git commit` would introduce HIGH/CRITICAL PII. The
goal is for the user to see **which file** tripped the scan and
**what to fix** in one block — no need to re-invoke
`pii-lint scan` to inspect the leak.

The hook always exits non-zero on a HIGH+ finding. Bypass once
with `git commit --no-verify`; that is the user's responsibility.

## Block message layout

Every block has the same three sections, in order:

### 1. Un-stage notice (always)

```
pii-lint: HIGH/CRITICAL PII found. Unstaging from the index:
  <file-1>
  <file-2>
  ...

pii-lint: re-run `git status` to see the remaining staged files, redact, and re-add.
```

The listed files are run through `git reset HEAD -- <file>` so
the offending row is no longer in the index waiting to leak on
the next commit. The file itself is untouched on disk.

### 2. Inline Markdown report (always when there is at least one finding)

The hook feeds the JSON scan output back into the same
`render_markdown` helper that `pii-lint scan --staged` uses, so
the report is byte-identical to the standalone command. Format:

```text
# PII scan report

- files_scanned: <N>
- total_findings: <N>
- severity_counts: LOW=<n>, MEDIUM=<n>, HIGH=<n>, CRITICAL=<n>
- mode: staged-diff

## <file-1>

| location | entity | severity | evidence_masked |
|---|---|---|---|
| <file-1>:<line> | <ENTITY> | <3 or 4> | `<masked cell>` |

> **Suggestions:** <per-entity suggestions, deduplicated>

## <file-2>
...
```

### 3. Exit code

The hook exits with the **scan** exit code, **not** zero:

| Highest finding severity | Exit | Meaning |
|---|---|---|
| none (clean commit) | 0 | Commit proceeds. |
| HIGH (3) | 1 | Commit blocked. |
| CRITICAL (4) | 2 | Commit blocked. |

## Privacy invariants

- `evidence_raw` is **never** read from the scan JSON and
  **never** written to stderr. The hook only reads
  `evidence_masked`, which is the display-safe form produced by
  `pii_linter.report.mask_value`.
- The inline report is written to **stderr**, not stdout, so
  git's commit-message machinery and any other consumer of
  commit output see no PII.
- A clean commit prints **nothing** from the hook.

## Worked example

A `leads.csv` with a planted phone number:

```text
$ git add leads.csv
$ git commit -m "Add new leads"

pii-lint: HIGH/CRITICAL PII found. Unstaging from the index:
  leads.csv

pii-lint: re-run `git status` to see the remaining staged files, redact, and re-add.

# PII scan report

- files_scanned: 2
- total_findings: 2
- severity_counts: LOW=0, MEDIUM=1, HIGH=1, CRITICAL=0
- mode: staged-diff

## leads.csv

| location | entity | severity | evidence_masked |
|---|---|---|---|
| leads.csv:2 | PHONE | 3 | `Nam,***,***` |
| leads.csv:2 | EMAIL | 2 | `Nam,***,***` |

> **Suggestions:** Replace with dummy_<n> or redact to ***. Replace with dummy@example.com or redact local-part.
```

`evidence_masked` masks the whole cell, so the neighbouring
columns are hidden too — the report never leaks the rest of the
row just to show you one value.

## Pre-push hook

The `pre-push` hook uses the same report renderer via
`pii-lint scan --pushed-base ... --pushed-head ...`, so the
output format is identical when the second wall fires.
