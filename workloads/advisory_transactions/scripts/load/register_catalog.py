"""Catalog registration + LF-Tag application for `advisory_transactions`.

Production: registers Silver/Gold Iceberg tables in the Glue Data Catalog and
applies Lake Formation LF-Tags on PII columns for tag-based access control
(TBAC). Local mode: prints the plan (the tables/columns that would be tagged)
so the demo can show governance intent without touching AWS.

This module is also the AWS Lambda entrypoint invoked by the Step Functions
`RegisterCatalog` state (`lambda_handler`). It intentionally avoids importing
the pandas-based `local_runner` module so the Lambda deployment package stays
small (pyyaml + boto3 only) -- see docs/ARCHITECTURE.md#packaging.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import sys
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.utils.pii import PII_CLASSIFICATION  # noqa: E402

WORKLOAD = "advisory_transactions"
SILVER_TABLE = "silver_advisory_transactions"
GOLD_FACT_TABLE = "fact_transactions"

# Only these columns are actually present on this workload's Silver table
# (see config/semantic.yaml). PII_CLASSIFICATION is shared across workloads,
# so each workload's register_catalog scopes it down to its own columns.
_ADVISORY_PII_COLUMNS = {"client_ssn", "client_email", "client_name"}

# Hardcoded rather than inferred from the Parquet file at registration time:
# this Lambda deliberately stays pandas/pyarrow-free (see module docstring),
# and the schema is fixed for this pilot (see config/semantic.yaml). A
# generic multi-workload version would infer this via a Glue Crawler instead.
_SILVER_COLUMNS = [
    ("transaction_id", "string"), ("account_id", "string"), ("advisor_id", "string"),
    ("client_id", "string"), ("client_name", "string"), ("client_email", "string"),
    ("client_ssn", "string"), ("security_id", "string"), ("security_name", "string"),
    ("asset_class", "string"), ("transaction_type", "string"), ("trade_date", "date"),
    ("settlement_date", "date"), ("quantity", "double"), ("unit_price", "double"),
    ("gross_amount", "double"), ("commission", "double"), ("fees", "double"),
    ("net_amount", "double"), ("currency", "string"), ("account_type", "string"),
    ("advisor_name", "string"), ("branch_code", "string"), ("ingestion_date", "string"),
    ("trade_year", "bigint"), ("trade_month", "bigint"),
]
_GOLD_FACT_COLUMNS = [
    ("transaction_id", "string"), ("account_id", "string"), ("advisor_id", "string"),
    ("security_id", "string"), ("trade_date", "date"), ("quantity", "double"),
    ("unit_price", "double"), ("gross_amount", "double"), ("commission", "double"),
    ("fees", "double"), ("net_amount", "double"),
]


def plan_lf_tags(database: str | None = None) -> list[dict]:
    if database is None:
        # CLI/local/test path only -- lazy import so the Lambda path never
        # needs pandas just to read a database name.
        from workloads.advisory_transactions.scripts.transform import local_runner
        src = local_runner.load_config("source.yaml")
        database = src["zones"]["silver"]["database"]
    tags = []
    for column, (pii_type, sensitivity) in PII_CLASSIFICATION.items():
        if column not in _ADVISORY_PII_COLUMNS:
            continue
        tags.append({
            "database": database,
            "table": SILVER_TABLE,
            "column": column,
            "lf_tags": {"PII_Type": pii_type, "Data_Sensitivity": sensitivity},
        })
    return tags


def run_local() -> None:
    print("[load] Glue catalog registration plan (Iceberg):")
    for zone in ("silver", "gold"):
        print(f"  - register {zone} tables from sql/{zone}/*.sql")
    print("[load] Lake Formation LF-Tag plan (TBAC on PII columns):")
    for t in plan_lf_tags():
        print(f"  - {t['table']}.{t['column']} -> {t['lf_tags']}")
    print("[load] NOTE: Gold suppresses SSN/email/name entirely (no tags needed).")


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


def register_tables(database: str, bucket: str) -> list[dict]:  # pragma: no cover - requires AWS
    """Idempotently registers the Silver table and the Gold fact table in the
    Glue Data Catalog, pointing at the Parquet this pilot's Glue jobs already
    wrote (see docs/ARCHITECTURE.md#packaging -- a real deployment would
    register Iceberg tables instead of plain Parquet-on-S3)."""
    import boto3
    glue = boto3.client("glue")
    tables = [
        (SILVER_TABLE, f"s3://{bucket}/silver/{WORKLOAD}/", _SILVER_COLUMNS),
        (GOLD_FACT_TABLE, f"s3://{bucket}/gold/{WORKLOAD}/{GOLD_FACT_TABLE}/", _GOLD_FACT_COLUMNS),
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


def apply_lf_tags(tags: list[dict]) -> list[dict]:  # pragma: no cover - requires AWS
    """Associate pre-provisioned LF-Tags to columns (keys/values created via IaC)."""
    import boto3
    lf = boto3.client("lakeformation")
    results = []
    for t in tags:
        try:
            lf_tags = [{"TagKey": k, "TagValues": [v]} for k, v in t["lf_tags"].items()]
            lf.add_lf_tags_to_resource(
                Resource={"TableWithColumns": {
                    "DatabaseName": t["database"],
                    "Name": t["table"],
                    "ColumnNames": [t["column"]],
                }},
                LFTags=lf_tags,
            )
            results.append({**t, "status": "applied"})
        except Exception as exc:  # noqa: BLE001
            results.append({**t, "status": "failed", "error": str(exc)})
    return results


def run_glue():  # pragma: no cover - requires AWS
    """Production path via glue-athena + lakeformation MCP servers / boto3."""
    raise SystemExit("Catalog registration runs against AWS; use --local for the demo.")


def lambda_handler(event: dict, context) -> dict:  # pragma: no cover - requires AWS
    """Step Functions `RegisterCatalog` task target.

    event = {"action": "register_and_tag", "database": "<optional override>"}
    """
    database = (event or {}).get("database") or os.environ.get("GLUE_DATABASE")
    bucket = (event or {}).get("data_lake_bucket") or os.environ.get("DATA_LAKE_BUCKET")
    tags = plan_lf_tags(database=database)
    try:
        import boto3  # noqa: F401
        # Iceberg tables are registered by Glue ETL commits — do not overwrite with Parquet DDL.
        table_results = []
        if (event or {}).get("register_tables") and bucket:
            table_results = register_tables(database, bucket)
        results = apply_lf_tags(tags)
    except ImportError:
        table_results = []
        results = [{**t, "status": "planned (boto3 unavailable, dry-run)"} for t in tags]
    failed = [r for r in results if r["status"] == "failed"] + [r for r in table_results if r["status"] == "failed"]
    if failed:
        print(f"[register_catalog] warnings: {failed}")
    return {
        "workload": WORKLOAD, "tables": table_results,
        "tagged": len(results), "failed": len(failed), "results": results,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()
    run_local() if args.local else run_glue()
