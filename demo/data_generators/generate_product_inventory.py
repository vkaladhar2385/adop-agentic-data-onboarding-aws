"""Synthetic data generator for the `product_inventory` factory-proof workload.

Deterministic SKU snapshot (~200 rows) plus a few dirty rows so quality gates
have something to catch. No AWS, no real catalog data.

Usage:
    python demo/data_generators/generate_product_inventory.py \
        --rows 200 --out demo/sample_data/product_inventory.csv
"""
from __future__ import annotations

import argparse
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

CATEGORIES = ["ELECTRONICS", "APPAREL", "HOME", "GROCERY", "SPORTS"]
WAREHOUSES = ["WH-EAST-01", "WH-WEST-02", "WH-CENTRAL-03"]
STATUSES = ["ACTIVE", "ACTIVE", "ACTIVE", "ACTIVE", "DISCONTINUED"]
SUPPLIERS = [
    ("SUP-100", "Northwind Goods"),
    ("SUP-200", "Contoso Supply"),
    ("SUP-300", "Fabrikam Parts"),
]
PRODUCTS = [
    ("Wireless Mouse", "ELECTRONICS"),
    ("USB-C Cable", "ELECTRONICS"),
    ("Crew Socks", "APPAREL"),
    ("Denim Jacket", "APPAREL"),
    ("Floor Lamp", "HOME"),
    ("Coffee Mug", "HOME"),
    ("Oat Granola", "GROCERY"),
    ("Sparkling Water", "GROCERY"),
    ("Yoga Mat", "SPORTS"),
    ("Tennis Balls", "SPORTS"),
]

HEADER = [
    "sku",
    "product_name",
    "category",
    "warehouse_id",
    "on_hand_qty",
    "reserved_qty",
    "unit_cost",
    "list_price",
    "supplier_id",
    "supplier_name",
    "status",
    "updated_at",
    "ingestion_date",
]


def _money(x: float) -> str:
    return f"{x:.2f}"


def generate(rows: int, seed: int, ingestion_day: date) -> list[dict]:
    rng = random.Random(seed)
    records: list[dict] = []
    for i in range(1, rows + 1):
        name, category = PRODUCTS[(i - 1) % len(PRODUCTS)]
        variant = ((i - 1) // len(PRODUCTS)) + 1
        sku = f"SKU{i:06d}"
        on_hand = rng.randint(0, 500)
        reserved = rng.randint(0, min(40, on_hand) if on_hand else 0)
        unit_cost = round(rng.uniform(2.0, 80.0), 2)
        list_price = round(unit_cost * rng.uniform(1.15, 1.8), 2)
        supplier_id, supplier_name = rng.choice(SUPPLIERS)
        updated = datetime(
            ingestion_day.year,
            ingestion_day.month,
            ingestion_day.day,
            rng.randint(0, 23),
            rng.randint(0, 59),
            0,
        ) - timedelta(hours=rng.randint(0, 48))
        records.append(
            {
                "sku": sku,
                "product_name": f"{name} v{variant}",
                "category": category,
                "warehouse_id": rng.choice(WAREHOUSES),
                "on_hand_qty": str(on_hand),
                "reserved_qty": str(reserved),
                "unit_cost": _money(unit_cost),
                "list_price": _money(list_price),
                "supplier_id": supplier_id,
                "supplier_name": supplier_name,
                "status": rng.choice(STATUSES),
                "updated_at": updated.strftime("%Y-%m-%dT%H:%M:%S"),
                "ingestion_date": ingestion_day.isoformat(),
            }
        )
    _inject_dirty_rows(records)
    return records


def _inject_dirty_rows(records: list[dict]) -> None:
    if len(records) < 10:
        return
    dup = dict(records[0])
    dup["on_hand_qty"] = str(int(dup["on_hand_qty"]) + 25)
    dup["updated_at"] = (
        datetime.fromisoformat(dup["updated_at"]) - timedelta(hours=6)
    ).strftime("%Y-%m-%dT%H:%M:%S")
    records.append(dup)
    records[1]["sku"] = ""
    records[2]["on_hand_qty"] = "-8"
    records[3]["product_name"] = ""
    records[4]["list_price"] = _money(float(records[4]["unit_cost"]) - 1.00)
    records[5]["reserved_qty"] = str(int(records[5]["on_hand_qty"]) + 15)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic product inventory")
    ap.add_argument("--rows", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--date", default=date(2026, 9, 8).isoformat())
    ap.add_argument("--out", default="demo/sample_data/product_inventory.csv")
    args = ap.parse_args()

    records = generate(args.rows, args.seed, date.fromisoformat(args.date))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(records)
    print(f"Wrote {len(records)} rows -> {out_path}")


if __name__ == "__main__":
    main()
