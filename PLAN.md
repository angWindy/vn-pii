# PLAN.md — PA1 PII Linter (Slices 1–2)

> This file is the **single source of truth** for project goal and scope.
> Detailed history and design decisions: [docs/PLAN.md](docs/PLAN.md).
> Session log: [Worklog/INDEX.md](Worklog/INDEX.md).

## Goal

Provide a Vietnamese PII scanner that runs **locally with no external service dependency** and can:

1. **Pre-commit gate**: block CSV/JSONL/Markdown that contain Vietnamese PII before it lands in a repo.
2. **AI-agent wrapper**: block an AI agent tool call if it would introduce or leak PII.

## Slice 1 scope (MVP)

| Component | Description |
|---|---|
| Entities | `PHONE`, `ID_NUMBER` (CCCD/CMND), `EMAIL`, `CARD_NO` (Luhn), `ASSET` (VIN/plate), `URL_HANDLE` (zalo.me), `NOTE` (free-text combo), `PERSON` (column hint) |
| Detectors | `column_name`, `content_regex`, `luhn_card`, `free_text` |
| File formats | `.csv`, `.jsonl`, `.md` (table) |
| CLI | `pa1-lint scan <path>`, `pa1-lint guard -- <cmd>` |
| Output | Markdown (default) or JSON |
| Severity | LOW / MEDIUM / HIGH / CRITICAL + exit code 0/1/2/3 |
| Suppressions | YAML with `column_pattern`, `value_prefix`, `owner`, `expires_at` |
| Pre-commit | `.pre-commit-hooks.yaml` at root, copy-paste via `examples/` |
| Env | `pa1` conda env (Python 3.11) |

## Out of scope (Slice 1 does **not** include)

- Cross-file correlation
- Presidio integration
- SARIF / GitHub Action output
- Precision/recall evaluation
- PyPI / conda-forge publishing
- First-party wrappers for Cursor / Aider / Claude Code (slice 1 ships only `pa1-lint guard`)

## Target directory layout

```
vn-pii/
├── PLAN.md                   ← this file: goal + scope + out-of-scope
├── INDEX.md                  ← navigation graph for AI agents
├── AGENTS.md                 ← workflow rules for AI agents
├── README.md                 ← two personas (contributor / user)
├── pyproject.toml            ← package metadata + entry point `pa1-lint`
├── environment.yml           ← conda env `pa1`, Python 3.11
├── .pre-commit-hooks.yaml    ← hook definition consumed by other repos
├── suppressions.toml         ← example suppressions file (Slice 2; zero runtime dep)
├── pii_linter/               ← main package
├── tests/                    ← pytest suite
├── fixtures/{gold,negative}/ ← synthetic data (gold is git-ignored)
├── Worklog/                  ← one file per session; bug fixes and decisions
├── docs/                     ← architecture, contributing, detectors, spec, user-guide, problem
└── .claude/rules/            ← auto-applied rules per file type
```

## Slice 1 completion criteria

- [x] `pa1-lint --version` prints `0.1.0` inside the `pa1` env
- [x] `pa1-lint scan fixtures/gold/leads_50.csv` → exit 1, at least one PHONE finding
- [x] `pa1-lint scan fixtures/negative/aggregate_50.csv` → exit 0, zero findings
- [x] `pa1-lint scan fixtures/gold/notes_50.jsonl` → exit 2 (CRITICAL), at least one CARD_NO
- [x] `pytest tests/` passes all tests
- [x] `.pre-commit-hooks.yaml` is parseable
- [x] Five docs files + `docs/problem/PA1/PA1.md` exist
- [x] `AGENTS.md` + three `.claude/rules/` files exist

## How to use PLAN.md

| You want to | Read |
|---|---|
| Understand where the project is heading | This file + [docs/PLAN.md](docs/PLAN.md) |
| Design decisions, architecture, regex reference | [docs/PLAN.md](docs/PLAN.md) |
| See what was fixed and at which session | [Worklog/INDEX.md](Worklog/INDEX.md) |