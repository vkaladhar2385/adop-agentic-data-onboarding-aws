# spec_hash: 403eb7c8a867aaaa6d0fdfd837b06c5a2dab188826687f85b43f5e73155eb36a
# template_id: bronze_to_silver
# template_hash: c6f15b6ef331ad1d26cc71e5325b358ae328195907ba1d5fbf85de6e3ce33edb
# schema_version: v1
# rendered_at: 2026-10-01T23:26:46Z
"""Bronze -> Silver transform for `azure_demo` (Azure Synapse Spark).

Reads Bronze from ADLS Gen2 (abfss://), writes Apache Iceberg to the Silver
catalog table, and exports Parquet for the Python quality gate. Local mode uses
pandas for unit tests. Transform rules come from transformations.yaml.
Source format: csv.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_self = Path(__file__).resolve()
_REPO_ROOT = _self.parents[4] if len(_self.parents) > 4 else _self.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from workloads.azure_demo.scripts.transform import local_runner, spark_transforms
except ImportError:  # pragma: no cover - local/demo fallback
    local_runner = None  # type: ignore
    spark_transforms = None  # type: ignore

DATABASE = "azure_demo_db"
SILVER_TABLE = "silver_azure_demo"


def run_local(bronze_parquet: str, out_dir: str) -> dict:
    import pandas as pd

    cfg = local_runner.load_config("transformations.yaml")
    bronze = pd.read_parquet(bronze_parquet)
    silver, quarantine = local_runner.bronze_to_silver(bronze, cfg)

    out = Path(out_dir)
    (out / "silver").mkdir(parents=True, exist_ok=True)
    (out / "quarantine").mkdir(parents=True, exist_ok=True)
    silver.to_parquet(out / "silver" / "silver_azure_demo.parquet", index=False)
    quarantine.to_csv(out / "quarantine" / "quarantine.csv", index=False)
    print(f"[silver] clean rows: {len(silver)}  |  quarantined: {len(quarantine)}")
    return {"silver": silver, "quarantine": quarantine}


def run_synapse_spark():  # pragma: no cover - requires Synapse Spark pool
    """Synapse Spark entrypoint. Args: --bronze_path --silver_path (abfss://)."""
    from pyspark.sql import SparkSession

    ap = argparse.ArgumentParser()
    ap.add_argument("--bronze_path", required=True, help="abfss:// path to Bronze")
    ap.add_argument("--silver_path", required=True, help="abfss:// warehouse root for Silver")
    args, _ = ap.parse_known_args()

    spark = (
        SparkSession.builder.appName("azure_demo_bronze_to_silver")
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        .config("spark.sql.catalog.spark_catalog", "org.apache.iceberg.spark.SparkSessionCatalog")
        .config("spark.sql.catalog.spark_catalog.type", "hadoop")
        .config("spark.sql.catalog.spark_catalog.warehouse", args.silver_path)
        .getOrCreate()
    )

    bronze_df = spark.read.parquet(args.bronze_path)
    input_rows = bronze_df.count()

    if spark_transforms is not None:
        silver_df, quarantine_df = spark_transforms.bronze_to_silver_df(bronze_df)
    else:
        silver_df, quarantine_df = bronze_df, bronze_df.limit(0)

    silver_df.writeTo(f"{DATABASE}.{SILVER_TABLE}").using("iceberg").createOrReplace()

    export_path = f"{args.silver_path.rstrip('/')}/quality_export"
    silver_df.write.mode("overwrite").parquet(export_path)
    print(f"[silver] input={input_rows} -> iceberg {DATABASE}.{SILVER_TABLE}; export={export_path}")
    spark.stop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--bronze", default="output/azure_demo/bronze/bronze_azure_demo.parquet")
    ap.add_argument("--out", default="output/azure_demo")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.bronze, args.out)
    else:
        run_synapse_spark()
