"""Generate synthetic CSV/JSONL fixtures for PII tests and demos.

Run inside the ``pii`` conda env:

    python fixtures/generators/make_synthetic.py --out fixtures/gold fixtures/negative

All data is FAKE (Faker, vi_VN + en_US, seed=42). Card numbers pass Luhn.
VINs are 17 chars with no I/O/Q.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

from faker import Faker

_FAKE_VI = Faker("vi_VN")
_FAKE_EN = Faker("en_US")
_SEED = 42


def _reset_seed() -> None:
    _FAKE_VI.seed_instance(_SEED)
    _FAKE_EN.seed_instance(_SEED)
    random.seed(_SEED)


# --- Helpers --------------------------------------------------------------


def make_card_luhn(prefix: str) -> str:
    """Return a card number starting with `prefix` that passes Luhn."""
    base = prefix
    while len(base) < 15:
        base += str(random.randint(0, 9))
    base = base[:15]
    digits = [int(c) for c in base]
    checksum = 0
    parity = (len(digits) - 2) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    check = (10 - (checksum % 10)) % 10
    return base + str(check)


def make_vin() -> str:
    """Return a fake 17-char VIN (no I/O/Q)."""
    alphabet = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
    return "".join(random.choice(alphabet) for _ in range(17))


def make_plate() -> str:
    return f"{random.randint(11, 99)}{random.choice('ABCDEFGHJKLM')}-{random.randint(100, 999)}.{random.randint(10, 99)}"


def make_vn_phone() -> str:
    return "0" + "".join(str(random.randint(0, 9)) for _ in range(9))


def make_cccd() -> str:
    return "0" + "".join(str(random.randint(0, 9)) for _ in range(11))


def make_email() -> str:
    return _FAKE_EN.email().lower()


def make_customer_id(i: int) -> str:
    return f"id_{i:04d}"


# --- Gold (with PII) ------------------------------------------------------


def make_leads(n: int) -> list[dict]:
    out = []
    for i in range(1, n + 1):
        out.append({
            "customer_id": make_customer_id(i),
            "name": _FAKE_VI.name(),
            "phone": make_vn_phone(),
            "email": make_email(),
            "note": f"Anh/chị {_FAKE_VI.name()} mua xe {random.choice(['Vios', 'Accent', 'Morning'])} ngày {_FAKE_VI.date_this_year()}.",
        })
    return out


def make_contracts(n: int) -> list[dict]:
    out = []
    for i in range(1, n + 1):
        out.append({
            "customer_id": make_customer_id(i),
            "name": _FAKE_VI.name(),
            "cccd": make_cccd(),
            "account_no": "".join(str(random.randint(0, 9)) for _ in range(10)),
            "sign_date": str(_FAKE_VI.date_this_year()),
        })
    return out


def make_service(n: int) -> list[dict]:
    out = []
    for i in range(1, n + 1):
        out.append({
            "customer_id": make_customer_id(i),
            "vin": make_vin(),
            "plate": make_plate(),
            "note": f"Bảo dưỡng định kỳ {_FAKE_VI.name()}, SĐT {make_vn_phone()}.",
        })
    return out


def make_finance(n: int) -> list[dict]:
    out = []
    for i in range(1, n + 1):
        out.append({
            "customer_id": make_customer_id(i),
            "card_no": make_card_luhn("4111"),
            "amount": round(random.uniform(100, 5000), 2),
        })
    return out


def make_notes(n: int) -> list[dict]:
    out = []
    for i in range(1, n + 1):
        out.append({
            "customer_id": make_customer_id(i),
            "note": f"Liên hệ {_FAKE_VI.name()}, SĐT {make_vn_phone()}, CCCD {make_cccd()}, zalo.me/{random.randint(100000, 999999999)}.",
        })
    return out


# --- Negative (no PII) ----------------------------------------------------


def make_negative_crm(n: int) -> list[dict]:
    out = []
    for i in range(1, n + 1):
        out.append({
            "customer_id": make_customer_id(i),
            "phone": f"dummy_{i:04d}",
            "email": f"dummy_{i:04d}@example.com",
            "stage": random.choice(["new", "qualified", "won", "lost"]),
        })
    return out


def make_negative_aggregate(n: int) -> list[dict]:
    out = []
    for i in range(1, n + 1):
        out.append({
            "account_no": "0",
            "tx_count": random.randint(0, 50),
            "total_amount": round(random.uniform(0, 10000), 2),
        })
    return out


# --- Writers --------------------------------------------------------------


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    headers = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", nargs="+", required=True,
                        help="Output roots: 'gold' and/or 'negative'.")
    parser.add_argument("--n", type=int, default=50)
    args = parser.parse_args(argv)

    _reset_seed()
    n = args.n
    roots = {a.lower() for a in args.out}

    if "gold" in roots:
        g = Path("fixtures/gold")
        g.mkdir(parents=True, exist_ok=True)
        _write_csv(g / "leads_50.csv", make_leads(n))
        _write_csv(g / "contracts_50.csv", make_contracts(n))
        _write_csv(g / "service_50.csv", make_service(n))
        _write_csv(g / "finance_50.csv", make_finance(n))
        _write_jsonl(g / "notes_50.jsonl", make_notes(n))
        print(f"[gold] wrote {n} rows x 5 files", file=sys.stderr)

    if "negative" in roots:
        n_root = Path("fixtures/negative")
        n_root.mkdir(parents=True, exist_ok=True)
        _write_csv(n_root / "crm_pipeline_50.csv", make_negative_crm(n))
        _write_csv(n_root / "aggregate_50.csv", make_negative_aggregate(n))
        print(f"[negative] wrote {n} rows x 2 files", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())