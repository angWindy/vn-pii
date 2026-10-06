"""Guard mode for PII.

Runs a user-supplied command but pre/post-scans ``git diff HEAD`` so that
the command only executes when both states are PII-clean. Designed to be
the wrapper around AI agent commands like ``aider``, ``cursor`` or
``claude`` itself.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from pii_linter import Finding, ScanResult, TARGET_EXTS
from pii_linter.report import render_markdown
from pii_linter.severity import HIGH
from pii_linter.suppressions import Suppression, is_suppressed, load_suppressions

# Default suppressions file at the repo root, if present. Diff-scanned lines
# have no column header, so these records match on ``value_prefix`` alone.
_SUPPRESSIONS_FILE = Path(__file__).resolve().parent.parent / "suppressions.toml"


def _diff_added_lines(cwd: Path, refs: list[str]) -> str:
    """Return lines added by ``git diff <refs...>`` ('+' lines, marker stripped).

    Only files whose extension is in ``TARGET_EXTS`` are included, matching
    ``cli.scan_staged``. Without this filter the guard scanned *every* file
    in the diff — including ``.py`` — so committing a test file that merely
    mentions a synthetic phone number blocked the commit even though the
    tool only ever claims to cover CSV/JSONL/Markdown.
    """
    exe = shutil.which("git")
    if exe is None:
        return ""
    try:
        out = subprocess.run(
            [exe, "diff", *refs, "--unified=0", "--no-renames"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    added: list[str] = []
    current = ""
    for line in out.stdout.splitlines():
        if line.startswith("diff --git"):
            parts = line.split()
            current = parts[3].lstrip("b/") if len(parts) > 3 else ""
            continue
        if line.startswith("+++"):
            # b/<path> — trust this over the diff --git header.
            current = line[4:].strip().lstrip("b/") if len(line) > 4 else current
            continue
        if line.startswith("+") and not line.startswith("+++"):
            if current and Path(current).suffix.lower() in TARGET_EXTS:
                added.append(line[1:])
    return "\n".join(added)


def _git_diff_text(cwd: Path) -> str:
    """Return text introduced by working-tree + staged changes (lines starting with '+')."""
    if not (cwd / ".git").exists():
        return ""
    return _diff_added_lines(cwd, ["HEAD"])


def _head_sha(cwd: Path) -> str:
    """Return the current HEAD commit sha, or '' when there is none."""
    exe = shutil.which("git")
    if exe is None:
        return ""
    try:
        out = subprocess.run(
            [exe, "rev-parse", "HEAD"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip()


def _has_high_plus(findings: list[Finding]) -> bool:
    return any(f.severity >= HIGH for f in findings)


def _scan_diff_text(
    text: str,
    suppressions: list[Suppression] | None = None,
) -> list[Finding]:
    """Scan the synthetic blob of staged/added lines.

    ``suppressions`` is optional for backwards compatibility; pass the
    loaded records so diff-scanned lines honour them just like the
    ``scan`` path does. Diff lines carry no column header, so
    suppressions are matched with an empty column name.

    Delegates to ``cli._dispatch_value`` so a staged line and the same line
    read from disk produce byte-identical evidence masks. Running the two
    detectors here independently used to leak a co-located PAN into the
    PHONE finding's evidence -- the one report a blocked commit shows.
    """
    if not text.strip():
        return []
    # Imported here, not at module scope: `cli` imports this module lazily
    # from `_cmd_guard`, so a top-level import would close the cycle.
    from pii_linter.cli import _dispatch_value

    findings: list[Finding] = []
    for line in text.splitlines():
        if suppressions and is_suppressed("", line, suppressions):
            continue
        findings.extend(_dispatch_value(line, []))
    return findings


def _fake_result(findings: list[Finding]) -> ScanResult:
    by_file: dict[str, list[Finding]] = {"(staged diff)": findings}
    return ScanResult(findings=findings, files_scanned=1, by_file=by_file)


def run(cmd: list[str]) -> int:
    """Pre-scan, run ``cmd``, post-scan. Return the worst exit code."""
    # `argparse.REMAINDER` swallows the conventional `--` separator
    # (`pii-lint guard -- aider ...`), leaving it as argv[0] and making
    # subprocess raise FileNotFoundError. Normalise it away here so every
    # caller is safe, not just the one that went through the CLI.
    cmd = list(cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        sys.stderr.write("[pii-guard] no command given; nothing to run.\n")
        return 2

    cwd = Path.cwd()
    # Load suppressions once so the diff path honours the same records as
    # `scan --suppressions`. Diff lines have no column context, so
    # suppressions only match on `value_prefix`.
    suppressions: list[Suppression] = []
    if _SUPPRESSIONS_FILE.exists():
        try:
            suppressions = load_suppressions(_SUPPRESSIONS_FILE)
        except ValueError:
            suppressions = []

    if not (cwd / ".git").exists():
        sys.stderr.write(
            "[pii-guard] not a git repo; running command without guard.\n"
        )
        proc = subprocess.run(cmd, cwd=str(cwd))
        return proc.returncode

    pre_text = _git_diff_text(cwd)
    pre_findings = _scan_diff_text(pre_text, suppressions)
    if _has_high_plus(pre_findings):
        sys.stderr.write(
            "[pii-guard] BLOCKED: pre-scan found HIGH+ findings. "
            "Refusing to run the command.\n"
        )
        sys.stderr.write(render_markdown(_fake_result(pre_findings)))
        return 2

    # Anchor the post-scan to the HEAD that existed *before* the command ran.
    # Scoping it to live HEAD instead would go blind whenever the command
    # commits: the staged content becomes part of HEAD, `git diff HEAD` comes
    # back empty, and PII the agent just committed sails through unchecked.
    pre_head = _head_sha(cwd)

    proc = subprocess.run(cmd, cwd=str(cwd))
    if proc.returncode != 0:
        return proc.returncode

    post_head = _head_sha(cwd)
    if pre_head and post_head and post_head != pre_head:
        # The command created commits — diff old HEAD..new HEAD so the
        # committed content is actually inspected.
        post_text = _diff_added_lines(cwd, [pre_head, post_head])
    else:
        post_text = _git_diff_text(cwd)
    post_findings = _scan_diff_text(post_text, suppressions)
    pre_masks = {f.evidence_raw for f in pre_findings}
    new = [f for f in post_findings if f.evidence_raw not in pre_masks]
    if _has_high_plus(new):
        sys.stderr.write(
            "[pii-guard] BLOCKED: post-scan found new HIGH+ findings "
            "introduced by the command.\n"
        )
        sys.stderr.write(render_markdown(_fake_result(new)))
        return 2

    return 0