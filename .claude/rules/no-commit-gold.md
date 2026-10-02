# No commit of `fixtures/gold/*`

PII are synthetic but should never enter the version control history.
This repo `.gitignore`s `fixtures/gold/*.csv` and
`fixtures/gold/*.jsonl`. The rule is here so AI agents do not
accidentally try to `git add` them.

## Trigger

This rule applies whenever an AI agent is about to:

- Run `git add ...`
- Run `git commit ...`
- Suggest a `git` command that would stage PII fixture files

## What counts as PII fixture

- `fixtures/gold/leads_50.csv`
- `fixtures/gold/contracts_50.csv`
- `fixtures/gold/service_50.csv`
- `fixtures/gold/finance_50.csv`
- `fixtures/gold/notes_50.jsonl`

## Action

If you ever see these files in `git status` as staged, run:

```bash
git restore --staged fixtures/gold/*.csv fixtures/gold/*.jsonl
```

Do **not** commit them, do **not** `git push`, and do **not** suggest
workarounds that would weaken `.gitignore`.

## Allowed (committed) fixtures live in `fixtures/negative/`

`fixtures/negative/crm_pipeline_50.csv` and `aggregate_50.csv` are
**intended** to be committed. They contain only clearly-synthetic
prefixes (`id_`, `dummy_`, `0`) and are the test corpus for
`tests/test_smoke.py`.

If you need a non-secret sample dataset for testing in another repo,
copy from `fixtures/negative/` or regenerate fresh fixtures with:

```bash
python fixtures/generators/make_synthetic.py --out negative
```

## Why

- Even synthetic PII in version control trains the wrong muscle.
- A new contributor cloning the repo will not see them, leading to
  broken `tests/test_smoke.py` because the gold corpus is gone.
- Suppressions inside `suppressions.yaml` rely on the `id_` prefix; if
  the gold corpus is leaked, false-positive testing gets easier.