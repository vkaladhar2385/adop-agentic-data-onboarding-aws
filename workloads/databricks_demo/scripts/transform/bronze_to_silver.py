# spec_hash: 78bca2aa54e1678fcc556ed9d67620548d4a270c9e47301c6674ccb14792e807
# template_id: bronze_to_silver
# template_hash: 5d0c894afed8faec77623df76a93a6e67fe7035e5a5cd2a113f750d36d139333
# schema_version: v1
# rendered_at: 2026-10-01T23:47:23Z
"""Bronze -> Silver for `databricks_demo` (Databricks PySpark + Unity Catalog).

Table format: delta. Local mode uses pandas for pytest.
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
    from workloads.databricks_demo.scripts.transform import local_runner, spark_transforms
except ImportError:  # pragma: no cover
    local_runner = None  # type: ignore
    spark_transforms = None  # type: ignore

CATALOG = "main"
DATABASE = "databricks_demo_db"
SILVER_TABLE = "silver_databricks_demo"
LAKE_FORMAT = "delta"


def run_local(bronze_parquet: str, out_dir: str) -> dict:
    import pandas as pd

    cfg = local_runner.load_config("transformations.yaml")
    bronze = pd.read_parquet(bronze_parquet)
    silver, quarantine = local_runner.bronze_to_silver(bronze, cfg)
    out = Path(out_dir)
    (out / "silver").mkdir(parents=True, exist_ok=True)
    (out / "quarantine").mkdir(parents=True, exist_ok=True)
    silver.to_parquet(out / "silver" / "silver_databricks_demo.parquet", index=False)
    quarantine.to_csv(out / "quarantine" / "quarantine.csv", index=False)
    print(f"[silver] clean={len(silver)} quarantined={len(quarantine)}")
    return {"silver": silver, "quarantine": quarantine}


def run_databricks_spark():  # pragma: no cover
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.appName("databricks_demo_bronze_to_silver").getOrCreate()
    ap = argparse.ArgumentParser()
    ap.add_argument("--bronze_path", required=True)
    ap.add_argument("--silver_path", required=True)
    args, _ = ap.parse_known_args()

    bronze_df = spark.read.parquet(args.bronze_path)
    if spark_transforms is not None:
        silver_df, _q = spark_transforms.bronze_to_silver_df(bronze_df)
    else:
        silver_df = bronze_df

    fqn = f"{CATALOG}.{DATABASE}.{SILVER_TABLE}"
    if LAKE_FORMAT == "iceberg":
        silver_df.writeTo(fqn).using("iceberg").createOrReplace()
    else:
        silver_df.write.format("delta").mode("overwrite").saveAsTable(fqn)

    export = f"{args.silver_path.rstrip('/')}/quality_export"
    silver_df.write.mode("overwrite").parquet(export)
    print(f"[silver] {fqn} export={export}")
    spark.stop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--bronze", default="output/databricks_demo/bronze/bronze_databricks_demo.parquet")
    ap.add_argument("--out", default="output/databricks_demo")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.bronze, args.out)
    else:
        run_databricks_spark()
