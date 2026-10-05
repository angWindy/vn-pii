"""PA1 Dataset PII Linter.

A local-only defensive scanner for Vietnamese datasets (CSV / JSONL / Markdown).
Designed to be wired into pre-commit hooks and AI agent workflows so that
PII-bearing rows are caught before they leave the workstation.
"""

from __future__ import annotations

from dataclasses import dataclass

__version__ = "0.1.0"

# File extensions the linter claims to cover. The filesystem scan
# (``cli._list_files``) and both diff scans (``cli.scan_staged`` and
# ``guard``) filter on this, so it lives in the package root rather than in
# one module: ``guard`` cannot import ``cli`` (``cli`` imports ``guard``
# lazily), and a guard that scanned files outside this set would contradict
# the documented CSV/JSONL/Markdown scope.
TARGET_EXTS = frozenset({".csv", ".jsonl", ".md"})


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


# Public callables, resolved lazily. ``scan`` is the import-friendly alias for
# ``cli.scan_path``. ``cli`` cannot be imported at module scope: every detector
# imports this module back (``from pii_linter import Finding``), so a top-level
# import would be circular. PEP 562 defers it to first attribute access, which
# keeps a bare ``import pii_linter`` cheap and cycle-free.
_LAZY_EXPORTS = {
    "scan": ("pii_linter.cli", "scan_path"),
    "scan_staged": ("pii_linter.cli", "scan_staged"),
}

__all__ = [
    "ColumnHint",
    "Finding",
    "ScanResult",
    "TARGET_EXTS",
    "scan",
    "scan_staged",
]


def __getattr__(name: str):
    if name in _LAZY_EXPORTS:
        import importlib

        mod_name, attr = _LAZY_EXPORTS[name]
        value = getattr(importlib.import_module(mod_name), attr)
        # Cache in module globals so repeat lookups skip __getattr__ entirely.
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)