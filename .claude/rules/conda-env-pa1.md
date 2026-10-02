# Conda env `pa1` — required for PA1 tooling

PA1 PII Linter enforces a fail-fast check at startup (see
`pii_linter/cli._in_pa1_env`). The scanner refuses to run if
`sys.prefix` does not contain `pa1`.

## Trigger

This rule applies whenever an AI agent is about to:

- Run `pa1-lint ...`
- Run `pytest tests/`
- Run `python fixtures/generators/make_synthetic.py ...`
- Run any script in `pii_linter/`

## Action

Before the command, ensure the active Python is `pa1`:

```bash
source ~/miniconda3/etc/profile.d/conda.sh && conda activate pa1
```

If `conda activate` is not possible, use the absolute Python interpreter:

```bash
~/miniconda3/envs/pa1/bin/python -m pa1_linter.cli scan <path>
```

## Verify

`which python` should print a path under `~/miniconda3/envs/pa1/`.

## Why

- The conda env pins `pyyaml`, `Faker`, `pandas`, `pytest` to known-good
  versions.
- Running from the system Python produces unpredictable results and
  bypasses the version checks the scanner depends on.
- The fail-fast check (`exit 3`) makes it obvious when you forgot to
  activate.