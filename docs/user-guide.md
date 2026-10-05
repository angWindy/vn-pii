# User guide

PA1 PII Linter ships as a zero-dependency Python package plus a CLI entry
point. You can use it two different ways: as a **pre-commit hook**
(recommended for any project that touches CSV / JSONL data) or as a
**wrapper** around an AI agent command.

Slice 2 made the tool work in any Python 3.11+ environment with a single
`pip install` and **no** extra packages.

## Install

### End user (your own project)

```bash
pip install git+https://github.com/angWindy/vn-pii
```

That is it. `pa1-lint` is now on your `PATH`. The tool has zero runtime
dependencies, so this command does not pull anything else.

Verify:

```bash
pa1-lint --version          # 0.1.0
pa1-lint --help
```

### Contributor (this repo)

```bash
git clone https://github.com/angWindy/vn-pii
cd vn-pii
pip install -e .[dev]
```

The `[dev]` extra pulls `Faker` (for the synthetic fixture generator)
and `pytest`. None of them are required at scan time.

## Run a one-off scan

```bash
pa1-lint scan path/to/dataset --format markdown
pa1-lint scan path/to/dataset --format json --suppressions suppressions.toml
```

JSON is easier to wire into CI dashboards. Markdown is preferred when you
want a human-readable report.

## Suppressions

Create `suppressions.toml` in your repo:

```toml
[[suppressions]]
column_pattern = "customer_id"
value_prefix = "id_"
owner = "synth-data-team"
expires_at = 2027-12-31
reason = "Faker seed 42; verified by tests/test_smoke.py"
```

Pass it to the scan:

```bash
pa1-lint scan path/to/dataset --suppressions suppressions.toml
```

### Best practices

- Only suppress columns whose values are clearly synthetic (`id_`,
  `dummy_`, `0`-padded accounts).
- Set `expires_at` far in the future but revisit every quarter.
- Never suppress real customer data. If you find yourself needing to,
  the right fix is to remove the data, not silence the scanner.

## Pre-commit hook

1. Copy [`examples/pre-commit-config.yaml`](examples/pre-commit-config.yaml)
   into your repo as `.pre-commit-config.yaml`.
2. Make sure `pa1-lint` is installed in the active Python env
   (`pa1-lint --version` should work).
3. Install pre-commit:

   ```bash
   pip install pre-commit
   pre-commit install
   ```

From now on, every `git commit` that touches `.csv` / `.jsonl` /
`.markdown` files runs `pa1-lint scan --staged` on the staged content.
**Only the lines added by your commit are scanned** — pre-existing PII
in lines you did not touch is ignored. The commit is blocked if HIGH or
CRITICAL findings appear.

If you want to scan everything (not just staged files), call
`pa1-lint scan <path>` directly.

### What a blocked commit looks like

```text
$ git add leads.csv
$ git commit -m "Add new leads"
PA1 PII linter (staged diff)............................Failed
- hook id: pa1-lint-staged
- exit code: 1

# PA1 PII scan report

- files_scanned: 1
- total_findings: 1
- severity_counts: LOW=0, MEDIUM=0, HIGH=1, CRITICAL=0
- mode: staged-diff

## leads.csv

| location | entity | severity | evidence_masked |
|---|---|---|---|
| leads.csv:51 | PHONE | 3 | `planted,***,foo@bar.com` |

> **Suggestions:** Replace with dummy_<n> or redact to ***.
```

Fix the line, re-stage (`git add leads.csv`), and commit again.

If you want to scan everything (not just staged files), call
`pa1-lint scan <path>` directly.

## Wrap an AI agent

`pa1-lint guard` is designed to wrap any command that creates or edits
files. The common cases are:

```bash
pa1-lint guard -- aider --message "summarise repo"
pa1-lint guard -- cursor ...
pa1-lint guard -- claude -p "..."
```

The wrapper:

1. Snapshots `git diff HEAD` (added text in `.csv` / `.jsonl` / `.md` files
   only — other file types are outside the documented scope).
2. Scans that text. If HIGH+ findings exist, the command is not run and
   the wrapper exits `2`.
3. Records the current `HEAD`, then runs the wrapped command.
4. Re-scans, anchored to the `HEAD` from step 3. If the command created
   commits the diff is `<old HEAD>..<new HEAD>`, so PII the command
   committed is still inspected; otherwise it is the live `git diff HEAD`.
   New HIGH+ findings exit `2`.

Step 4 is anchored deliberately: a plain `git diff HEAD` goes blind once
the wrapped command commits, because the staged content has become part of
`HEAD` and the diff comes back empty.

This is meant to be wired into your shell alias:

```bash
alias aider-safe="pa1-lint guard -- aider"
```

