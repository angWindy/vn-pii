# CLAUDE.md

> **Context for AI coding assistants** (Claude Code, Cursor, Aider, etc.)
> working on this repository.

## What this project is

PA1 PII Linter is a local-only Python scanner that flags Vietnamese PII
(SĐT, CCCD, CMND, email, card Luhn, VIN/plate, Zalo handle, free-text
blobs) in CSV / JSONL / Markdown datasets. The scanner wraps both
`git commit` (via pre-commit) and AI-agent commands (via
`pa1-lint guard --`).

It is slice-1 MVP: detectors + scanner + guard + suppressions. Out of
scope: cross-file correlation, Presidio, SARIF, PyPI publishing.

## Build & run

The project pins to a dedicated conda env named `pa1` (see
`environment.yml`). **Activate it before running anything:**

```bash
conda activate pa1
```

Common commands:

| Command | Purpose |
|---|---|
| `pip install -e .[dev]` | editable install (CLI entry point `pa1-lint`) |
| `pa1-lint scan fixtures/gold` | scan synthetic gold fixtures |
| `pa1-lint scan path/ --suppressions suppressions.yaml` | scan with suppressions |
| `pa1-lint guard -- <cmd>` | wrap a command with pre/post PII scan |
| `pytest tests/ -v` | run unit + smoke tests |
| `python fixtures/generators/make_synthetic.py --out gold negative` | regenerate fixtures |

## Layout

- `pii_linter/` — Python source. `cli.py` is the entry point (`pa1-lint`).
- `tests/` — pytest suite.
- `fixtures/{gold,negative}/` — synthetic data (Faker, seed=42).
- `examples/pre-commit-config.yaml` — copy-paste into user repos.
- `docs/` — architecture, contributing, detectors, spec, user-guide.
- `.pre-commit-hooks.yaml` — exposed to other repos as a hook.
- `suppressions.yaml` — example suppressions file.
- `.claude/rules/` — workflow rules for AI agents (this file plus others).

## Conventions

- **Dataclasses** for DTOs: `Finding`, `ColumnHint`, `Suppression`,
  `ScanResult` (in `pii_linter/__init__.py`).
- **Mask before printing.** `evidence_raw` is for in-memory use only.
  Reporters render `evidence_masked`.
- **Detectors are dependency-free** (no I/O). The orchestrator is
  `cli._dispatch_value`.
- **Layered:** detectors → orchestrator → reporters. Add a new detector
  by adding `pii_linter/detectors/<name>.py` and wiring it into
  `cli._dispatch_value`.
- **One entity per regex.** Each `Finding.entity` is a key in
  `SEVERITY_BY_ENTITY`.
- **Type hints everywhere** on public functions.

## Safety notes for AI assistants

- Do **not** scan real customer data with `pa1-lint`. The repo only
  contains synthetic fixtures.
- Do **not** commit `fixtures/gold/*.csv` or `fixtures/gold/*.jsonl`
  (they are git-ignored — but if you see them staged, `git restore
  --staged <file>`).
- Do **not** add suppressions for non-synthetic data.
- Do **not** add dependencies to `pyproject.toml` without consulting
  the maintainer.
- When editing a CSV/JSONL file in this repo, run `pa1-lint guard --
  <edit-command>` to make sure no synthetic PII leaks into the wrong
  place.

## Where to look first

| You want to | Read |
|---|---|
| Understand the architecture | `docs/architecture.md` |
| Add a new entity / detector | `docs/contributing.md` |
| Look up a regex / Luhn spec | `docs/detectors.md` |
| Find a public function | `docs/spec.md` |
| Install / troubleshoot | `docs/user-guide.md` |
| The original problem statement | `docs/problem/PA1/PA1.md` |
| AI-agent workflow rules | `AGENTS.md` + `.claude/rules/*.md` |