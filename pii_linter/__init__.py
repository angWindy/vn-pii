"""PA1 Dataset PII Linter.

A local-only defensive scanner for Vietnamese datasets (CSV / JSONL / Markdown).
Designed to be wired into pre-commit hooks and AI agent workflows so that
PII-bearing rows are caught before they leave the workstation.
"""

from __future__ import annotations

from dataclasses import dataclass

__version__ = "0.1.0"


@dataclass(frozen=True)
class Finding:
    """One PII occurrence detected in a single cell value.

    ``evidence_raw`` holds the original match span; ``evidence_masked`` is a
    deterministic human-readable mask (see :func:`pii_linter.report.mask_value`).
    Raw values are NEVER printed by reporters — they only live in memory for
    downstream tooling.

    ``file`` and ``line_no`` carry the diff-cursor path and line number for
    findings produced by ``pa1-lint scan --staged``. They are empty/zero for
    findings produced by the full-scan path, so the field is optional and
    backwards compatible.
    """

    entity: str          # one of SEVERITY_BY_ENTITY keys
    severity: int        # 1=LOW, 2=MEDIUM, 3=HIGH, 4=CRITICAL
    evidence_raw: str    # the slice of `value` that matched (or full value if not span-aware)
    evidence_masked: str # display-safe version
    span: tuple[int, int] | None  # (start, end) into the value, None when not applicable
    file: str = ""       # repo-relative path; non-empty only for diff-mode findings
    line_no: int = 0     # line number in the file; non-zero only for diff-mode findings


@dataclass(frozen=True)
class ColumnHint:
    """A heuristic guess of what kind of entity a column likely holds.

    Produced by :func:`pii_linter.detectors.column_name.score_column`. The
    severity here is a *baseline* used when a content regex matches but the
    regex alone cannot confirm entity type.
    """

    entity: str
    severity: int


@dataclass
class ScanResult:
    """Aggregate output of one :func:`pii_linter.cli.scan_path` invocation."""

    findings: list[Finding]
    files_scanned: int
    by_file: dict[str, list[Finding]]