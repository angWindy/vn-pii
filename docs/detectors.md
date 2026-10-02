# Detectors reference

PA1 has four detector modules in [`pii_linter/detectors/`](../pii_linter/detectors).
Each is a pure function that takes a single cell value (and optional column
hints) and returns zero or more `Finding` dataclasses.

## `column_name.score_column(name) -> list[ColumnHint]`

Maps a column header to a list of `ColumnHint` guesses. Case-insensitive
regex. Empty input returns an empty list (caller falls back to content
regex). Multiple hints are returned when distinct entities both apply (e.g.
`customer_id_cccd` → `ID_NUMBER`).

The heuristic table is in
[`column_name.py: COLUMN_RULES`](../pii_linter/detectors/column_name.py).

## `content_regex.scan_value(value, hints) -> list[Finding]`

Runs every pre-compiled regex in this order (first one to fire wins per
cell, multiple matches can stack):

| Regex | Entity | Severity | Notes |
|---|---|---|---|
| `(?:\+84\|0)\d{9}\b` | `PHONE` | HIGH | Vietnamese mobile (10-digit) |
| `\b0\d{11}\b` | `ID_NUMBER` | HIGH | CCCD 12-digit |
| `\b\d{9}\b` | `ID_NUMBER` | HIGH | CMND 9-digit, **only** when column hint contains `ID_NUMBER` |
| `\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b` | `EMAIL` | MEDIUM | RFC-lite |
| `\b[A-HJ-NPR-Z0-9]{17}\b` | `ASSET` | MEDIUM | VIN 17-char (no I/O/Q) |
| `\b\d{2}[A-Z]?[\-\s]?\d{3}[\.\-]?\d{2,3}\b` | `ASSET` | MEDIUM | VN license plate |

`CMND` (9 digits) is intentionally noisy on its own — require an
`ID_NUMBER` column hint, or disable it entirely in [`content_regex.py`](../pii_linter/detectors/content_regex.py).

## `luhn_card.detect_card(value) -> Finding | None`

A card finding is emitted **only** when **all** of:

1. The value contains 13–19 digits (with optional spaces / dashes).
2. The digit string passes the Luhn checksum (ISO/IEC 7812).
3. The BIN prefix is in the supported-network table.

Supported BIN prefixes (subset, by length 4 / 2 / 1):

| Length | Prefix | Network |
|---|---|---|
| 1 | `4` | Visa |
| 2 | `51`–`55` | Mastercard |
| 2 | `34`, `37` | Amex |
| 2 | `35` | JCB |
| 4 | `2131`, `1800` | JCB |

Severity: `CRITICAL`. The mask shows the last 4 digits and the network:
`****-****-****-1111 [Visa]`.

## `free_text.scan(value, hints) -> list[Finding]`

Activated for:

- a `NOTE` column (hint `NOTE`), **or**
- values longer than 30 characters.

Runs the content regex set, then applies **combo boost**:

- If ≥ 2 distinct entities are at HIGH or above in the same value, all
  findings are bumped by `COMBO_BUMP` levels (capped at `CRITICAL`) and a
  synthetic `COMBO` finding is appended to make the combo visible to
  reporters.

## Suppressions

A TOML file (`suppressions.toml` at the repo root is an example) with this
shape:

```toml
[[suppressions]]
column_pattern = "customer_id"        # regex, case-insensitive
value_prefix = "id_"                 # literal string the value must start with
owner = "synth-data-team"            # who is responsible
expires_at = 2027-12-31              # ISO date — past this date it stops matching
reason = "Faker seed 42; verified by /tests/test_smoke.py"
```

`pii_linter.suppressions.load_suppressions(path)` parses the file using
stdlib `tomllib` and returns `[]` if it is missing. `is_suppressed(col,
value, sups)` returns `True` for the first active match. Slice 2 moved
this loader off PyYAML so the tool has zero runtime dependencies.

**Best practice:**

- Only suppress columns whose values are clearly synthetic (`id_`,
  `dummy_`, `0`-padded accounts).
- Never suppress real customer data; remove from the repo instead.
- Set `expires_at` far in the future but revisit every quarter.