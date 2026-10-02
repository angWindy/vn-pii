"""PA1 PII Linter CLI entrypoint.

Usage:
    pa1-lint scan <path> [--format {markdown,json}] [--suppressions PATH]
    pa1-lint guard -- <cmd>...

The CLI fail-fasts if it is not running inside the ``pa1`` conda environment
(exit code 3).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Iterable

from pii_linter import Finding, ScanResult
from pii_linter.detectors.column_name import score_column
from pii_linter.detectors.content_regex import scan_value as scan_content
from pii_linter.detectors.free_text import scan as scan_free_text
from pii_linter.detectors.luhn_card import detect_card
from pii_linter.report import render_markdown
from pii_linter.severity import CRITICAL, HIGH
from pii_linter.suppressions import (
    is_suppressed,
    load_suppressions,
)


_MAX_DEPTH = 3
_TARGET_EXTS = {".csv", ".jsonl", ".md"}
_MD_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")


def _in_pa1_env() -> bool:
    """Return True if we are running inside the ``pa1`` conda env."""
    sys_prefix = (sys.prefix or "").lower()
    return ("pa1" in sys_prefix) or ("envs/pa1" in sys_prefix)


def _env_fail() -> None:
    sys.stderr.write(
        "pa1-lint: not running in conda env 'pa1'. "
        "Activate it first:  conda activate pa1\n"
    )


def _list_files(root: Path) -> Iterable[Path]:
    """Yield target files up to depth ``_MAX_DEPTH``.

    If ``root`` is a single file (e.g. ``pa1-lint scan path/to/x.csv``),
    yield it directly so callers can scan individual fixtures.
    """
    if root.is_file():
        if root.suffix.lower() in _TARGET_EXTS:
            yield root
        return
    base_depth = len(root.parts) - 1
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in _TARGET_EXTS:
            continue
        depth = len(p.parts) - 1 - base_depth
        if depth > _MAX_DEPTH:
            continue
        yield p


def _dispatch_value(
    value: str,
    hints,
) -> list[Finding]:
    """Run all detectors on a single value and return 0+ Finding."""
    findings: list[Finding] = []
    card = detect_card(value)
    if card is not None:
        findings.append(card)
    findings.extend(scan_content(value, hints))
    findings.extend(scan_free_text(value, hints))
    return findings


def _scan_csv(
    p: Path,
    suppressions,
    file_findings: list[Finding],
) -> None:
    with p.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        hints_by_col = {h: score_column(h) for h in headers}
        for row_idx, row in enumerate(reader, start=2):
            for col, value in row.items():
                if value is None:
                    continue
                if is_suppressed(col, value, suppressions):
                    continue
                hints = hints_by_col.get(col, [])
                file_findings.extend(_dispatch_value(value, hints))


def _scan_jsonl(
    p: Path,
    suppressions,
    file_findings: list[Finding],
) -> None:
    with p.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            for key, value in obj.items():
                if not isinstance(value, str):
                    continue
                if is_suppressed(key, value, suppressions):
                    continue
                hints = score_column(key)
                file_findings.extend(_dispatch_value(value, hints))


def _scan_md(
    p: Path,
    suppressions,
    file_findings: list[Finding],
) -> None:
    with p.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not _MD_TABLE_LINE.match(line):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            for col_idx, value in enumerate(cells):
                if not value:
                    continue
                col = f"col{col_idx}"
                if is_suppressed(col, value, suppressions):
                    continue
                hints = score_column(col)
                file_findings.extend(_dispatch_value(value, hints))


def scan_path(root: str | Path, suppressions_path: str | Path | None = None) -> ScanResult:
    """Scan a directory tree and return a :class:`ScanResult`."""
    root = Path(root)
    sups = (
        load_suppressions(suppressions_path)
        if suppressions_path is not None
        else []
    )
    findings: list[Finding] = []
    by_file: dict[str, list[Finding]] = {}
    files = 0
    for p in sorted(_list_files(root)):
        files += 1
        rel = str(p.relative_to(root)
                  if root in p.parents or p == root
                  else p)
        bucket: list[Finding] = []
        try:
            if p.suffix.lower() == ".csv":
                _scan_csv(p, sups, bucket)
            elif p.suffix.lower() == ".jsonl":
                _scan_jsonl(p, sups, bucket)
            elif p.suffix.lower() == ".md":
                _scan_md(p, sups, bucket)
        except (OSError, UnicodeDecodeError):
            continue
        if bucket:
            by_file[rel] = bucket
            findings.extend(bucket)
    return ScanResult(findings=findings, files_scanned=files, by_file=by_file)


def _exit_for(findings: list[Finding]) -> int:
    if not findings:
        return 0
    max_sev = max(f.severity for f in findings)
    if max_sev >= CRITICAL:
        return 2
    if max_sev >= HIGH:
        return 1
    return 0


def _cmd_scan(args: argparse.Namespace) -> int:
    result = scan_path(args.path, suppressions_path=args.suppressions)
    if args.format == "json":
        sys.stdout.write(
            json.dumps(
                {
                    "files_scanned": result.files_scanned,
                    "findings": [
                        {
                            "entity": f.entity,
                            "severity": f.severity,
                            "evidence_masked": f.evidence_masked,
                            "span": list(f.span) if f.span else None,
                        }
                        for f in result.findings
                    ],
                    "by_file": {
                        path: [
                            {
                                "entity": f.entity,
                                "severity": f.severity,
                                "evidence_masked": f.evidence_masked,
                            }
                            for f in fs
                        ]
                        for path, fs in result.by_file.items()
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_markdown(result))
    return _exit_for(result.findings)


def _cmd_guard(args: argparse.Namespace) -> int:
    from pii_linter.guard import run

    return run(args.cmd)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pa1-lint",
        description="Local-only PII linter for VN datasets (CSV/JSONL/Markdown).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Scan a directory tree for PII.")
    p_scan.add_argument("path", help="Root directory to scan recursively.")
    p_scan.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format (default markdown).",
    )
    p_scan.add_argument(
        "--suppressions",
        default=None,
        help="Path to a suppressions.yaml file.",
    )
    p_scan.set_defaults(func=_cmd_scan)

    p_guard = sub.add_parser(
        "guard", help="Pre/post-scan a command: only run if both scans are clean."
    )
    p_guard.add_argument(
        "cmd",
        nargs=argparse.REMAINDER,
        help="The shell command and args to execute after pre-scan.",
    )
    p_guard.set_defaults(func=_cmd_guard)
    return parser


def main(argv: list[str] | None = None) -> int:
    if not _in_pa1_env():
        _env_fail()
        return 3
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())