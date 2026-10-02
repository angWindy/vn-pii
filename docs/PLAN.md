# PA1 PII Linter — Project Plan

This is the archived plan for PA1 PII Linter. It consolidates decisions
from all slices. For the current status, see [PLAN.md](../PLAN.md).

---

## Slices

| Slice | Goal | Status |
|---|---|---|
| Slice 1 | MVP: detectors + scanner + guard + suppressions + 5 docs + ECC | ✅ Done |
| Slice 2 | Zero-dep distribution: TOML suppressions, drop PyYAML, drop env enforcement, `pip install git+...` | ✅ Done |

---

## Design decisions

### Why flat root layout?

`docs/problem/` is for research notes (existing `side.md`, `side.vi.md`).
Slice 1 moved all production code to the repo root — standard Python
layout — so `docs/` holds only user-facing documentation.

### Severity table

| Entity | Severity | Notes |
|---|---|---|
| `PERSON` | HIGH | column hint only |
| `PHONE` | HIGH | Vietnamese mobile 10-digit (`0` or `+84` prefix) |
| `ID_NUMBER` | HIGH | CCCD 12-digit or CMND 9-digit (with column hint) |
| `CARD_NO` | CRITICAL | 13–19 digits, Luhn + BIN check |
| `ACCOUNT_NO` | HIGH | — |
| `EMAIL` | MEDIUM | RFC-lite regex |
| `ASSET` | MEDIUM | VIN 17-char or VN plate |
| `NOTE` | MEDIUM | free-text combo |
| `URL_HANDLE` | MEDIUM | zalo.me links |

### Masking strategy

| Entity | Mask | Rule |
|---|---|---|
| `PERSON` | `Nguyễn V*** A***` | keep first letter of each word |
| `PHONE` | `09****123` | keep 2 digits + last 3 |
| `ID_NUMBER` | `****-****-***-12` | keep last 2 |
| `EMAIL` | `n.g.u.y.e.n@domain` | keep domain |
| `CARD_NO` | `****-****-****-1234` | keep last 4 |
| `ASSET` | first 3 chars + `***` | — |
| `NOTE` | `***[NOTE]***` | redact entirely |

### Why TOML for suppressions (Slice 2)?

`tomllib` is in Python 3.11+ stdlib — zero runtime dependencies. TOML
supports comments (unlike JSON) and is already the standard for Python
config (`pyproject.toml`).

### Why drop conda-env enforcement (Slice 2)?

End users in downstream projects do not have a `pa1` conda env. The tool
now runs in any Python 3.11+ environment. The `pa1` env is still used
for local development (isolates Faker for fixture generation), but it is
**not** a tool requirement.

---

## Architecture

```
pa1-lint (CLI)
├── scan <path> [--suppressions <path>] [--format markdown|json]
│   ├── cli._list_files()           — enumerate CSV/JSONL/MD up to depth 3
│   ├── cli._scan_csv()             — csv.DictReader per file
│   ├── cli._scan_jsonl()           — json.loads per line
│   ├── cli._scan_md()              — extract table rows from Markdown
│   ├── detectors.column_name        — header → list[ColumnHint]
│   ├── detectors.content_regex     — regex match per entity
│   ├── detectors.luhn_card         — Luhn checksum + BIN prefix
│   ├── detectors.free_text          — len > 30 OR NOTE column → combo boost
│   ├── suppressions                — load TOML, check column + prefix
│   └── report                      — mask_value + render_markdown
└── guard -- <cmd>
    ├── git diff HEAD (pre)         — scan added lines
    ├── run <cmd>                   — subprocess.run
    └── git diff HEAD (post)         — scan new added lines
```

### Data flow

```
CSV/JSONL/MD files
  → _list_files() [enumerate up to depth 3]
  → for each cell:
       score_column() [column hint]
       scan_content() [regex]
       detect_card() [Luhn + BIN]
       scan_free_text() [combo]
  → apply_combo_boost() [≥2 HIGH+ in same value → bump 1 level]
  → is_suppressed() [column pattern + value prefix + expires]
  → mask_value() [per-entity masker]
  → render_markdown() [grouped by file]
```

---

## Module inventory

