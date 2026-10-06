# AGENTS.md

> **Workflow rules for AI coding agents** (Cursor, Aider, Claude Code,
> GitHub Copilot Workspace, etc.) operating on this repository.
>
> Pair this with [`CLAUDE.md`](CLAUDE.md) for project context.

## 1. Slice 2 dropped the conda-env enforcement

`pii-lint` runs in any Python 3.11+ environment — no conda env check, no
`exit 3` for a "wrong" environment. This is intentional so end users can
adopt the tool with a single `pip install` (see [PLAN.md §Slice 2](PLAN.md)).

For this repo's local development, the maintainer still uses the `pii`
conda env because it isolates `Faker` (a heavy fixture-only dep) from
the system Python. **That is a maintainer convenience, not a tool
requirement.** Other contributors can use any virtualenv that has
`pip install -e .[dev]`.

If you want the dev env:

```bash
# Optional — only needed to regenerate synthetic fixtures or run tests
conda env create -f environment.yml
conda activate pii
```

## 2. Wrap PII-risk edits with `pii-lint guard`

Before modifying a `.csv`, `.jsonl`, or `.md` file outside
`fixtures/negative/`, wrap the edit tool with the guard:

```bash
pii-lint guard -- <edit-command-and-args>
```

If the guard exits `2`, **do not push the edit** — back out and tell
the human user. The exit code means a HIGH+ finding was introduced or
existed in the staged diff.

## 3. Never commit `fixtures/gold/*.csv` or `*.jsonl`

The repo `.gitignore` already blocks these, but if you (or an IDE
plugin) ever stage them, run:

```bash
git restore --staged fixtures/gold/*.csv fixtures/gold/*.jsonl
```

If you need a non-secret sample dataset, copy from `fixtures/negative/`
or generate fresh ones with the synthetic generator.

## 4. When adding a detector, also update `SEVERITY_BY_ENTITY`

A new `entity` string only carries a baseline severity if you add it to
[`SEVERITY_BY_ENTITY`](pii_linter/severity.py). Do this even for
seemingly obvious entries — `cli._exit_for` reads from the table.

## 5. Add tests for new detector / entity pairs

The test pyramid is:

- `tests/test_column_name.py` — header heuristics
- `tests/test_content_regex.py` — regex matches
- `tests/test_luhn_card.py` — Luhn + BIN
- `tests/test_suppressions.py` — YAML loader
- `tests/test_guard.py` — git-diff scan
- `tests/test_smoke.py` — end-to-end on fixtures

Every new detector should add at least one positive + one negative test
to the matching file.

## 6. Reference docs

- [`docs/contributing.md`](docs/contributing.md) — how to extend the
  scanner
- [`docs/detectors.md`](docs/detectors.md) — regex + Luhn reference
- [`docs/spec.md`](docs/spec.md) — public API
- [`docs/user-guide.md`](docs/user-guide.md) — install + troubleshooting
- [`.claude/rules/`](.claude/rules/) — auto-applied rules per file type

## 7. Hard limits (enforced by the scanner and by these rules)

- Never print `evidence_raw` to stdout, stderr, or a chat message.
- Never add suppressions for real customer data — only for
  clearly-synthetic prefixes (`id_`, `dummy_`, `test_`, `example`).
  All-zero padding is NOT a valid synthetic marker: `0000000000` matches
  the phone regex and `000000000000` matches the CCCD regex, both at
  CRITICAL, so such a suppression can never unblock a commit.
- Never modify a release version or push to a registry without human
  approval.