# INDEX.md — Navigation for AI agents

> **This file is the entry point.** A new agent entering this repo (Cursor / Aider / Claude Code) reads this file first to understand the context.
>
> Reading order: `INDEX.md` (this) → `AGENTS.md` → `PLAN.md` → `Worklog/INDEX.md` → topical docs under `docs/`.

## Overall repo flow (mermaid)

```mermaid
flowchart TD
    User([User / Maintainer]) --> AGENTS[AGENTS.md<br/>workflow rules]
    User --> INDEX[INDEX.md<br/>this file]

    INDEX --> PLAN[PLAN.md<br/>goal + scope]
    INDEX --> WORKLOG[Worklog/INDEX.md<br/>bug-fix / decision catalog]
    INDEX --> AGENTS
    INDEX --> DOCS[docs/<br/>architecture · contributing · detectors · spec · user-guide]
    INDEX --> SRC[pii_linter/<br/>main package]
    INDEX --> TESTS[tests/<br/>pytest suite]
    INDEX --> FIX[fixtures/{gold,negative}/<br/>]

    AGENTS --> RULES[.claude/rules/<br/>pii-guard · no-commit-gold · conda-env-pii]
    PLAN --> CURSOR[(docs/PLAN.md<br/>design decisions<br/>+ slices)]

    SRC --> CLI[cli.py · guard.py]
    CLI --> DET[detectors/<br/>column_name · content_regex · luhn_card · free_text]
    CLI --> RPT[report.py]
    CLI --> SEV[severity.py]
    CLI --> SP2[suppressions.py]

    DOCS --> PROBLEM[docs/problem/PII/PII.md<br/>original problem + side.md]
    FIX --> GOLD[fixtures/gold/<br/>gitignored]
    FIX --> NEG[fixtures/negative/<br/>tracked in git]
```

## Task-to-file mapping

| Agent needs | Read |
|---|---|
| Understand what the project does and its scope | [`PLAN.md`](PLAN.md) |
| Workflow rules (env, guard, no committing gold, ...) | [`AGENTS.md`](AGENTS.md) |
| What bugs were fixed, which decisions were made | [`Worklog/INDEX.md`](Worklog/INDEX.md) |
| What the latest session changed | The newest file inside `Worklog/` |
| Understand package architecture and data flow | [`docs/architecture.md`](docs/architecture.md) |
| How to add a new detector / entity | [`docs/contributing.md`](docs/contributing.md) |
| Regex + Luhn spec | [`docs/detectors.md`](docs/detectors.md) |
| Public API + CLI flags + exit codes | [`docs/spec.md`](docs/spec.md) |
| Install / suppressions / pre-commit / FAQ | [`docs/user-guide.md`](docs/user-guide.md) |
| Original problem statement | [`docs/problem/PII/PII.md`](docs/problem/PII/PII.md) |
| Code entry point | `pii_linter/cli.py` |
| Add a detector | `pii_linter/detectors/<name>.py` + update `severity.py` |
| Severity table | `pii_linter/severity.py` `SEVERITY_BY_ENTITY` |
| Suppressions format | `suppressions.toml` + `pii_linter/suppressions.py` (TOML via stdlib tomllib) |
| Tests | `tests/test_*.py` |

## Reading rules (for a new agent)

1. **Required reading before any code change:**
   - `AGENTS.md` (once)
   - The newest `Worklog/` entry whose date is today or earlier
2. **Read on demand:** topical docs — only read them when the task is in that area (for example, adding a new detector → read `docs/contributing.md`).
3. **Create a worklog entry after the work is done:** every session appends one file under `Worklog/` plus one row in `Worklog/INDEX.md`.
4. **Never touch `fixtures/gold/`** (git-ignored; it stays local, never commit).

## Change rules

| Before you change | You must |
|---|---|
| Edit a `.csv` / `.jsonl` / `.md` outside `fixtures/negative/` | Wrap with `pii-lint guard -- <edit-cmd>` |
| Run `pii-lint` / `pytest` / any `fixtures/generators/` script | No env required — tool runs in any Python 3.11+ |
| Stage a file inside `fixtures/gold/` | `git restore --staged <file>` |
| Add a new detector / entity | Add a key to `SEVERITY_BY_ENTITY` and a test in `tests/test_<name>.py` |
| Add a dependency to `pyproject.toml` | Ask the user first |
| Commit | Create a worklog entry first |

## External links

- Design decisions, architecture, slices: [`docs/PLAN.md`](docs/PLAN.md)