| File | Purpose |
|---|---|
| `pii_linter/__init__.py` | `__version__ = "0.1.0"` |
| `pii_linter/severity.py` | `LOW=1, MEDIUM=2, HIGH=3, CRITICAL=4`, `SEVERITY_BY_ENTITY`, `apply_combo_boost()` |
| `pii_linter/suppressions.py` | `Suppression` dataclass, `load_suppressions()` (tomllib), `is_suppressed()` |
| `pii_linter/report.py` | `mask_value()`, `render_markdown()`, `ScanResult` dataclass |
| `pii_linter/cli.py` | `main()`, `scan_path()`, `_list_files()`, `_dispatch_value()` |
| `pii_linter/guard.py` | `run(cmd)` — pre/post git-diff scan wrapper |
| `pii_linter/detectors/column_name.py` | `COLUMN_RULES`, `score_column()` |
| `pii_linter/detectors/content_regex.py` | `RE_VN_PHONE`, `RE_CCCD`, `RE_CMND`, `RE_EMAIL`, `RE_VIN`, `RE_PLATE`, `RE_ZALO`, `scan_value()` |
| `pii_linter/detectors/luhn_card.py` | `luhn_check()`, `detect_card()` |
| `pii_linter/detectors/free_text.py` | `scan()` — combo boost for long values or NOTE columns |
| `fixtures/generators/make_synthetic.py` | `Faker("vi_VN")` + `Faker("en_US")`, seed=42; helpers for Luhn cards and VIN |
| `suppressions.toml` | 3 example entries (customer_id, phone/email, account_no) |

---

## Regex reference

| Entity | Pattern | Notes |
|---|---|---|
| `PHONE` | `(?:\+84\|0)\d{9}` | Vietnamese mobile, 10-digit |
| `ID_NUMBER` (CCCD) | `\b0\d{11}\b` | 12-digit starting with 0 |
| `ID_NUMBER` (CMND) | `\b\d{9}\b` | 9-digit, **only** with column hint |
| `EMAIL` | RFC-lite regex | standard email shape |
| `ASSET` (VIN) | `\b[A-HJ-NPR-Z0-9]{17}\b` | 17-char, no I/O/Q |
| `ASSET` (plate) | `\b\d{2}[A-Z]?[\-\s]?\d{3}[\.\-]?\d{2,3}\b` | VN plate format |
| `URL_HANDLE` | `zalo\.me/\w+` | Zalo profile links |

---

## Fixture generation

- `Faker("vi_VN")` + `Faker("en_US")`, `seed=42`
- Helper `make_card_luhn(prefix)` for Luhn-valid test cards (Visa 4xx, MC 5xx)
- Helper `make_vin()` for 17-char VIN without I/O/Q
- `fixtures/gold/` is **git-ignored** (contains planted PII)
- `fixtures/negative/` is **committed** (clean data for CI)

---

## Out of scope

- Cross-file correlation (same phone across two files)
- Presidio integration
- SARIF / GitHub Action output
- Precision/recall evaluation against labeled data
- PyPI / conda-forge publishing
- First-party Cursor / Aider / Claude Code wrapper

---

## Slice 1 acceptance tests (all verified ✅)

```
pa1-lint --version                  → 0.1.0
pa1-lint scan fixtures/gold/leads_50.csv
  → exit 1, ≥1 PHONE finding
pa1-lint scan fixtures/gold/notes_50.jsonl
  → exit 2 (CRITICAL), ≥1 CARD_NO
pa1-lint scan fixtures/negative/aggregate_50.csv
  → exit 0, 0 findings
pa1-lint scan fixtures/gold/leads_50.csv (single-file path)
  → exit 1 (Slice 1 bug fix)
pytest tests/                       → 36/36 pass
```

---

## Slice 2 acceptance tests (all verified ✅)

```
pip install git+https://github.com/anthang2003/vn-pii
  → zero extra packages pulled
pa1-lint --version                  → works without conda env
pa1-lint scan fixtures/gold/leads_50.csv
  → exit 1, 100 findings (no ImportError: yaml)
pa1-lint scan fixtures/gold/leads_50.csv \
  --suppressions suppressions.toml
  → loads TOML correctly (3 entries)
pytest tests/                       → 36/36 pass
```

---

## How this plan was built

The original `.cursor/plans/` directory contained working-session snapshots.
It was consolidated into this document so the information lives alongside
the other project documentation in `docs/`. The source snapshots were:

- `.cursor/plans/pa1_pii_linter_slice_1_(v3_-_flat_root_+_ecc_+_docs)_2cfee7f3.plan.md`
- `.cursor/plans/pa1_pii_linter_slice_2_zero-dep_distribution.plan.md`