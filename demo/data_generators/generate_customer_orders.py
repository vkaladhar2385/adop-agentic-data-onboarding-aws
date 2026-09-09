#!/usr/bin/env python3
"""Generate sample customer_orders CSV for local demo and profiling."""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "sample_data" / "customer_orders.csv"
STATUSES = ["pending", "shipped", "delivered", "cancelled"]


def main() -> None:
    random.seed(42)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    base = date(2026, 1, 1)
    rows = []
    for i in range(1, 101):
        qty = random.randint(1, 5)
        unit = round(random.uniform(10.0, 250.0), 2)
        rows.append(
            {
                "order_id": f"ORD-{i:05d}",
                "customer_id": f"CUST-{random.randint(1000, 1099)}",
                "product_sku": f"SKU-{random.randint(100, 199)}",
                "quantity": qty,
                "order_date": (base + timedelta(days=i % 30)).isoformat(),
                "order_status": random.choice(STATUSES),
                "order_total": round(qty * unit, 2),
                "updated_at": f"{(base + timedelta(days=i % 30)).isoformat()}T12:00:00Z",
            }
        )

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    main()
