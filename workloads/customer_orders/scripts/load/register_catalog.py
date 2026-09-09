"""Catalog registration for `customer_orders` (PII LF-Tags on customer_id)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

WORKLOAD = "customer_orders"
SILVER_TABLE = "silver_customer_orders"
GOLD_TABLE = "gold_customer_orders"


def plan_lf_tags(database: str | None = None) -> list[dict]:
    return [
        {
            "database": database or "customer_orders_db",
            "table": SILVER_TABLE,
            "tag_key": "pii",
            "tag_value": "true",
            "columns": ["customer_id"],
        }
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    tags = plan_lf_tags()
    print(f"[register_catalog] workload={WORKLOAD} tags={len(tags)} dry_run={args.dry_run}")
    if tags:
        for t in tags:
            print(t)


if __name__ == "__main__":
    main()
