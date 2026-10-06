# PII Linter

> **🚫 Blocks your commit if HIGH+ PII is staged.**
> Wires `git diff --cached` into a pre-commit hook that scans only the
> lines you are about to commit, shows `file:line | masked_evidence`, and
> blocks the commit on findings.
> See [docs/user-guide.md §Pre-commit hook](docs/user-guide.md#pre-commit-hook).

A local-only pre-commit scanner that flags Vietnamese PII (SĐT, CCCD, CMND,
email, card Luhn, VIN/plate, Zalo handle, free-text blobs) in CSV / JSONL /
Markdown datasets. Designed to wrap both `git` (pre-commit) and AI-agent
commands (Cursor, Aider, Claude Code).

> **Status:** zero-config install. One command sets up the package *and* the
> global git hook, so plain `git commit` blocks PII in any repo with no
> per-repo setup. No runtime dependencies. Python 3.11+ required.
>
> See [docs/spec.md](docs/spec.md) for the public API and
> [docs/problem/PII/PII.md](docs/problem/PII/PII.md) for the original
> problem statement.

## Quick start — Use in any project

```bash
curl -fsSL https://raw.githubusercontent.com/angWindy/vn-pii/main/install.sh | sh
pii-lint path/to/your/dataset
```

The installer picks an isolated environment for you (`pipx`, else a private
venv) and switches on the global git hook, so this is the whole setup. See
[one command, every repo](#quick-start--one-command-every-repo) for what that
enables.

Installing by hand works too, and is the better choice if you want the CLI in
an environment you already manage:

```bash
pipx install git+https://github.com/angWindy/vn-pii   # recommended
# or, inside a venv/conda env you activate yourself:
pip install git+https://github.com/angWindy/vn-pii
```

> **On Debian/Ubuntu, a bare `pip install` into the system Python fails** with
> `error: externally-managed-environment` (PEP 668). It is the OS protecting
> itself, not a bug in this tool — and `--user` does **not** bypass it. Use
> `pipx`, a venv, or the one-liner above. Avoid `--break-system-packages`.

`pii-lint` on its own scans the current directory. `scan` is optional, so
`pii-lint scan <path>` (the older, explicit form) still works identically.

If the console script is not on your `PATH` (no virtualenv, no conda env),
the module entry point is equivalent:

```bash
python -m pii_linter path/to/your/dataset
```

Suppressions:

```bash
pii-lint path/to/your/dataset --suppressions suppressions.toml
```

Note that suppressions do **not** apply to the git hook, which scans staged
diff lines and has no column context to match `column_pattern` against. See
[They do not apply to the git hook](docs/user-guide.md#they-do-not-apply-to-the-git-hook).

And as a plain library call:

```python
from pii_linter import scan

result = scan("path/to/your/dataset")
print(len(result.findings))
```

The tool pulls **zero** extra packages because the suppressions loader uses
Python 3.11's stdlib `tomllib`.

## Quick start — Contributor

```bash
git clone https://github.com/angWindy/vn-pii
cd vn-pii
pip install -e .[dev]
python fixtures/generators/make_synthetic.py --out gold negative
pii-lint fixtures/gold
pytest tests/
```

The optional `[dev]` extra pulls `Faker` (for the fixture generator) and
`pytest`. They are not part of the runtime footprint.

## Quick start — one command, every repo

```bash
curl -fsSL https://raw.githubusercontent.com/angWindy/vn-pii/main/install.sh | sh
```

That installs the package and switches on a global git hook. There is no
per-repo step: from then on, in any repository on the machine,

```bash
git add data.csv && git commit -m "add Q4 rows"
```

scans the staged lines and **blocks the commit** if it contains HIGH or
CRITICAL PII, printing a masked report to your terminal. Nothing to run,
nothing to configure, nothing to remember.

Prefer two steps? Same result:

```bash
pipx install git+https://github.com/angWindy/vn-pii   # or: pip install ...
pii-lint init                                          # install the global hook
```

| Command | Effect |
|---|---|
| `pii-lint init` | install the global hook (idempotent; `--dry-run` to preview) |
| `pii-lint uninstall` | remove it and restore your git config |
| `pre-commit install` | per-repo instead, if you use husky or another hook manager |

If `init` refuses because another tool (husky) already owns your hooks
directory, use the pre-commit framework per repo instead: merge
`examples/pre-commit-config.yaml` into your `.pre-commit-config.yaml` and
run `pre-commit install`. That composes with your existing hooks instead
of competing for `core.hooksPath`. Full steps in
[docs/user-guide.md](docs/user-guide.md#if-you-use-husky-or-another-hook-manager).

To wrap an AI agent command:

```bash
pii-lint guard -- aider --message "summarise repo"
```

## Quick start — Editor & AI agent integration

The global git hook fires from any `git commit` invocation, including
the **Source Control** panel in VSCode and the **Git** panel in Cursor
*when they shell out to the git CLI*. Pure libgit2 commit paths used
by some IDE integrations do not run hooks — for those, prefer the
integrated terminal or use one of the AI agent hooks below.

Native AI agent hooks let the agent **stop its own tool call** when it
detects HIGH+ PII — no user report to read, no manual redaction.

```bash
# User-wide (one command covers every project you ever work on):
pii-lint install-hooks all

# Per-project (recommended for project-specific configs):
cd /path/to/project
pii-lint install-hooks claude-code --project
pii-lint install-hooks codex --project
```

Supported agents: `claude-code`, `cursor`, `cody`, `codex`, `aider`,
`opencode`, `gemini`, `zed`, `antigravity`, `qwen`, `hermes`,
`openclaw`, `kimi`, `codebuddy`, `joycode`, `copilot`.
Claude Code uses `PreToolUse` + `PostToolUse` + `Stop`; Codex uses
`notify` (it has no PreToolUse). See
[docs/user-guide.md §Coding-agent hooks](docs/user-guide.md#coding-agent-hooks-claude-code-cursor-cody-codex-)
for the full list and per-agent behaviour.

## Layout

| Path | Purpose |
|---|---|
| `pii_linter/` | Python package (entry point: `pii-lint`) |
| `tests/` | pytest suite (unit + smoke) |
| `fixtures/` | synthetic CSVs/JSONL generated by Faker |
| `examples/` | copy-paste configs |
| `docs/` | architecture, contributing, detectors, spec, user-guide |
| `.pre-commit-hooks.yaml` | hook defs exposed to other repos |
| `suppressions.toml` | example suppressions file (TOML) |
| `AGENTS.md`, `.claude/rules/` | AI-agent onboarding (ECC) |

## Documentation

- [docs/architecture.md](docs/architecture.md) — system layout + data flow
- [docs/contributing.md](docs/contributing.md) — add a new detector or entity
- [docs/detectors.md](docs/detectors.md) — regex / Luhn reference
- [docs/spec.md](docs/spec.md) — public API + exit codes + TOML schema
- [docs/user-guide.md](docs/user-guide.md) — install, suppressions, FAQ
- [docs/problem/PII/PII.md](docs/problem/PII/PII.md) — original problem statement

## Safety

- **All fixtures are synthetic.** Do not point `pii-lint` at real
  customer data; the report intentionally shows masked evidence but the
  scan keeps raw evidence in memory.
- **Never suppress real customer data.** Suppressions exist for clearly
  synthetic prefixes (`id_`, `dummy_`, `test_`, `example`). Padding a
  number with zeros is not one of them — the regex only checks shape, so
  a zero-padded ten-digit string still trips the phone regex at CRITICAL
  and a zero-padded twelve-digit string still trips the CCCD regex.

## License

MIT. See [pyproject.toml](pyproject.toml).