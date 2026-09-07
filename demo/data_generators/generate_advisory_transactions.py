"""Synthetic data generator for the `advisory_transactions` demo workload.

Produces a deterministic CSV of daily brokerage / advisory transactions that
mimics what a wealth-management firm would land in S3 each day. The data is
intentionally seeded with a handful of *dirty* rows (bad dates, negative
amounts, broken SOX math, duplicate transaction ids, malformed PII) so the
downstream quality gates and quarantine logic have something to catch.

Nothing here touches AWS or real client data — it is 100% synthetic.

Usage:
    python demo/data_generators/generate_advisory_transactions.py \
        --rows 200 --out demo/sample_data/advisory_transactions.csv
"""
from __future__ import annotations

import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

SECURITIES = [
    ("AAPL", "Apple Inc.", "EQUITY"),
    ("MSFT", "Microsoft Corp.", "EQUITY"),
    ("VOO", "Vanguard S&P 500 ETF", "ETF"),
    ("VTSAX", "Vanguard Total Stock Mkt", "MUTUAL_FUND"),
    ("BND", "Vanguard Total Bond ETF", "BOND"),
    ("CASH", "Cash Sweep", "CASH"),
]
TXN_TYPES = ["BUY", "SELL", "DIVIDEND", "FEE"]
ACCOUNT_TYPES = ["BROKERAGE", "IRA", "ROTH_IRA", "401K"]
BRANCHES = ["BR-NYC-01", "BR-SFO-02", "BR-CHI-03", "BR-DAL-04"]
CURRENCIES = ["USD"]

FIRST_NAMES = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Linda", "David"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]

HEADER = [
    "transaction_id", "account_id", "advisor_id", "client_id",
    "client_name", "client_email", "client_ssn",
    "security_id", "security_name", "asset_class", "transaction_type",
    "trade_date", "settlement_date",
    "quantity", "unit_price", "gross_amount", "commission", "fees", "net_amount",
    "currency", "account_type", "advisor_name", "branch_code", "ingestion_date",
]


def _money(x: float) -> str:
    return f"{x:.2f}"


def generate(rows: int, seed: int, ingestion_day: date) -> list[dict]:
    rng = random.Random(seed)
    records: list[dict] = []
    for i in range(1, rows + 1):
        txn_id = f"TXN{i:07d}"
        acct_num = rng.randint(10001, 10050)
        advisor_num = rng.randint(501, 520)
        client_num = rng.randint(90001, 90080)
        sec_id, sec_name, asset_class = rng.choice(SECURITIES)
        txn_type = rng.choice(TXN_TYPES)

        trade_dt = ingestion_day - timedelta(days=rng.randint(0, 2))
        settle_dt = trade_dt + timedelta(days=2)  # T+2 settlement

        quantity = round(rng.uniform(1, 500), 2)
        unit_price = round(rng.uniform(5, 650), 2)
        gross = round(quantity * unit_price, 2)
        commission = round(gross * rng.uniform(0.0005, 0.002), 2)
        fees = round(rng.uniform(0.0, 3.0), 2)
        net = round(gross - commission - fees, 2)

        fn = rng.choice(FIRST_NAMES)
        ln = rng.choice(LAST_NAMES)
        name = f"{fn} {ln}"
        email = f"{fn.lower()}.{ln.lower()}{client_num}@example.com"
        ssn = f"{rng.randint(100, 899)}-{rng.randint(10, 99)}-{rng.randint(1000, 9999)}"

        records.append({
            "transaction_id": txn_id,
            "account_id": f"ACC{acct_num}",
            "advisor_id": f"ADV{advisor_num}",
            "client_id": f"CLI{client_num}",
            "client_name": name,
            "client_email": email,
            "client_ssn": ssn,
            "security_id": sec_id,
            "security_name": sec_name,
            "asset_class": asset_class,
            "transaction_type": txn_type,
            "trade_date": trade_dt.isoformat(),
            "settlement_date": settle_dt.isoformat(),
            "quantity": _money(quantity),
            "unit_price": _money(unit_price),
            "gross_amount": _money(gross),
            "commission": _money(commission),
            "fees": _money(fees),
            "net_amount": _money(net),
            "currency": rng.choice(CURRENCIES),
            "account_type": rng.choice(ACCOUNT_TYPES),
            "advisor_name": f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
            "branch_code": rng.choice(BRANCHES),
            "ingestion_date": ingestion_day.isoformat(),
        })

    _inject_dirty_rows(records, ingestion_day)
    return records


def _inject_dirty_rows(records: list[dict], ingestion_day: date) -> None:
    """Seed known data-quality defects so the pipeline has something to catch."""
    if len(records) < 10:
        return

    # 1) Duplicate transaction_id (uniqueness violation -> dedup should drop one)
    dup = dict(records[0])
    dup["net_amount"] = _money(float(dup["net_amount"]) + 1.00)  # stale copy
    records.append(dup)

    # 2) Broken SOX math: gross != quantity * unit_price (accuracy critical)
    records[2]["gross_amount"] = _money(float(records[2]["gross_amount"]) + 500.00)

    # 3) Broken SOX math: net != gross - commission - fees (consistency critical)
    records[3]["net_amount"] = _money(float(records[3]["net_amount"]) - 250.00)

    # 4) Invalid trade_date (validity critical -> quarantine)
    records[4]["trade_date"] = "2026-13-45"

    # 5) Negative quantity (validity critical -> quarantine)
    records[5]["quantity"] = "-10.00"

    # 6) Missing required field: net_amount null (completeness)
    records[6]["net_amount"] = ""

    # 7) Malformed email + SSN (PII validity -> flagged, still masked)
    records[7]["client_email"] = "not-an-email"
    records[7]["client_ssn"] = "000-00-0000"

    # 8) trade_date after settlement_date (validity)
    records[8]["settlement_date"] = (
        date.fromisoformat(records[8]["trade_date"]) - timedelta(days=1)
    ).isoformat()


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic advisory transactions")
    ap.add_argument("--rows", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--date", default=date(2026, 9, 3).isoformat(),
                    help="ingestion_date (YYYY-MM-DD)")
    ap.add_argument("--out", default="demo/sample_data/advisory_transactions.csv")
    args = ap.parse_args()

    ingestion_day = date.fromisoformat(args.date)
    records = generate(args.rows, args.seed, ingestion_day)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(records)

    print(f"Wrote {len(records)} rows -> {out_path}")


if __name__ == "__main__":
    main()
