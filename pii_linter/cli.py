"""PA1 PII Linter CLI entrypoint.

Usage:
    pa1-lint scan <path> [--format {markdown,json}] [--suppressions PATH]
    pa1-lint scan --staged [--format {markdown,json}] [--suppressions PATH]
    pa1-lint guard -- <cmd>...

The tool runs in any Python 3.11+ environment (no conda env check in
Slice 2+).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from pii_linter import Finding, ScanResult
from pii_linter.detectors.column_name import score_column
from pii_linter.detectors.content_regex import scan_value as scan_content
from pii_linter.detectors.free_text import apply_combo
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
    """Run all detectors on a single value and return 0+ Finding.

    Content regex runs once; combo boost is applied to the merged list
    (no double-scan). The NOTE-column / long-value gating is the caller's
    responsibility (it already knows whether ``hints`` contains NOTE).
    """
    findings: list[Finding] = []
    card = detect_card(value)
    if card is not None:
        findings.append(card)
    findings.extend(scan_content(value, hints))
    return apply_combo(findings)


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
        if root.is_file():
            rel = p.name
        else:
            rel = str(p.relative_to(root)) if root in p.parents else str(p)
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


# ---------------------------------------------------------------------------
# Staged-diff scan (used by `pa1-lint scan --staged` and the pre-commit hook).
# ---------------------------------------------------------------------------

def _git_diff_staged(cwd: Path) -> list[tuple[str, int, str]]:
    """Return added lines from ``git diff --cached`` as ``(file, line_no, text)``.

    Lines starting with ``+++`` are file headers (skipped). Lines starting
    with ``+`` (excluding ``+++``) are content added in the new revision. The
    leading ``+`` is stripped; ``dt.line_no`` is taken from the hunk header
    (``@@ -a,b +c,d @@``).

    Returns ``[]`` if the cwd is not a git repo or git is not on PATH.
    """
    if not (cwd / ".git").exists():
        return []
    exe = shutil.which("git")
    if exe is None:
        return []
    try:
        proc = subprocess.run(
            [exe, "diff", "--cached", "--unified=0", "--no-renames", "--no-color"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    out: list[tuple[str, int, str]] = []
    current_file = ""
    new_line = 0
    for line in proc.stdout.splitlines():
        if line.startswith("diff --git"):
            # diff --git a/path/to/file b/path/to/file
            try:
                parts = line.split()
                current_file = parts[2].lstrip("a/")
            except IndexError:
                current_file = ""
            new_line = 0
            continue
        if line.startswith("--- "):
            continue
        if line.startswith("+++ "):
            continue
        if line.startswith("@@"):
            # @@ -old_a,old_b +new_a,new_b @@
            try:
                plus = line.split("+", 1)[1]
                num = plus.split(",", 1)[0].split(" ", 1)[0]
                new_line = int(num)
            except (IndexError, ValueError):
                new_line = 0
            continue
        if line.startswith("+"):
            if current_file and new_line:
                out.append((current_file, new_line, line[1:]))
            new_line += 1
    return out


def scan_staged(cwd: str | Path | None = None, suppressions_path=None) -> ScanResult:
    """Scan lines added by ``git diff --cached`` and return findings.

    Only lines whose file extension is in ``_TARGET_EXTS`` are scanned.
    Each finding carries ``file`` (path) and ``line_no`` so reporters can
    render a ``file:line`` cursor.
    """
    from dataclasses import replace

    root = Path(cwd) if cwd else Path.cwd()
    sups = (
        load_suppressions(suppressions_path)
        if suppressions_path is not None
        else []
    )
    findings: list[Finding] = []
    by_file: dict[str, list[Finding]] = {}
    files_scanned = 0
    for file_path, lineno, text in _git_diff_staged(root):
        display_path = file_path.removeprefix("a/")
        ext = Path(display_path).suffix.lower()
        if ext not in _TARGET_EXTS:
            continue
        files_scanned += 1
        if not text.strip():
            continue
        if is_suppressed("", text, sups):
            continue
        bucket: list[Finding] = []
        for f in _dispatch_value(text, []):
            bucket.append(replace(f, file=display_path, line_no=lineno))
        if bucket:
            by_file.setdefault(display_path, []).extend(bucket)
            findings.extend(bucket)
    return ScanResult(findings=findings, files_scanned=files_scanned, by_file=by_file)


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
    if args.staged:
        result = scan_staged(suppressions_path=args.suppressions)
    elif args.path is None:
        sys.stderr.write("Error: PATH is required unless --staged is set.\n")
        return 2
    else:
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
                            "file": f.file or None,
                            "line_no": f.line_no or None,
                        }
                        for f in result.findings
                    ],
                    "by_file": {
                        path: [
                            {
                                "entity": f.entity,
                                "severity": f.severity,
                                "evidence_masked": f.evidence_masked,
                                "line_no": f.line_no or None,
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

    p_scan = sub.add_parser("scan", help="Scan a directory tree or staged diff for PII.")
    p_scan.add_argument("path", nargs="?", default=None,
                        help="Root directory to scan recursively. Omit when --staged is set.")
    p_scan.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format (default markdown).",
    )
    p_scan.add_argument(
        "--suppressions",
        default=None,
        help="Path to a suppressions.toml file.",
    )
    p_scan.add_argument(
        "--staged",
        action="store_true",
        help="Scan only the lines introduced by `git diff --cached` "
             "(used by the pre-commit hook). Implies no positional PATH.",
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
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())