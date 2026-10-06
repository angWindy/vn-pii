"""PII Linter CLI entrypoint.

Usage:
    pii-lint init                     # install the global git hook (one-time)
    pii-lint uninstall                # remove it again
    pii-lint [PATH]                 # same as `pii-lint scan PATH`; bare -> cwd
    pii-lint scan <path> [--format {markdown,json}] [--suppressions PATH]
    pii-lint scan --staged [--format {markdown,json}] [--suppressions PATH]
    pii-lint guard -- <cmd>...
    python -m pii_linter [PATH]      # identical to `pii-lint`

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
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from pii_linter import Finding, ScanResult, TARGET_EXTS
from pii_linter.detectors.column_name import score_column
from pii_linter.detectors.content_regex import _redact_all
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
_TARGET_EXTS = TARGET_EXTS
_MD_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")

# Bad invocation (sysexits.h EX_USAGE) is deliberately distinct from 2, which
# means "CRITICAL PII found" in `docs/spec.md`. Sharing the code made a typo in
# a hook config indistinguishable from a real leak in the logs.
EX_USAGE = 64


def _list_files(root: Path) -> Iterable[Path]:
    """Yield target files up to depth ``_MAX_DEPTH``.

    If ``root`` is a single file (e.g. ``pii-lint scan path/to/x.csv``),
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

    Each detector only knows its own span, so a cell holding a PAN and a phone
    produced ``CARD_NO -> ***,***`` and ``PHONE -> 4111111111111111,***``: the
    PAN then landed in the report in the clear. Re-masking the merged span set
    here means every finding in a value carries the same, fully redacted
    evidence, so the reporters can never print a co-located secret.
    """
    findings: list[Finding] = []
    card = detect_card(value)
    if card is not None:
        findings.append(card)
    findings.extend(scan_content(value, hints))
    if len(findings) < 2:
        return apply_combo(findings)
    spans = [f.span for f in findings if f.span]
    masked = _redact_all(value, spans)
    return apply_combo([replace(f, evidence_masked=masked) for f in findings])


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
    """Scan a Markdown file.

    Table rows keep the per-cell ``col<N>`` column heuristic. Non-table prose
    is scanned line-by-line with no column hints — that is the same path
    ``guard._scan_diff_text`` and ``scan --staged`` take, so a file yields
    the same findings no matter which entry point reads it. Skipping prose
    entirely used to make ``scan <file.md>`` silently miss PII that
    ``scan --staged`` and ``guard`` both flagged in the very same file.
    """
    with p.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            if not _MD_TABLE_LINE.match(line):
                # Prose line: no column context, but still real content.
                if is_suppressed("", line, suppressions):
                    continue
                file_findings.extend(_dispatch_value(line, []))
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
# Staged-diff scan (used by `pii-lint scan --staged` and the pre-commit hook).
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


def _cmd_install_hooks(args: argparse.Namespace) -> int:
    from pii_linter.hooks import install_hooks

    if args.agent == "all":
        agents = ["claude-code", "cursor", "cody", "codex"]
    elif args.agent == "aider":
        agents = ["aider"]
    else:
        agents = [args.agent]

    if args.user and args.project:
        sys.stderr.write("Error: --user and --project are mutually exclusive.\n")
        return EX_USAGE
    scope = "project" if args.project else "user"
    return install_hooks.install(
        agents=agents,
        scope=scope,
        force_replace=args.force_replace,
        dry_run=args.dry_run,
    )


def _cmd_init(args: argparse.Namespace) -> int:
    """Install the global git hook. The one-time setup for zero-config use."""
    from pii_linter.hooks import install_git

    return install_git.install(dry_run=args.dry_run)


def _cmd_uninstall(args: argparse.Namespace) -> int:
    from pii_linter.hooks import install_git

    return install_git.uninstall(dry_run=args.dry_run)


def _cmd_guard(args: argparse.Namespace) -> int:
    from pii_linter.guard import run

    if not [c for c in args.cmd if c != "--"]:
        sys.stderr.write("Error: guard requires a command to run.\n")
        return EX_USAGE
    # `guard.run` normalises the `--` separator itself, so the documented
    # `pii-lint guard -- <cmd>` form and the bare form both work.
    return run(args.cmd)


class _Parser(argparse.ArgumentParser):
    """ArgumentParser that exits EX_USAGE instead of 2 on bad flags.

    argparse's default exit code 2 collides with our convention that
    ``2 == CRITICAL PII found`` (``docs/spec.md``), which made a typo in a
    hook config indistinguishable from a real leak in the logs. Using this
    as the root ``parser_class`` propagates the fix to every subparser too.
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        sys.stderr.write(f"Error: {message}\n")
        sys.stderr.write(
            f"Run 'pii-lint --help' for usage. (exit {EX_USAGE} = bad usage, "
            f"not a PII finding.)\n"
        )
        raise SystemExit(EX_USAGE)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="pii-lint",
        description="Local-only PII linter for VN datasets (CSV/JSONL/Markdown).",
    )
    sub = parser.add_subparsers(dest="command", required=False)

    p_scan = sub.add_parser("scan", help="Scan a directory tree or staged diff for PII.")
    p_scan.add_argument("path", nargs="?", default=".",
                        help="Root directory to scan recursively (default: the current directory).")
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

    p_install = sub.add_parser(
        "install-hooks",
        help="Install PII hook configs into a coding agent's config dir. "
             "Templates are read from the installed package.",
    )
    p_install.add_argument(
        "agent",
        choices=("claude-code", "cursor", "cody", "codex", "aider", "all"),
        help="Which agent's config to install. 'all' covers the 4 JSON/TOML agents.",
    )
    p_install.add_argument(
        "--user",
        action="store_true",
        help="Install under $HOME (default).",
    )
    p_install.add_argument(
        "--project",
        action="store_true",
        help="Install under the current git repo root (./.claude, ./.cursor, ...).",
    )
    p_install.add_argument(
        "--force-replace",
        action="store_true",
        help="Overwrite existing config files instead of merging.",
    )
    p_install.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without touching any files.",
    )
    p_install.set_defaults(func=_cmd_install_hooks)

    p_init = sub.add_parser(
        "init",
        help="Install the global git pre-commit hook. Once per machine; "
             "after this, every `git commit` anywhere scans staged PII.",
    )
    p_init.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without touching any files or git config.",
    )
    p_init.set_defaults(func=_cmd_init)

    p_uninstall = sub.add_parser(
        "uninstall",
        help="Remove the global git hook and restore core.hooksPath.",
    )
    p_uninstall.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be removed without touching any files.",
    )
    p_uninstall.set_defaults(func=_cmd_uninstall)
    return parser


# Every subcommand the parser defines. If argv[0] is one of these the user is
# naming a command explicitly and it is left alone. `guard` / `install-hooks`
# are not dataset scans, so they keep their name; `scan` is spelled out here
# only to stay backward compatible with the documented form.
_ALL_COMMANDS = ("scan", "guard", "install-hooks", "init", "uninstall")
_ROOT_FLAGS = ("-h", "--help")


def _normalise_argv(argv: list[str]) -> list[str]:
    """Allow `pii-lint <path>` and bare `pii-lint` to mean "scan".

    ``pii-lint data.csv`` is rewritten to ``scan data.csv`` and a bare
    ``pii-lint`` scans the current directory. Anything that already names a
    subcommand, or asks for root help, is passed through untouched.
    """
    if not argv:
        return ["scan", "."]
    if argv[0] in _ALL_COMMANDS or argv[0] in _ROOT_FLAGS:
        return argv
    return ["scan", *argv]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(_normalise_argv(raw))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())