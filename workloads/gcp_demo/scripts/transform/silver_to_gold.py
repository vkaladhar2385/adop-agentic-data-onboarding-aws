# spec_hash: 59bba43219adc6d66bb4c93c3fcfd490f5658ad2f546432a2a0dcff0945f9e02
# template_id: silver_to_gold
# template_hash: 2607a88e1cf63a28b2010b7005fabcc46c9a73d95847ecd1ed23a35d0d32ce91
# schema_version: v1
# rendered_at: 2026-10-01T23:35:13Z
"""Silver -> Gold for `gcp_demo` (GCP Dataproc Spark)."""
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
GOLD_TABLE = "gold_gcp_demo"


def run_local(silver_parquet: str, out_dir: str) -> dict:
    import pandas as pd

    cfg = local_runner.load_config("transformations.yaml")
    silver = pd.read_parquet(silver_parquet)
    gold = local_runner.silver_to_gold(silver, cfg)
    out = Path(out_dir)
    (out / "gold").mkdir(parents=True, exist_ok=True)
    gold.to_parquet(out / "gold" / "gold_gcp_demo.parquet", index=False)
    print(f"[gold] rows={len(gold)}")
    return {"gold": gold}


def run_dataproc_spark():  # pragma: no cover
    from pyspark.sql import SparkSession

    ap = argparse.ArgumentParser()
    ap.add_argument("--gold_path", required=True, help="gs:// warehouse root")
    args, _ = ap.parse_known_args()

    spark = (
        SparkSession.builder.appName("gcp_demo_silver_to_gold")
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        .config("spark.sql.catalog.spark_catalog", "org.apache.iceberg.spark.SparkSessionCatalog")
        .config("spark.sql.catalog.spark_catalog.type", "hadoop")
        .config("spark.sql.catalog.spark_catalog.warehouse", args.gold_path)
        .getOrCreate()
    )
    silver_df = spark.table(f"{DATABASE}.silver_gcp_demo")
    gold_df = spark_transforms.silver_to_gold_df(silver_df) if spark_transforms else silver_df
    gold_df.writeTo(f"{DATABASE}.{GOLD_TABLE}").using("iceberg").createOrReplace()
    print(f"[gold] iceberg {DATABASE}.{GOLD_TABLE}")
    spark.stop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--silver", default="output/gcp_demo/silver/silver_gcp_demo.parquet")
    ap.add_argument("--out", default="output/gcp_demo")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.silver, args.out)
    else:
        run_dataproc_spark()
