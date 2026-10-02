# User guide

PA1 PII Linter ships as a Python package plus a CLI entry point. You can
use it two different ways: as a **pre-commit hook** (recommended for any
project that touches CSV / JSONL data) or as a **wrapper** around an AI
agent command.

## Install

### Contributor (this repo)

```bash
conda env create -f environment.yml && conda activate pa1
pip install -e .[dev]
```

### End user (your own dataset)

```bash
conda create -n pa1 python=3.10 -y
conda activate pa1
pip install -e /path/to/this/repo        # until PyPI is up, install from source
# or: pip install pa1-pii-linter        # once published
```

Verify:

```bash
pa1-lint --help
```

## Run a one-off scan

```bash
pa1-lint scan path/to/dataset --format markdown
pa1-lint scan path/to/dataset --format json --suppressions suppressions.yaml
```

JSON is easier to wire into CI dashboards. Markdown is preferred when you
want a human-readable report.

## Pre-commit hook

1. Copy `examples/pre-commit-config.yaml` into your repo as
   `.pre-commit-config.yaml`.
2. Make sure `pa1-lint` is installed in the active Python env
   (`conda activate pa1`).
3. Install pre-commit:

    ```bash
    pip install pre-commit
    pre-commit install
    ```

From now on, every `git commit` that touches `.csv` / `.jsonl` /
`.markdown` files runs `pa1-lint scan` on the staged content. The commit
is blocked if HIGH or CRITICAL findings appear.

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

1. Snapshots `git diff HEAD` (added text).
2. Scans that text. If HIGH+ findings exist, the command is not run and
   the wrapper exits `2`.
3. Runs the wrapped command.
4. Re-scans `git diff HEAD`. If new HIGH+ findings appeared, exits `2`.

This is meant to be wired into your shell alias:

```bash
alias aider-safe="pa1-lint guard -- aider"
```

## Suppressions

Create a `suppressions.yaml` in your repo:

```yaml
suppressions:
  - column_pattern: customer_id
    value_prefix: "id_"
    owner: synth-data-team
    expires_at: 2027-12-31
    reason: Faker seed 42; verified by /tests/test_smoke.py
```

Pass it to the scan:

```bash
pa1-lint scan path/to/dataset --suppressions suppressions.yaml
```

### Best practices

- Only suppress columns whose values are clearly synthetic (`id_`,
  `dummy_`, `0`-padded accounts).
- Set `expires_at` far in the future but revisit every quarter.
- Never suppress real customer data. If you find yourself needing to,
  the right fix is to remove the data, not silence the scanner.

## Troubleshooting

### `pa1-lint: command not found`

The `pa1-lint` script is installed by `pip install -e .`. Make sure you
ran that step **inside** the `pa1` conda env:

```bash
conda activate pa1
pip install -e /path/to/this/repo
```

### `pa1-lint: not running in conda env 'pa1'. Activate it first:  conda activate pa1`

This is the env check from
[`cli._in_pa1_env()`](../pii_linter/cli.py). Run:

```bash
conda activate pa1
pa1-lint scan path/to/dataset
```

If you intentionally want to bypass it (e.g. you have a different env
name), edit `_in_pa1_env` to whitelist your env name.

### Pre-commit hook does not run

Make sure `core.hooksPath` is empty (or `.git/hooks`):

```bash
git config --get core.hooksPath    # should be empty / unset
```

If you set `core.hooksPath` to a custom directory, the pre-commit
framework will look there instead.

### False positive on `customer_id` containing `id_001`

Add a suppression entry with `column_pattern: customer_id` and
`value_prefix: "id_"`.

### Why is the scanner printing `***` instead of real evidence?

By design. `pii_linter.report.mask_value` only ever produces masked
output. Raw evidence never reaches stdout, stderr, or your terminal.

## Support

- Bug reports / feature requests: open an issue on this repo.
- For questions, see [docs/architecture.md](architecture.md) and
  [docs/detectors.md](detectors.md) for internals.