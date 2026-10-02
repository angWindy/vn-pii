# Public spec

This is the contract of PA1 PII Linter slice 1. Anything not listed here
is implementation detail and may change.

## Package

- **Name:** `pa1-pii-linter`
- **Version:** `0.1.0` (see `pii_linter.__version__`)
- **License:** MIT (see `pyproject.toml`)
- **Python:** `>= 3.11` (stdlib `tomllib` is required for `suppressions.toml`)
- **Runtime dependencies:** `[]` (zero)
- **Install:** `pip install git+https://github.com/anthang2003/vn-pii`

## Public dataclasses (in `pii_linter`)

### `Finding`

```python
@dataclass(frozen=True)
class Finding:
    entity: str                # one of SEVERITY_BY_ENTITY keys
    severity: int              # 1=LOW, 2=MEDIUM, 3=HIGH, 4=CRITICAL
    evidence_raw: str          # matched slice; NEVER printed by reporters
    evidence_masked: str       # display-safe form (see report.mask_value)
    span: tuple[int, int] | None
```

### `ColumnHint`

```python
@dataclass(frozen=True)
class ColumnHint:
    entity: str
    severity: int              # baseline severity from SEVERITY_BY_ENTITY
```

### `ScanResult`

```python
@dataclass
class ScanResult:
    findings: list[Finding]
    files_scanned: int
    by_file: dict[str, list[Finding]]  # path -> findings
```

### `Suppression`

```python
@dataclass(frozen=True)
class Suppression:
    column_pattern: str        # regex (case-insensitive)
    value_prefix: str          # literal string
    owner: str
    expires_at: datetime.date
    reason: str
```

## Severity scale

| Name | Code | Exit | Examples |
|---|---|---|---|
| LOW | 1 | 0 | — |
| MEDIUM | 2 | 0 | EMAIL, ASSET, NOTE, URL_HANDLE |
| HIGH | 3 | 1 | PHONE, ID_NUMBER, ACCOUNT_NO, PERSON |
| CRITICAL | 4 | 2 | CARD_NO |

`SEVERITY_BY_ENTITY` lives in [`pii_linter/severity.py`](../pii_linter/severity.py)
and is the single source of truth.

## Public functions

| Function | Where | Purpose |
|---|---|---|
| `score_column(name)` | `pii_linter.detectors.column_name` | Map header → hints |
| `scan_value(value, hints)` | `pii_linter.detectors.content_regex` | Run regex set |
| `luhn_check(pan)` | `pii_linter.detectors.luhn_card` | Luhn checksum |
| `detect_card(value)` | `pii_linter.detectors.luhn_card` | Find one Luhn+PAN |
| `scan(value, hints)` | `pii_linter.detectors.free_text` | Combo-boost rule |
| `mask_value(value, entity)` | `pii_linter.report` | Per-entity masker |
| `render_markdown(result)` | `pii_linter.report` | Markdown reporter |
| `load_suppressions(path)` | `pii_linter.suppressions` | YAML loader |
| `is_suppressed(col, value, sups)` | `pii_linter.suppressions` | Match predicate |
| `scan_path(root, suppressions_path)` | `pii_linter.cli` | End-to-end scan |
| `run(cmd)` | `pii_linter.guard` | Pre/post-scan wrapper |

## CLI

### `pa1-lint scan <path> [--format {markdown,json}] [--suppressions PATH]`

- Recursively walks `<path>` for `.csv`, `.jsonl`, `.md` up to depth 3.
- Loads `suppressions.toml` from `--suppressions PATH` (default: none).
- Prints Markdown (default) or JSON to stdout.
- Exit code:
  - `0` — no HIGH+ findings
  - `1` — at least one HIGH finding
  - `2` — at least one CRITICAL finding

### `pa1-lint guard -- <cmd> [<args>...]`

- Reads `git diff HEAD` and scans added lines.
- If HIGH+ findings exist, refuses to run `<cmd>` (exit `2`).
- Otherwise executes `<cmd>` via `subprocess.run`.
- After `<cmd>`, scans `git diff HEAD` again. If new HIGH+ findings
  appeared (and did not exist in the pre-scan), exits `2`.
- Outside a git repo: prints a warning and runs the command anyway
  (exit 0 / `<cmd>` exit).

### `pa1-lint` exit codes

| Code | Meaning |
|---|---|
| 0 | Clean / success |
| 1 | HIGH finding(s) blocked |
| 2 | CRITICAL finding(s) blocked / guard refused |

## Suppressions file format (`suppressions.toml`)

Slice 2 moved suppressions from `suppressions.yaml` (PyYAML) to
`suppressions.toml` (stdlib `tomllib`) so the tool has zero runtime
dependencies. The schema is TOML `[[suppressions]]` array-of-tables:

```toml
[[suppressions]]
column_pattern = "customer_id"   # regex (case-insensitive) matched against column header
value_prefix = "id_"            # literal string; the value must start with this
owner = "synth-data-team"       # who is responsible
expires_at = 2027-12-31         # ISO date; past this date the entry stops matching
reason = "Faker seed 42"        # free-text justification
```

Multiple `[[suppressions]]` blocks are allowed. Each block produces one
`Suppression` dataclass. The file is optional — if it does not exist,
no suppression is applied.

### Type mapping

| TOML type  | Field          | Notes |
|------------|----------------|-------|
| string     | `column_pattern` | regex syntax (`re.search`, `re.IGNORECASE`) |
| string     | `value_prefix`   | literal prefix (case-sensitive) |
| string     | `owner`          | informational |
| date       | `expires_at`     | `YYYY-MM-DD` literal; parser is `date.fromisoformat` |
| string     | `reason`         | optional; default empty |

## Compatibility

- The runtime dep list is empty (`pyproject.toml: dependencies = []`).
  `tomllib` is part of Python 3.11+ stdlib. `Faker` and `pytest` are
  dev-only.
- Tests run on Python 3.11+ (the floor is enforced by the package
  metadata and by the `tomllib` import in `pii_linter/suppressions.py`).

## Out of scope (slice 2)

- Publishing to PyPI / conda-forge.
- Pre-built wheels / GitHub Action.
- Cross-file correlation.
- Presidio integration.
- SARIF / GitHub Action.
- Precision/recall evaluation.