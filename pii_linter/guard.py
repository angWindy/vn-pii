"""Guard mode for PA1.

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

from pii_linter import Finding, ScanResult
from pii_linter.detectors.column_name import score_column
from pii_linter.detectors.content_regex import scan_value as scan_content_fn
from pii_linter.detectors.free_text import apply_combo as apply_combo_fn
from pii_linter.detectors.luhn_card import detect_card
from pii_linter.report import render_markdown
from pii_linter.severity import HIGH


def _diff_added_lines(cwd: Path, refs: list[str]) -> str:
    """Return lines added by ``git diff <refs...>`` ('+' lines, marker stripped)."""
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
    for line in out.stdout.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
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


def _scan_diff_text(text: str) -> list[Finding]:
    """Scan the synthetic blob of staged/added lines."""
    if not text.strip():
        return []
    findings: list[Finding] = []
    for line in text.splitlines():
        card = detect_card(line)
        if card is not None:
            findings.append(card)
        findings.extend(scan_content_fn(line, []))
    return apply_combo_fn(findings)


def _fake_result(findings: list[Finding]) -> ScanResult:
    by_file: dict[str, list[Finding]] = {"(staged diff)": findings}
    return ScanResult(findings=findings, files_scanned=1, by_file=by_file)


def run(cmd: list[str]) -> int:
    """Pre-scan, run ``cmd``, post-scan. Return the worst exit code."""
    # `argparse.REMAINDER` swallows the conventional `--` separator
    # (`pa1-lint guard -- aider ...`), leaving it as argv[0] and making
    # subprocess raise FileNotFoundError. Normalise it away here so every
    # caller is safe, not just the one that went through the CLI.
    cmd = list(cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        sys.stderr.write("[pa1-guard] no command given; nothing to run.\n")
        return 2
    cwd = Path.cwd()
    if not (cwd / ".git").exists():
        sys.stderr.write(
            "[pa1-guard] not a git repo; running command without guard.\n"
        )
        proc = subprocess.run(cmd, cwd=str(cwd))
        return proc.returncode

    pre_text = _git_diff_text(cwd)
    pre_findings = _scan_diff_text(pre_text)
    if _has_high_plus(pre_findings):
        sys.stderr.write(
            "[pa1-guard] BLOCKED: pre-scan found HIGH+ findings. "
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
        # The command created commits - diff old HEAD..new HEAD so the
        # committed content is actually inspected.
        post_text = _diff_added_lines(cwd, [pre_head, post_head])
    else:
        post_text = _git_diff_text(cwd)
    post_findings = _scan_diff_text(post_text)
    pre_masks = {f.evidence_raw for f in pre_findings}
    new = [f for f in post_findings if f.evidence_raw not in pre_masks]
    if _has_high_plus(new):
        sys.stderr.write(
            "[pa1-guard] BLOCKED: post-scan found new HIGH+ findings "
            "introduced by the command.\n"
        )
        sys.stderr.write(render_markdown(_fake_result(new)))
        return 2

    return 0