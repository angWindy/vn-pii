"""Markdown reporter and per-entity mask helpers for PA1.

The mask functions are deliberately separate from ``Finding`` so they can be
unit-tested in isolation and reused by other reporters (JSON, SARIF).
"""

from __future__ import annotations

from typing import Iterable

from pii_linter import Finding, ScanResult
from pii_linter.severity import (
    CRITICAL,
    HIGH,
    LOW,
    MEDIUM,
)


_SUGGESTION_BY_ENTITY = {
    "PERSON":     "Replace with synthetic_id (e.g. id_0001) or initials.",
    "PHONE":      "Replace with dummy_<n> or redact to ***.",
    "EMAIL":      "Replace with dummy@example.com or redact local-part.",
    "ID_NUMBER":  "Replace with synthetic 12-digit; never store CCCD in plain text.",
    "ACCOUNT_NO": "Replace with synthetic or tokenize at gateway.",
    "CARD_NO":    "TOKENIZE at gateway; do not store PAN.",
    "ASSET":      "Replace VIN/plate with synthetic or hash.",
    "NOTE":       "Move free-text into a redacted notes column.",
    "URL_HANDLE": "Replace social handle with synthetic.",
    "COMBO":      "Row contains multiple HIGH+ entities — split or tokenize.",
}


def _mask_phone(raw: str) -> str:
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) < 4:
        return "****"
    return digits[:2] + "****" + digits[-3:]


def _mask_id(raw: str) -> str:
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) < 2:
        return "****"
    return "****-****-***-" + digits[-2:]


def _mask_email(raw: str) -> str:
    if "@" not in raw:
        return "***"
    local, _, domain = raw.partition("@")
    if len(local) <= 2:
        masked_local = "***"
    else:
        # 1 letter on, 1 off to keep shape.
        masked_local = ".".join(local[::2])[:1] + "." + ".".join(local[1::2])[:1]
    return f"{masked_local}@{domain}"


def _mask_card(raw: str) -> str:
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) <= 4:
        return "****"
    return "****-****-****-" + digits[-4:]


def _mask_person(raw: str) -> str:
    parts = raw.split()
    if not parts:
        return "***"
    masked = [parts[0][:1] + "***" if len(p) > 1 else "***" for p in parts[:2]]
    return " ".join(masked)


def _mask_default(raw: str) -> str:
    if len(raw) <= 4:
        return "***"
    return raw[:2] + "***" + raw[-2:]


def mask_value(value: str, entity: str) -> str:
    """Return a deterministic, display-safe mask for ``value`` based on ``entity``."""
    if not value:
        return ""
    m = {
        "PHONE":      _mask_phone,
        "ID_NUMBER":  _mask_id,
        "EMAIL":      _mask_email,
        "CARD_NO":    _mask_card,
        "PERSON":     _mask_person,
    }.get(entity, _mask_default)
    return m(value)


def _row(findings: Iterable[Finding]) -> str:
    rows = []
    for f in findings:
        if f.file and f.line_no:
            cursor = f"{f.file}:{f.line_no}"
        else:
            cursor = ""
        rows.append(
            f"| {cursor or '`—`'} | {f.entity} | {f.severity} | `{f.evidence_masked}` |"
        )
    return "\n".join(rows)


def _any_diff_mode(result: ScanResult) -> bool:
    """True if any finding carries a file/line cursor (i.e. --staged output)."""
    return any(f.file and f.line_no for f in result.findings)


def render_markdown(result: ScanResult) -> str:
    """Render a Markdown report grouped by file."""
    lines: list[str] = []
    lines.append("# PA1 PII scan report")
    lines.append("")
    lines.append(f"- files_scanned: {result.files_scanned}")
    lines.append(f"- total_findings: {len(result.findings)}")
    by_sev = {LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 0}
    for f in result.findings:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
    lines.append(
        f"- severity_counts: LOW={by_sev[LOW]}, MEDIUM={by_sev[MEDIUM]}, "
        f"HIGH={by_sev[HIGH]}, CRITICAL={by_sev[CRITICAL]}"
    )
    if _any_diff_mode(result):
        lines.append("- mode: staged-diff")
    lines.append("")
    header_extra = " location |" if _any_diff_mode(result) else ""
    for path, findings in result.by_file.items():
        lines.append(f"## {path}")
        lines.append("")
        lines.append(f"|{header_extra} entity | severity | evidence_masked |")
        sep = "---|" + ("---|" if header_extra else "")
        lines.append(f"|{sep}---|---|---|")
        lines.append(_row(findings))
        lines.append("")
        max_sev = max(f.severity for f in findings) if findings else LOW
        if max_sev >= HIGH:
            unique_ents = sorted({f.entity for f in findings})
            suggs = sorted({_SUGGESTION_BY_ENTITY.get(e, "") for e in unique_ents})
            suggs = [s for s in suggs if s]
            if suggs:
                lines.append(f"> **Suggestions:** {' '.join(suggs)}")
                lines.append("")
    if not result.by_file:
        lines.append("_No files to check._")
    return "\n".join(lines) + "\n"