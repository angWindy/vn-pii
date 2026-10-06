# User guide

PA1 PII Linter ships as a zero-dependency Python package plus a CLI entry
point. One command installs it and switches on a git hook that covers every
repository on your machine — after that, a plain `git commit` blocks PII
with no per-repo setup.

## Install

### The one command

```bash
curl -fsSL https://raw.githubusercontent.com/angWindy/vn-pii/main/install.sh | sh
```

This picks a Python 3.11+ interpreter, installs the package with `pipx`
(falling back to `pip`), and runs `pa1-lint init` to install the global git
hook. There is no second step and nothing to do per repo.

Verify:

```bash
python -c "import pii_linter; print(pii_linter.__version__)"   # -> 0.1.0
git config --get core.hooksPath                               # -> ~/.githooks
pa1-lint init --dry-run                                       # what it would write
```

### Doing it in two steps

Identical result, if you would rather control the install:

```bash
pipx install git+https://github.com/angWindy/vn-pii   # or: pip install ...
pa1-lint init
```

`pip install` on its own does **not** enable the hook: pip has no
post-install script mechanism (PEP 660 metadata is written but no code is
executed), so `init` has to be invoked explicitly.

`pipx` is preferred because it keeps the tool out of your project
environments. Any Python 3.11+ env works — a conda env, a virtualenv, or
on macOS/Windows the plain system Python. Zero runtime dependencies.

### If you hit `error: externally-managed-environment`

That error comes from Debian/Ubuntu marking the **system** Python as
externally managed (PEP 668). It is the OS protecting itself; nothing is
wrong with this tool. It applies only to the bare system interpreter, so any
of these is enough — no `--break-system-packages`:

```bash
conda activate pa1                       # a conda env
python3 -m venv .venv && source .venv/bin/activate
pipx install git+https://github.com/angWindy/vn-pii
```

The pre-commit hook below runs `python -m pii_linter`, not the `pa1-lint`
script, so it keeps working from any shell — you do **not** need to activate
an environment before every `git commit`.

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
pa1-lint path/to/dataset --format markdown
pa1-lint path/to/dataset --format json --suppressions suppressions.toml
```

`scan` is optional — `pa1-lint scan <path>` is accepted too, it just spells
out the verb. Run `pa1-lint` with no path to scan the current directory.

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
pa1-lint path/to/dataset --suppressions suppressions.toml
```

### Best practices

- Only suppress columns whose values are clearly synthetic (`id_`,
  `dummy_`, `test_`, `example`).
- Set `expires_at` far in the future but revisit every quarter.
- Never suppress real customer data. If you find yourself needing to,
  the right fix is to remove the data, not silence the scanner.

Note: do not sanitise a number by padding it with zeros. `0000000000`
still matches the PHONE regex and `000000000000` still matches the
CCCD regex, both at CRITICAL, so the commit stays blocked and the data
is now wrong. Use a non-numeric placeholder such as `REDACTED` or
`dummy_<n>`.

### They do not apply to the git hook

`column_pattern` is matched against a CSV **header**, and the hook scans a
staged *diff* — added lines only, with no column context. So a
suppression will usually not match there even though it works for a
whole-file scan. Verify a suppression before you rely on it:

```bash
pa1-lint scan path/to/dataset --suppressions suppressions.toml  # expect 0 findings
```

If you need the hook itself to respect a suppression, the pragmatic
options are to stop putting that value in version control, or to accept
the blocked commit and re-run with `git commit --no-verify` after
confirming the data is genuinely synthetic.

## The git hook (zero-config)

`pa1-lint init` installs one hook that covers **every** repo on the machine.
Run it once, after installing the package:

```bash
pa1-lint init
```

From now on, in any repository, every `git commit` scans the staged lines.
**Only the lines added by your commit are scanned** — pre-existing PII in
lines you did not touch is ignored. The commit is blocked if HIGH or
CRITICAL findings appear.

There is nothing to add to any repo. `init` sets `core.hooksPath` to
`~/.githooks` and writes a `pre-commit` hook there. Because that replaces
git's hook lookup, it also writes passthrough shims for `commit-msg`,
`prepare-commit-msg`, `post-commit` and friends, so hooks a repo already
had keep working.

Preview without touching anything, or remove it again:

```bash
pa1-lint init --dry-run
pa1-lint uninstall
```

### If you use husky or another hook manager

`init` **refuses** to install when the hooks directory already holds a
`pre-commit` it did not write, because overwriting husky's hook would break
every commit in your repos. Use the pre-commit framework per repo instead:

