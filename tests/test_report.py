"""Tests for pii_linter.report masking helpers."""

from pii_linter.report import mask_value


def test_mask_email_short_local() -> None:
    """Local-part of ≤2 chars gets fully masked."""
    assert mask_value("ab@example.com", "EMAIL") == "***@example.com"


def test_mask_email_long_local_keeps_all_chars() -> None:
    """Regression: prior impl silently truncated via [:1]; must keep full shape.

    'nguyen' has 6 chars; on-step (i=0,2,4) = 'n,u,e', off-step (i=1,3,5)
    = 'g,y,n'. Joined with '.' for readability.
    """
    out = mask_value("nguyen@example.com", "EMAIL")
    assert out == "n.u.e.g.y.n@example.com"


def test_mask_email_long_alphanumeric_local() -> None:
    out = mask_value("anthang2003@example.com", "EMAIL")
    # local = a,n,t,h,a,n,g,2,0,0,3
    # on  (i=0,2,4,6,8,10): a,t,a,g,0,3     -> "a.t.a.g.0.3"
    # off (i=1,3,5,7,9):    n,h,n,2,0       -> "n.h.n.2.0"
    assert out == "a.t.a.g.0.3.n.h.n.2.0@example.com"


def test_mask_email_no_at_sign() -> None:
    assert mask_value("not-an-email", "EMAIL") == "***"


def test_mask_email_preserves_domain() -> None:
    """Domain part must never be redacted (PII lives in local-part)."""
    assert "important.gov.vn" in mask_value("a@b.important.gov.vn", "EMAIL")


def test_mask_value_other_entities_unaffected() -> None:
    """Sanity check: phone mask still works as before."""
    assert "09" in mask_value("0912345678", "PHONE")
    assert "678" in mask_value("0912345678", "PHONE")


def test_table_cells_match_header_in_both_modes() -> None:
    """Every emitted row must have as many cells as the header.

    Regression: whole-file mode emitted a 3-cell header above 4-cell rows
    (a stray `—` cursor cell), and the separator row always had 4 columns
    regardless of mode. Both render as a broken table in Markdown.
    """
    from pii_linter import Finding, ScanResult
    from pii_linter.report import render_markdown

    def widths(report: str) -> set[int]:
        return {row.count("|") for row in report.splitlines() if row.startswith("|")}

    def one(line_no: int = 0) -> list[Finding]:
        return [
            Finding(
                entity="PHONE",
                severity=3,
                evidence_raw="x",
                evidence_masked="***",
                span=(0, 1),
                file="d.csv",
                line_no=line_no,
            )
        ]

    # Whole-file mode: no file/line cursor, so no location column.
    plain = render_markdown(
        ScanResult(findings=one(), files_scanned=1, by_file={"d.csv": one()})
    )
    # header, separator and the single data row must all agree.
    assert widths(plain) == {4}

    # Diff mode: findings carry a cursor, so the location column appears.
    diff = render_markdown(
        ScanResult(findings=one(2), files_scanned=2, by_file={"d.csv": one(2)})
    )
    assert widths(diff) == {5}