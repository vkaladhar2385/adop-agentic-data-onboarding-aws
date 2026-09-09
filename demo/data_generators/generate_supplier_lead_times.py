"""Synthetic CSV for `supplier_lead_times` (Tier A workload #4 factory proof)."""
from __future__ import annotations

import argparse
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

CATEGORIES = ["ELECTRONICS", "APPAREL", "HOME", "RAW_MATERIALS"]
COUNTRIES = ["US", "CA", "MX", "DE", "CN"]
SUPPLIERS = [
    ("SUP-001", "Northwind Components"),
    ("SUP-002", "Contoso Manufacturing"),
    ("SUP-003", "Fabrikam Logistics"),
    ("SUP-004", "Adventure Works Supply"),
]

HEADER = [
    "supplier_id",
    "supplier_name",
    "product_category",
    "lead_time_days",
    "min_order_qty",
    "country_code",
    "is_preferred",
    "effective_date",
    "updated_at",
    "ingestion_date",
]


def generate(rows: int, seed: int, ingestion_day: date) -> list[dict]:
    rng = random.Random(seed)
    out: list[dict] = []
    for i in range(rows):
        sid, sname = rng.choice(SUPPLIERS)
        cat = rng.choice(CATEGORIES)
        lead = rng.randint(3, 45)
        updated = datetime.combine(ingestion_day, datetime.min.time()) + timedelta(hours=rng.randint(0, 12))
        out.append({
            "supplier_id": sid,
            "supplier_name": sname,
            "product_category": cat,
            "lead_time_days": str(lead),
            "min_order_qty": str(rng.randint(10, 500)),
            "country_code": rng.choice(COUNTRIES),
            "is_preferred": "true" if rng.random() < 0.25 else "false",
            "effective_date": ingestion_day.isoformat(),
            "updated_at": updated.isoformat(timespec="seconds"),
            "ingestion_date": ingestion_day.isoformat(),
        })
    # Dirty rows for quarantine / quality tests
    out.append({
        "supplier_id": "",
        "supplier_name": "Bad Supplier",
        "product_category": "ELECTRONICS",
        "lead_time_days": "10",
        "min_order_qty": "1",
        "country_code": "US",
        "is_preferred": "false",
        "effective_date": ingestion_day.isoformat(),
        "updated_at": updated.isoformat(timespec="seconds"),
        "ingestion_date": ingestion_day.isoformat(),
    })
    out.append({
        "supplier_id": "SUP-999",
        "supplier_name": "Slow Freight Co",
        "product_category": "HOME",
        "lead_time_days": "-5",
        "min_order_qty": "1",
        "country_code": "US",
        "is_preferred": "false",
        "effective_date": ingestion_day.isoformat(),
        "updated_at": updated.isoformat(timespec="seconds"),
        "ingestion_date": ingestion_day.isoformat(),
    })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=120)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="demo/sample_data/supplier_lead_times.csv")
    args = ap.parse_args()
    ingestion_day = date(2026, 9, 8)
    rows = generate(args.rows, args.seed, ingestion_day)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {out_path}")


if __name__ == "__main__":
    main()
