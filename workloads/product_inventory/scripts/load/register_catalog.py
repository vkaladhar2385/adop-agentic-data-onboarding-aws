"""Catalog registration for `product_inventory` (no PII LF-Tags)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

WORKLOAD = "product_inventory"
SILVER_TABLE = "silver_product_inventory"
GOLD_TABLE = "gold_product_inventory"

_SILVER_COLUMNS = [
    ("sku", "string"),
    ("product_name", "string"),
    ("category", "string"),
    ("warehouse_id", "string"),
    ("on_hand_qty", "bigint"),
    ("reserved_qty", "bigint"),
    ("unit_cost", "double"),
    ("list_price", "double"),
    ("supplier_id", "string"),
    ("supplier_name", "string"),
    ("status", "string"),
    ("updated_at", "timestamp"),
    ("ingestion_date", "string"),
    ("available_qty", "bigint"),
    ("inventory_value", "double"),
    ("margin_pct", "double"),
]
_GOLD_COLUMNS = list(_SILVER_COLUMNS)


def plan_lf_tags(database: str | None = None) -> list[dict]:
    return []


def run_local() -> None:
    print("[load] Glue catalog registration plan (Iceberg):")
    for zone in ("silver", "gold"):
        print(f"  - register {zone} tables from sql/{zone}/*.sql")
    print("[load] Lake Formation LF-Tag plan: none (no PII columns).")


def _glue_table_input(name: str, s3_location: str, columns: list[tuple[str, str]]) -> dict:
    return {
        "Name": name,
        "StorageDescriptor": {
            "Columns": [{"Name": c, "Type": t} for c, t in columns],
            "Location": s3_location,
            "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
            "SerdeInfo": {"SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"},
        },
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {"classification": "parquet"},
    }


def register_tables(database: str, bucket: str) -> list[dict]:  # pragma: no cover
    import boto3

    glue = boto3.client("glue")
    tables = [
        (SILVER_TABLE, f"s3://{bucket}/silver/{WORKLOAD}/", _SILVER_COLUMNS),
        (GOLD_TABLE, f"s3://{bucket}/gold/{WORKLOAD}/{GOLD_TABLE}/", _GOLD_COLUMNS),
    ]
    results = []
    for name, location, columns in tables:
        table_input = _glue_table_input(name, location, columns)
        try:
            glue.create_table(DatabaseName=database, TableInput=table_input)
            results.append({"table": name, "status": "created"})
        except glue.exceptions.AlreadyExistsException:
            glue.update_table(DatabaseName=database, TableInput=table_input)
            results.append({"table": name, "status": "updated"})
        except Exception as exc:  # noqa: BLE001
            results.append({"table": name, "status": "failed", "error": str(exc)})
    return results


def lambda_handler(event: dict, context) -> dict:  # pragma: no cover
    database = (event or {}).get("database") or os.environ.get("GLUE_DATABASE")
    bucket = (event or {}).get("data_lake_bucket") or os.environ.get("DATA_LAKE_BUCKET")
    tags = plan_lf_tags(database=database)
    table_results = register_tables(database, bucket) if bucket else []
    return {
        "workload": WORKLOAD,
        "tables": table_results,
        "tagged": len(tags),
        "failed": len([r for r in table_results if r.get("status") == "failed"]),
        "results": tags,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()
    if args.local:
        run_local()
    else:
        raise SystemExit("Catalog registration runs against AWS; use --local for the demo.")