## Coding-agent hooks (Claude Code, Cursor, Cody, Codex, ...)

Most modern coding agents expose a **native hook system** that is a
better fit than wrapping the whole command: the agent sees a non-zero
exit and re-prompts itself to redact before continuing.

There is one way to install the hook configs:

### `pa1-lint install-hooks`

The CLI ships a subcommand that copies the bundled templates into the
correct location for the agent you choose. It deep-merges existing
JSON files (so a `UserPromptSubmit` you already configured survives) and
appends to TOML files (also preserving other agents' notify scripts).

```bash
# User-wide (default — writes under $HOME):
pa1-lint install-hooks claude-code
pa1-lint install-hooks all

# Project-wide (writes under current git repo root):
pa1-lint install-hooks claude-code --project
pa1-lint install-hooks cursor     --project

# Inspect first, write later:
pa1-lint install-hooks codex --dry-run

# Replace existing config instead of merging:
pa1-lint install-hooks cursor --force-replace
```

The agent list is `claude-code | cursor | cody | codex | aider | all`.
Aider is special: it drops a `pa1-lint-aider` wrapper next to the
`pa1-lint` binary (or in `$HOME/.local/bin` if the lookup fails), so you
can alias `aider-safe='pa1-lint-aider'` or call it directly.

Every hook calls `pa1-lint scan` and bubbles up the exit code:
`1` (HIGH) and `2` (CRITICAL) block the tool call. The agent then
re-prompts itself to redact.

## Using pa1-lint in a downstream project

Imagine you work on `Customer-Analytics` (your own repo) and you want
every CSV / JSONL commit scanned:

```bash
# 1. One-time setup in Customer-Analytics/
pip install git+https://github.com/angWindy/vn-pii
curl -O https://raw.githubusercontent.com/angWindy/vn-pii/main/examples/pre-commit-config.yaml
mv pre-commit-config.yaml .pre-commit-config.yaml
pip install pre-commit
pre-commit install

# 2. Add a per-project suppressions.toml
cat > suppressions.toml <<'EOF'
[[suppressions]]
column_pattern = "internal_id"
value_prefix = "id_"
owner = "data-eng"
expires_at = 2027-12-31
reason = "Synthetic IDs generated by our Faker factory."
EOF

# 3. Commit
git add data.csv suppressions.toml
git commit -m "Add Q4 customer dataset"   # blocked if HIGH+ findings
```

## Troubleshooting

### `pa1-lint: command not found`

`pa1-lint` is the console-script entry point declared in `pyproject.toml`.
It installs into whichever Python environment you ran `pip install` in.
Check that you ran `pip install` in the env you are using:

```bash
which python
python -m pip show pa1-pii-linter
```

If you used a virtual environment, make sure it is activated before
running `pa1-lint`.

### `Python 3.11 or newer is required`

Slice 2 bumped the Python floor to 3.11 because `tomllib` is in stdlib
from 3.11. Use `python3.11`, `python3.12`, `python3.13` or newer:

```bash
python3.11 -m pip install git+https://github.com/angWindy/vn-pii
```

### Pre-commit hook does not run

Run `pre-commit run --all-files` and check the output. The most common
causes are:

1. `pa1-lint` is not on `PATH` of the env pre-commit uses. The hook is
   declared with `language: system`, which means pre-commit calls the
   literal `pa1-lint` from `PATH`. If you used a virtualenv, run
   `pre-commit install` from inside that env so the hook can find the
   binary.
2. The file you are staging is not in `types_or: [csv, jsonl, markdown]`.
   pre-commit filters out other extensions; rename or move the file.
3. `core.hooksPath` is set to a non-empty value (e.g. `.husky`). The
   pre-commit framework then does not get to install its own hook.
   ```bash
   git config --get core.hooksPath    # should be empty / unset
   ```

To re-run the hook without committing:

```bash
pre-commit run pa1-lint-staged --hook-stage pre-commit
```

### Why is the staged report different from the full report?

`pa1-lint scan --staged` only scans the lines introduced by your commit.
`pa1-lint scan path/to/dataset` reads the whole file from disk. Same
detectors, same exit codes — only the input scope differs.

### False positive on `customer_id` containing `id_001`

Add a suppression entry with `column_pattern = "customer_id"` and
`value_prefix = "id_"` to your `suppressions.toml`.

### Why is the scanner printing `***` instead of real evidence?

By design. `pii_linter.report.mask_value` only ever produces masked
output. Raw evidence never reaches stdout, stderr, or your terminal.

## Support

- Bug reports / feature requests: open an issue on
  [github.com/angWindy/vn-pii](https://github.com/angWindy/vn-pii).
- For questions, see [docs/architecture.md](architecture.md) and
  [docs/detectors.md](detectors.md) for internals.