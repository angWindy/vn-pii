---
name: PA1 PII Linter Slice 2 (zero-dep distribution)
overview: Drop the runtime pyyaml dependency by switching suppressions to TOML (stdlib tomllib), bump Python floor to 3.11, remove the conda-env 'pa1' enforcement, add a `pip install git+...vn-pii` install path, and rewrite user-facing docs so any project can adopt the tool with a single `pip install` and zero extra packages.
todos:
  - id: code-suppressions-toml
    content: pii_linter/suppressions.py: replace 'import yaml' + 'yaml.safe_load' with 'tomllib.load'; switch load_suppressions() to consume suppressions.toml. Keep the same Suppression dataclass + matches() so public surface is unchanged.
    status: pending
  - id: code-cli-env-drop
    content: pii_linter/cli.py: remove _in_pa1_env() and the exit-3 branch in main(); tool now runs in any Python >= 3.11.
    status: pending
  - id: code-pyproject-bump
    content: pyproject.toml: requires-python '>=3.11'; dependencies []; add [project.urls] Homepage/Repository.
    status: pending
  - id: code-suppressions-toml-sample
    content: Create suppressions.toml at repo root with the same 3 example entries (customer_id / phone / account_no).
    status: pending
  - id: code-remove-yaml
    content: Delete suppressions.yaml (replaced by .toml).
    status: pending
  - id: tests-suppressions-toml
    content: tests/test_suppressions.py: update fixtures to use suppressions.toml; add one positive + one negative test for the TOML loader.
    status: pending
  - id: doc-readme-rewrite
    content: README.md: rewrite 'Quick start - End user' section around 'pip install git+https://github.com/anthang2003/vn-pii'; add a 'Use in any project' persona; drop references to conda env 'pa1'.
    status: pending
  - id: doc-user-guide-rewrite
    content: docs/user-guide.md: rewrite Install section for the new single-pip-install flow; update Troubleshooting (no more 'conda activate pa1' entries); add a 'Using pa1-lint in a downstream project' section.
    status: pending
  - id: doc-spec-update
    content: docs/spec.md: Python >= 3.11 (was 3.10); add a 'Suppressions file format' section describing the TOML schema.
    status: pending
  - id: doc-contributing-update
    content: docs/contributing.md: update 'Add a new suppression field' to reference the TOML schema; update 'Commit checklist' to mention .toml.
    status: pending
  - id: doc-architecture-update
    content: docs/architecture.md: update 'Why a conda env?' section to explain why Slice 2 dropped the env enforcement; update the dependency tree diagram.
    status: pending
  - id: worklog-slice-2-entry
    content: Worklog/2026-10-02_zero-dep-slice-2.md: new entry describing the user request, the four decisions (TOML, >=3.11, drop env check, pip install git), the code/doc changes, and the acceptance criteria for Slice 2.
    status: pending
  - id: plan-update
    content: Update PLAN.md to add 'Slice 2' section: 'Goal: zero runtime dependency, single pip install'. Cross-link to this plan snapshot.
    status: pending
isProject: false
---

# PA1 PII Linter — Slice 2 (zero-dep distribution)

## Why Slice 2

Slice 1 ships a working scanner, yet installation is awkward for end users:
- `pyyaml` is a runtime dependency.
- The CLI refuses to run unless the `pa1` conda env is active.
- The only install story is "clone this repo and `pip install -e .`".

User direction (2026-10-02): *"I want users to use my tool in any project with the
fewest library dependencies."* This slice drops the runtime dependency
altogether and ships a single `pip install` story.

## Decisions (locked)

| Topic | Decision | Rationale |
|---|---|---|
| Suppressions format | TOML (`suppressions.toml`) | `tomllib` is in stdlib from 3.11; format is comment-friendly; already standard for Python tooling. |
| Python floor | `>=3.11` | tomllib has been in stdlib since 3.11. Drops 3.10. |
| Runtime dependencies | `[]` | New pyproject entry: no runtime deps. |
| Env enforcement | Removed | `_in_pa1_env()` and the `exit 3` branch are deleted. Tool runs in any Python. |
| Distribution | `pip install git+https://github.com/anthang2003/vn-pii` | One-command install; no clone needed for end users. |
| Pre-commit hook | Unchanged (`.pre-commit-hooks.yaml`) | Already correct UX. |

## Code changes (3 files)

### `pii_linter/suppressions.py`

- Remove `import yaml`.
- Add `import tomllib` (Python 3.11+).
- `load_suppressions(path)` opens in binary mode and calls `tomllib.load`.
- `Suppression` dataclass and `matches()` are unchanged.
- Errors are wrapped in the same `ValueError` shape so callers do not change.

