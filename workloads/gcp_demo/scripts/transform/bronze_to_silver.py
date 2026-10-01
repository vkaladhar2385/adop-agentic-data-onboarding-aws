# spec_hash: b4505b4e6e29aaa18455c71438110a423b704166a84e3bd9ddbd7f81b17a906c
# template_id: bronze_to_silver
# template_hash: fb9fe39d9ae3019791da4e2c91089c44bd79ef2de2b72955d6347e9f4ac1315e
# schema_version: v1
# rendered_at: 2026-10-01T23:35:13Z
"""Bronze -> Silver for `gcp_demo` (GCP Dataproc Spark).

Reads Bronze from GCS, writes Iceberg Silver, exports Parquet for quality gate.
Local mode uses pandas (pytest). Rules from transformations.yaml.
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
    from workloads.gcp_demo.scripts.transform import local_runner, spark_transforms
except ImportError:  # pragma: no cover
    local_runner = None  # type: ignore
    spark_transforms = None  # type: ignore

DATABASE = "gcp_demo_db"
SILVER_TABLE = "silver_gcp_demo"


def run_local(bronze_parquet: str, out_dir: str) -> dict:
    import pandas as pd

    cfg = local_runner.load_config("transformations.yaml")
    bronze = pd.read_parquet(bronze_parquet)
    silver, quarantine = local_runner.bronze_to_silver(bronze, cfg)
    out = Path(out_dir)
    (out / "silver").mkdir(parents=True, exist_ok=True)
    (out / "quarantine").mkdir(parents=True, exist_ok=True)
    silver.to_parquet(out / "silver" / "silver_gcp_demo.parquet", index=False)
    quarantine.to_csv(out / "quarantine" / "quarantine.csv", index=False)
    print(f"[silver] clean={len(silver)} quarantined={len(quarantine)}")
    return {"silver": silver, "quarantine": quarantine}


def run_dataproc_spark():  # pragma: no cover
    from pyspark.sql import SparkSession

    ap = argparse.ArgumentParser()
    ap.add_argument("--bronze_path", required=True, help="gs:// Bronze path")
    ap.add_argument("--silver_path", required=True, help="gs:// warehouse root")
    args, _ = ap.parse_known_args()

    spark = (
        SparkSession.builder.appName("gcp_demo_bronze_to_silver")
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        .config("spark.sql.catalog.spark_catalog", "org.apache.iceberg.spark.SparkSessionCatalog")
        .config("spark.sql.catalog.spark_catalog.type", "hadoop")
        .config("spark.sql.catalog.spark_catalog.warehouse", args.silver_path)
        .getOrCreate()
    )
    bronze_df = spark.read.parquet(args.bronze_path)
    if spark_transforms is not None:
        silver_df, quarantine_df = spark_transforms.bronze_to_silver_df(bronze_df)
    else:
        silver_df, quarantine_df = bronze_df, bronze_df.limit(0)
    silver_df.writeTo(f"{DATABASE}.{SILVER_TABLE}").using("iceberg").createOrReplace()
    export_path = f"{args.silver_path.rstrip('/')}/quality_export"
    silver_df.write.mode("overwrite").parquet(export_path)
    print(f"[silver] iceberg {DATABASE}.{SILVER_TABLE} export={export_path}")
    spark.stop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--bronze", default="output/gcp_demo/bronze/bronze_gcp_demo.parquet")
    ap.add_argument("--out", default="output/gcp_demo")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.bronze, args.out)
    else:
        run_dataproc_spark()
