# stack: pyspark-iceberg
"""Silver -> Gold transform for `advisory_transactions`.

Local mode: pandas/local_runner. Glue ETL: PySpark star schema to Iceberg tables
plus Parquet export under --gold_path for the Python Shell quality gate.
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
    from workloads.advisory_transactions.scripts.transform import local_runner, spark_transforms
except ImportError:
    import local_runner  # type: ignore
    import spark_transforms  # type: ignore


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

    args = getResolvedOptions(
        sys.argv,
        ["JOB_NAME", "silver_path", "gold_path", "database"],
    )
    database = args["database"]
    silver_path = args["silver_path"].rstrip("/")
    gold_path = args["gold_path"].rstrip("/")

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    silver_df = spark.read.parquet(silver_path)
    gold = spark_transforms.silver_to_gold_tables(silver_df)

    for name, frame in gold.items():
        spark_transforms.write_iceberg_table(frame, database, name)
        export_prefix = f"{gold_path}/{name}"
        frame.write.mode("overwrite").parquet(export_prefix)
        print(f"[gold] {name}: {frame.count()} rows -> iceberg + {export_prefix}")

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
        target = gold_path.rstrip("/") + f"/{name}/{name}.parquet"
        s3_io.write_parquet(tbl, target)
        print(f"[gold] {name}: {len(tbl)} rows -> {target}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument(
        "--silver",
        default="output/advisory_transactions/silver/silver_advisory_transactions.parquet",
    )
    ap.add_argument("--out", default="output/advisory_transactions")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.silver, args.out)
    elif any(tok.startswith("--JOB_NAME") for tok in sys.argv):
        run_glue_spark()
    else:
        run_glue()
