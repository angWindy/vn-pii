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