```python
import tomllib
...
def load_suppressions(path):
    p = Path(path)
    if not p.exists():
        return []
    with p.open("rb") as fh:
        raw = tomllib.load(fh) or {}
    entries = raw.get("suppressions", [])
    ...
```

### `pii_linter/cli.py`

- Delete `_in_pa1_env()`.
- Delete the `_env_fail()` writer.
- `main()` no longer returns 3 for a wrong env; it just runs.

### `pyproject.toml`

```toml
requires-python = ">=3.11"
dependencies = []

[project.urls]
Homepage = "https://github.com/anthang2003/vn-pii"
Repository = "https://github.com/anthang2003/vn-pii"

[project.optional-dependencies]
dev = ["Faker>=30.0", "pytest>=8.0"]
# pandas removed from [dev]; nothing in the runtime path ever imported it.
```

## Sample file: `suppressions.toml`

```toml
# Suppressions for the synthetic gold fixtures in this repo.
# End users should keep this file next to their dataset; the format is
# stable and documented in docs/spec.md.

[[suppressions]]
column_pattern = "customer_id"
value_prefix = "id_"
owner = "synth-data-team"
expires_at = 2027-12-31
reason = "Faker seed 42; verified by tests/test_smoke.py"

[[suppressions]]
column_pattern = "phone|email"
value_prefix = "dummy"
owner = "synth-data-team"
expires_at = 2027-12-31
reason = "Faker seed 42; values look real but are dummy."

[[suppressions]]
column_pattern = "account_no"
value_prefix = "0"
owner = "synth-data-team"
expires_at = 2027-12-31
reason = "0-padded accounts are seed values."
```

## Test updates

`tests/test_suppressions.py`:

- Replace YAML fixtures with TOML fixtures.
- Add `test_load_toml_returns_empty_when_missing` (positive).
- Add `test_load_toml_parses_three_entries` (positive).
- Add `test_load_toml_raises_on_malformed_entry` (negative).
- Existing `test_matches_*` cases still pass because `Suppression.matches()` is untouched.

## Doc changes (5 files)

### `README.md`

Rewrite the "Quick start - End user" persona around:

```bash
pip install git+https://github.com/anthang2003/vn-pii
pa1-lint scan path/to/dataset
```

Add a third persona "Use in any project" that walks through wiring the
pre-commit hook into a downstream repo.

Remove all `conda activate pa1` lines.

### `docs/user-guide.md`

- New "Install" section with the single-command `pip install`.
- New "Using pa1-lint in a downstream project" section.
- Drop the "conda activate pa1" troubleshooting entries.
- Keep all other sections (Run, Suppressions, Pre-commit, FAQ).

### `docs/spec.md`

- Update `Python: >= 3.11` (was 3.10).
- New "Suppressions file format" section with the TOML schema and a
  minimal example.
- Update the public-API table to mention TOML loader.

### `docs/contributing.md`

- Update "Add a new suppression field" to reference the TOML schema and
  `tomllib.load` rather than `yaml.safe_load`.
- Drop the "wrap with conda activate" rule.

### `docs/architecture.md`

- Rewrite "Why a conda env?" → "Why a Python 3.11 floor?".
- Update the dependency diagram to show `[]` runtime and only stdlib
  imports in `pii_linter/`.

## Plan tracking

- New `Worklog/2026-10-02_zero-dep-slice-2.md` entry describes this slice.
- `PLAN.md` adds a "Slice 2" section with goal, scope, and the new
  completion criteria.

## Slice 2 completion criteria

- [ ] `pip install git+https://github.com/anthang2003/vn-pii` installs into a clean Python 3.11+ env with **no** extra packages pulled in.
- [ ] `pa1-lint --version` works without `conda activate pa1`.
- [ ] `pa1-lint scan some.csv` works without `pa1` env, has no `ImportError: yaml`.
- [ ] `pa1-lint scan some.csv --suppressions suppressions.toml` loads TOML correctly.
- [ ] `pytest tests/` passes (including the new TOML loader tests).
- [ ] `docs/spec.md` documents the TOML schema and `>=3.11` floor.
- [ ] `docs/user-guide.md` shows the single-pip-install path.
- [ ] `README.md` no longer references `conda activate pa1`.

## Out of scope (slice 2)

- PyPI publishing.
- Pre-built wheels / GitHub Action.
- Lock-file (`pip freeze`) regression test in CI.