# spec_hash: 92b5221a852f3f760fe8275f17495a79d86078c624f85fee5602f9638e12b91f
# template_id: silver_to_gold
# template_hash: 992a297bf14434e45b3c858f51de1ef5dcf9693c7107d57aaa036ebc30ada82c
# schema_version: v1
# rendered_at: 2026-10-01T23:26:46Z
"""Silver -> Gold transform for `azure_demo` (Azure Synapse Spark).

Reads Silver Iceberg, builds the Gold shape, writes Gold Iceberg on ADLS Gen2.
Local mode uses pandas for unit tests. Rules come from transformations.yaml.
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
GOLD_TABLE = "gold_azure_demo"


def run_local(silver_parquet: str, out_dir: str) -> dict:
    import pandas as pd

    cfg = local_runner.load_config("transformations.yaml")
    silver = pd.read_parquet(silver_parquet)
    gold = local_runner.silver_to_gold(silver, cfg)

    out = Path(out_dir)
    (out / "gold").mkdir(parents=True, exist_ok=True)
    gold.to_parquet(out / "gold" / "gold_azure_demo.parquet", index=False)
    print(f"[gold] rows: {len(gold)}")
    return {"gold": gold}


def run_synapse_spark():  # pragma: no cover - requires Synapse Spark pool
    """Synapse Spark entrypoint. Args: --silver_path --gold_path (abfss://)."""
    from pyspark.sql import SparkSession

    ap = argparse.ArgumentParser()
    ap.add_argument("--gold_path", required=True, help="abfss:// warehouse root for Gold")
    args, _ = ap.parse_known_args()

    spark = (
        SparkSession.builder.appName("azure_demo_silver_to_gold")
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        .config("spark.sql.catalog.spark_catalog", "org.apache.iceberg.spark.SparkSessionCatalog")
        .config("spark.sql.catalog.spark_catalog.type", "hadoop")
        .config("spark.sql.catalog.spark_catalog.warehouse", args.gold_path)
        .getOrCreate()
    )

    silver_df = spark.table(f"{DATABASE}.silver_azure_demo")
    if spark_transforms is not None:
        gold_df = spark_transforms.silver_to_gold_df(silver_df)
    else:
        gold_df = silver_df
    gold_df.writeTo(f"{DATABASE}.{GOLD_TABLE}").using("iceberg").createOrReplace()
    print(f"[gold] iceberg {DATABASE}.{GOLD_TABLE} written")
    spark.stop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--silver", default="output/azure_demo/silver/silver_azure_demo.parquet")
    ap.add_argument("--out", default="output/azure_demo")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.silver, args.out)
    else:
        run_synapse_spark()
