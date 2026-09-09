# spec_hash: e42fe4d2c013dea876125d205d61497272060900c92f427bf82975e7066f5651
# template_id: silver_to_gold
# template_hash: 1816c5c2bef086b27a16dcbca0996633fecdc9e3d2adc150bc895adb6421a748
# schema_version: v1
# rendered_at: 2026-09-09T05:21:47Z
# stack: pyspark-iceberg
"""Silver -> Gold transform for `customer_orders`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_self = Path(__file__).resolve()
_REPO_ROOT = _self.parents[4] if len(_self.parents) > 4 else _self.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from workloads.customer_orders.scripts.transform import local_runner
except ImportError:
    import local_runner  # type: ignore


def run_local(silver_parquet: str, out_dir: str) -> dict:
    import pandas as pd

    cfg = local_runner.load_config("transformations.yaml")
    silver = pd.read_parquet(silver_parquet)
    gold = local_runner.silver_to_gold(silver, cfg)
    out = Path(out_dir) / "gold"
    out.mkdir(parents=True, exist_ok=True)
    for name, tbl in gold.items():
        tbl.to_parquet(out / f"{name}.parquet", index=False)
        print(f"[gold] {name}: {len(tbl)} rows")
    return gold


def run_glue_spark():  # pragma: no cover
    from awsglue.context import GlueContext
    from awsglue.job import Job
    from awsglue.utils import getResolvedOptions
    from pyspark.context import SparkContext

    try:
        from workloads.customer_orders.scripts.transform import spark_transforms
    except ImportError:
        import spark_transforms  # type: ignore

    args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path", "database"])
    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    warehouse = spark_transforms._warehouse_from_s3_path(args["gold_path"])
    spark_transforms.configure_iceberg_catalog(spark, warehouse)
    silver_root = args["silver_path"].rstrip("/")
    silver_df = spark.read.parquet(silver_root + "/quality_export")
    gold_tables = spark_transforms.silver_to_gold_dfs(silver_df)
    for name, gdf in gold_tables.items():
        spark_transforms.write_iceberg_table(gdf, args["database"], name, warehouse=warehouse)
        gdf.write.mode("overwrite").parquet(args["gold_path"].rstrip("/") + f"/{name}")
        print(f"[gold] {name}: {gdf.count()} rows")
    job.commit()


def run_glue():  # pragma: no cover
    try:
        from shared.utils import s3_io
    except ImportError:
        import s3_io  # type: ignore

    silver_path = s3_io.get_arg("silver_path")
    gold_path = s3_io.get_arg("gold_path")
    if not silver_path or not gold_path:
        raise SystemExit("run_glue requires --silver_path and --gold_path")
    cfg = local_runner.load_config("transformations.yaml")
    silver = s3_io.read_parquet_prefix(silver_path)
    gold = local_runner.silver_to_gold(silver, cfg)
    for name, tbl in gold.items():
        s3_io.write_parquet(tbl, gold_path.rstrip("/") + f"/{name}.parquet")
        print(f"[gold] {name}: {len(tbl)} rows")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--silver", default="output/customer_orders/silver/silver_customer_orders.parquet")
    ap.add_argument("--out", default="output/customer_orders")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.silver, args.out)
    elif any(tok.startswith("--JOB_NAME") for tok in sys.argv):
        run_glue_spark()
    else:
        run_glue()
