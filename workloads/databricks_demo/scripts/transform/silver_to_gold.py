# spec_hash: 2110fb0e4cad7de2136402737bcd758ebaa172339f76dfd46f4967176e5c5200
# template_id: silver_to_gold
# template_hash: 1e158a357229b30d5b3cd36b5fc7fe52f640d52abd0a4f24ea7ab5d61958a901
# schema_version: v1
# rendered_at: 2026-10-02T00:13:38Z
"""Silver -> Gold for `databricks_demo` (Databricks PySpark + Unity Catalog)."""
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
GOLD_TABLE = "gold_databricks_demo"
LAKE_FORMAT = "delta"


def run_local(silver_parquet: str, out_dir: str) -> dict:
    import pandas as pd

    cfg = local_runner.load_config("transformations.yaml")
    silver = pd.read_parquet(silver_parquet)
    gold = local_runner.silver_to_gold(silver, cfg)
    out = Path(out_dir)
    (out / "gold").mkdir(parents=True, exist_ok=True)
    gold.to_parquet(out / "gold" / "gold_databricks_demo.parquet", index=False)
    print(f"[gold] rows={len(gold)}")
    return {"gold": gold}


def run_databricks_spark():  # pragma: no cover
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.appName("databricks_demo_silver_to_gold").getOrCreate()
    silver_df = spark.table(f"{CATALOG}.{DATABASE}.silver_databricks_demo")
    gold_df = spark_transforms.silver_to_gold_df(silver_df) if spark_transforms else silver_df
    fqn = f"{CATALOG}.{DATABASE}.{GOLD_TABLE}"
    if LAKE_FORMAT == "iceberg":
        gold_df.writeTo(fqn).using("iceberg").createOrReplace()
    else:
        gold_df.write.format("delta").mode("overwrite").saveAsTable(fqn)
    print(f"[gold] {fqn}")
    spark.stop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--silver", default="output/databricks_demo/silver/silver_databricks_demo.parquet")
    ap.add_argument("--out", default="output/databricks_demo")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.silver, args.out)
    else:
        run_databricks_spark()
