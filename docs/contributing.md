# Contributing

PII is intentionally small. Most contributions are one of:

- a new entity (`PERSON`, `PHONE`, …)
- a new detector regex
- a new suppression field
- a new test fixture

This guide assumes you have already followed the contributor steps in
[README.md](../README.md).

## Add a new entity

1. Add the entity to `pii_linter/severity.py:SEVERITY_BY_ENTITY` with a
   baseline severity (`LOW`/`MEDIUM`/`HIGH`/`CRITICAL`).
2. If you have a regex, add it to
   `pii_linter/detectors/content_regex.py` and append the tuple to
   `_PATTERNS` (entity → severity will resolve via the table).
3. Add the entity in `pii_linter/report.py:_SUGGESTION_BY_ENTITY` so the
   markdown report shows a remediation hint.
4. Add a test in `tests/test_content_regex.py` (positive + negative case).
5. Update `docs/detectors.md` and `docs/spec.md` if the entity appears in
   the public surface.

## Add a new suppression field

Slice 2 uses `suppressions.toml` (stdlib `tomllib`) instead of YAML.
To extend the schema:

1. Add the field to the `Suppression` dataclass in
   `pii_linter/suppressions.py`.
2. Parse it in `_parse_entry`.
3. Update `matches()` if the field changes matching behavior.
4. Add a positive + negative test in `tests/test_suppressions.py`.
5. Document the new field in `docs/spec.md` §Suppressions file format.

A detector is a pure function with the signature:

```python
def detect(value: str, column_hints: Iterable[ColumnHint] = ()) -> list[Finding]:
    ...
```

1. Drop the file in `pii_linter/detectors/<name>.py`.
2. Wire it into `pii_linter/cli._dispatch_value`.
3. Add a unit test in `tests/test_<name>.py`.
4. Document the regex / algorithm in `docs/detectors.md`.

## Add a new file format (e.g. parquet)

1. Add the extension to `_TARGET_EXTS` in `pii_linter/cli.py`.
2. Write a `_scan_<ext>(p, sups, bucket)` helper that iterates rows and
   calls `_dispatch_value` for each cell.
3. Increase `_MAX_DEPTH` if needed.

## Style guide

- Type hints everywhere on public functions.
- Dataclasses for DTOs (`@dataclass(frozen=True)` for `Finding`,
  `ColumnHint`, `Suppression`).
- Docstrings explain regex shape + entity + return contract.
- **Never** `print`/`write` raw values; route through `mask_value` first.
- Keep detector modules dependency-free (no I/O).
- Tests: pytest, no network, no filesystem pollution outside `tmp_path`.

## Run the smoke test

```bash
pytest tests/ -v
```

If you want to see the markdown output for a single gold file:

```bash
pii-lint scan fixtures/gold --suppressions suppressions.toml
```

## Commit checklist

- `git add` only tracked files (the repo `.gitignore` already blocks
  `fixtures/gold/*.csv`).
- The pre-commit hook will re-scan staged CSV/JSONL/MD and block the
  commit if HIGH+ findings appear.
- Do **not** add a suppression for real customer data; that defeats the
  scanner. Use suppression only for clearly synthetic prefixes.