1. Merge [`examples/pre-commit-config.yaml`](../examples/pre-commit-config.yaml)
   into your repo's `.pre-commit-config.yaml` — it only adds a `repos:`
   entry, so keep any prettier/ruff/eslint hooks you already have.
2. `pip install pre-commit && pre-commit install`.

No `pa1-lint` on your `PATH` is required: the hook entry is
`python -m pii_linter`, and `language: python` has pre-commit build a
dedicated environment for it.

### What a blocked commit looks like

```text
$ git add leads.csv
$ git commit -m "Add new leads"

# PA1 PII scan report

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

The commit does not happen. Fix the line, re-stage (`git add leads.csv`),
and commit again.

Note that `evidence_masked` masks the whole cell, so the neighbouring
columns are hidden too — the report never leaks the rest of the row just
to show you one value.

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

## Editor GUI (VSCode, Cursor)

The global `pre-commit` hook fires from any `git commit` invocation
that the OS-level `git` binary handles. In practice:

- **VSCode Source Control** and **Cursor Git** panels *usually* shell
  out to the `git` binary, so the hook runs and the panel reports the
  block. Test in your project: try a commit with a staged `.csv` that
  contains a phone number; the panel should show the PA1 report and
  refuse the commit.
- **Pure libgit2 paths** (some IDE integrations and a few extensions
  do not shell out) bypass hooks entirely. There is no portable fix
  from the tool side — the IDE is making the commit in-process.

Mitigations if the GUI bypasses the hook:

1. Use the **integrated terminal** for the commit — `git commit` from
   inside VSCode/Cursor always goes through the hook.
2. Install the **pre-commit framework** in the repo (see
   [If you use husky or another hook manager](#if-you-use-husky-or-another-hook-manager));
   pre-commit's own hook is installed by the framework and fires
   regardless of how the IDE commits.
3. Install a **Claude Code / Cursor / Cody hook** (next section). The
   agent hook fires on the file write itself, so it blocks even when
   the git hook is bypassed.

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

### What each agent actually does

| Agent | Event | What runs | What it does on HIGH+ |
|---|---|---|---|
| Claude Code | `PreToolUse` (Write/Edit/MultiEdit) | bash script reads tool-call JSON from stdin, scans the file or new bytes | Exit 2 — Claude re-prompts itself to redact *before* the bad bytes are written |
| Claude Code | `PostToolUse` (Write/Edit/MultiEdit) | inline `pa1-lint scan -- $file` | Exit 2 — belt-and-braces if PreToolUse is skipped |
| Claude Code | `Stop` | `pa1-lint scan --staged` | Exit 2 — Claude must clean up before signing off |
| Cursor | `PostToolUse` | inline `pa1-lint scan -- $file` | Exit 2 — Cursor re-prompts to redact |
| Cody | `PostToolUse` | inline `pa1-lint scan -- $file` | Exit 2 — Cody re-prompts to redact |
| Codex CLI | `notify` (end of every turn) | bash script scans `git diff --staged` | Exit 2 — Codex reads output back into the chat, re-prompts on next turn |
| Aider | wrapper | `pa1-lint scan -- <paths>` over files Aider touched | Exit 2 — Aider re-prompts to redact |

The Claude Code `PreToolUse` hook is the strictest: it runs *before*
the file is written, so the agent never lands PII on disk during the
first try. Codex has no `PreToolUse` event, so its `notify` hook is
best-effort: the agent may write PII on the first attempt and only
see the report after the turn ends. If you need pre-write blocking
for Codex, wrap the agent with `pa1-lint guard -- codex ...` instead.

## Using pa1-lint in a downstream project

Imagine you work on `Customer-Analytics` (your own repo) and you want
every CSV / JSONL commit scanned:

```bash
# 1. One-time setup, on your machine - not per repo
curl -fsSL https://raw.githubusercontent.com/angWindy/vn-pii/main/install.sh | sh
```

That is the whole setup. Do **not** copy
`examples/pre-commit-config.yaml` over an existing `.pre-commit-config.yaml`:
`mv` overwrites without asking, and you would lose every prettier / ruff /
eslint hook you already had. If you use the pre-commit framework, merge the
`repos:` entry in by hand instead.

A per-project `suppressions.toml` is **not** read by the hook. To use it,
pass it explicitly — the hook runs a fixed command with no arguments:

```bash
pa1-lint scan --staged --suppressions suppressions.toml   # manual run
```

This is a real limitation, not an oversight. In staged-diff mode the
scanner sees added *lines*, not CSV cells, so it has no column name to
match `column_pattern` against — the header row is usually not even part
of the commit. Suppressions that key on a column therefore only take
effect in a whole-file scan:

```bash
pa1-lint path/to/dataset --suppressions suppressions.toml   # works
```

The suppression file itself:

```toml
[[suppressions]]
column_pattern = "internal_id"
value_prefix = "id_"
owner = "data-eng"
expires_at = 2027-12-31
reason = "Synthetic IDs generated by our Faker factory."
```

Then just commit:

```bash
git add data.csv
git commit -m "Add Q4 customer dataset"   # blocked if HIGH+ findings
```

## Troubleshooting

### `error: externally-managed-environment`

Ubuntu/Debian mark the **system** Python as externally managed (PEP 668), so
`pip` refuses to install into it. Nothing is wrong with this tool — install
into an environment you own:

```bash
conda activate pa1
# or: python3 -m venv .venv && source .venv/bin/activate
pip install git+https://github.com/angWindy/vn-pii
```

Avoid `--break-system-packages`; it can break `apt` and the OS Python.

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

If you cannot or do not want to fix `PATH`, run the module directly — it
is the same program and returns the same exit codes:

```bash
python -m pii_linter path/to/dataset
```

### `Python 3.11 or newer is required`

Slice 2 bumped the Python floor to 3.11 because `tomllib` is in stdlib
from 3.11. Use `python3.11`, `python3.12`, `python3.13` or newer:

```bash
python3.11 -m pip install git+https://github.com/angWindy/vn-pii
```

### The hook does not run on commit

The hook fires from the **global** install, not from a per-repo
`.pre-commit-config.yaml`, so check these first:

```bash
pa1-lint init --dry-run     # shows the hooks dir and core.hooksPath
git config --get core.hooksPath
```

| Symptom | Cause | Fix |
|---|---|---|
| No hook at all, `core.hooksPath` empty | never ran `init` | `pa1-lint init` |
| `pa1-lint: resolver missing ... the PII scan did NOT run` | the resolver script got deleted; the hook can't run without it | `pa1-lint init` to regenerate |
| `pa1-lint: no Python interpreter with pa1_linter installed was found` | resolver ran but no conda env / venv / PATH python has pa1-lint installed (e.g. you deleted the only env that had it) | install pa1-lint into any env, then commit again; bypass once with `git commit --no-verify` |
| `REFUSED: ... was not written by pa1-lint` | husky or another manager owns that dir | merge [`examples/pre-commit-config.yaml`](../examples/pre-commit-config.yaml) and run `pre-commit install` (see above) |
| Hook runs but a repo's own `commit-msg` stopped | a shim was deleted by hand | `pa1-lint init` rewrites the shims |

Bypass once with `git commit --no-verify` if you are mid-rebase and cannot
fix the hook right now.

If you deliberately use the pre-commit framework instead (the husky case
above), its own hook is configured by `.pre-commit-config.yaml` and runs
with `language: python`, so it needs nothing on your `PATH`:

```bash
pre-commit run pa1-lint-staged --hook-stage pre-commit   # test without committing
```

Note that if `core.hooksPath` is set (by `init` or by husky), the
pre-commit framework's own `.git/hooks/pre-commit` is **not** consulted.
That is expected: only the hooks directory git is pointed at runs.

### Why is the staged report different from the full report?

`pa1-lint scan --staged` only scans the lines introduced by your commit.
`pa1-lint scan path/to/dataset` reads the whole file from disk. Same
detectors, same exit codes — only the input scope differs.

### False positive on `customer_id` containing `id_001`

Add a suppression entry with `column_pattern = "customer_id"` and
`value_prefix = "id_"` to your `suppressions.toml`.

Note that this only works for a whole-file scan. The `git commit` hook
scans a staged diff and has no column to match against, so the commit
will still be blocked — see
[They do not apply to the git hook](#they-do-not-apply-to-the-git-hook).

### Why is the scanner printing `***` instead of real evidence?

By design. `pii_linter.report.mask_value` only ever produces masked
output. Raw evidence never reaches stdout, stderr, or your terminal.

## Support

- Bug reports / feature requests: open an issue on
  [github.com/angWindy/vn-pii](https://github.com/angWindy/vn-pii).
- For questions, see [docs/architecture.md](architecture.md) and
  [docs/detectors.md](detectors.md) for internals.