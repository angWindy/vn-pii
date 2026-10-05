"""Luhn-validated credit card detector for PA1.

A finding is emitted only when:
  1. The value (after stripping common separators) is 13–19 digits.
  2. It passes the Luhn checksum (ISO/IEC 7812).
  3. The BIN prefix is in the known-card-network table.
"""

from __future__ import annotations

import re

from pii_linter import Finding
from pii_linter.severity import SEVERITY_BY_ENTITY


# Strip spaces, dashes; standardise 16-digit PAN.
_RE_PAN = re.compile(r"\b(?:\d[\d \-]{11,22}\d|\d{13,19})\b")

# Phone / email / CCCD. Not used to *detect* anything here -- `detect_card`
# only fires on a Luhn-valid PAN. This exists so the CARD_NO evidence mask can
# also redact other PII that happens to share the same cell, which would
# otherwise be printed verbatim next to the masked PAN.
_RE_OTHER_PII = re.compile(
    r"(?:\+84|0)\d{9}\b"
    r"|\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
    r"|\b0\d{11}\b"
)


# BIN prefix -> network. Only major brands.
_BIN_TABLE: dict[str, str] = {
    "4":    "Visa",
    "51":   "Mastercard",
    "52":   "Mastercard",
    "53":   "Mastercard",
    "54":   "Mastercard",
    "55":   "Mastercard",
    "34":   "Amex",
    "37":   "Amex",
    "35":   "JCB",
    "2131": "JCB",
    "1800": "JCB",
}


def luhn_check(pan: str) -> bool:
    """Return True if ``pan`` (digits only) passes the Luhn checksum."""
    digits = [int(c) for c in pan if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    parity = (len(digits) - 2) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _bin_network(pan: str) -> str | None:
    """Return the card network for the longest matching BIN prefix, else None."""
    for length in (4, 2, 1):
        prefix = pan[:length]
        if prefix in _BIN_TABLE:
            return _BIN_TABLE[prefix]
    return None


def detect_card(value: str) -> Finding | None:
    """Return a CRITICAL Finding if ``value`` looks like a real card number, else None."""
    if not value:
        return None
    for m in _RE_PAN.finditer(value):
        raw = m.group(0)
        digits = "".join(c for c in raw if c.isdigit())
        if not luhn_check(digits):
            continue
        network = _bin_network(digits)
        if network is None:
            continue
        # Mask the PAN *and* any other PII sharing the cell. A line like
        # "4111111111111111,0912345678" used to report the phone verbatim in
        # the CARD_NO evidence. `_redact_all` is imported lazily (content_regex
        # already imports this module's package root) to avoid a cycle.
        from pii_linter.detectors.content_regex import _redact_all

        spans = [(m.start(), m.end())]
        spans += [(o.start(), o.end()) for o in _RE_OTHER_PII.finditer(value)]
        return Finding(
            entity="CARD_NO",
            severity=SEVERITY_BY_ENTITY["CARD_NO"],
            evidence_raw=raw,
            # Trailing [network] is metadata, not PII, so it stays readable.
            evidence_masked=f"{_redact_all(value, spans)} [{network}]",
            span=(m.start(), m.end()),
        )
    return None