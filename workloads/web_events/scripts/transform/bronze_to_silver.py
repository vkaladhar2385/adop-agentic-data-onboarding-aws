# spec_hash: 2e41253f0197f94dd6ddddcda64858604f1bce13d02d056ece679e47728672fc
# template_id: bronze_to_silver
# template_hash: 0f00c058d91ab54d115288be52e19985d0158b4ef3b6dee8b2857a34e4f6d72b
# schema_version: v1
# rendered_at: 2026-09-15T05:10:40Z
"""Bronze -> Silver transform for `web_events`.

Local mode uses pandas/local_runner (pytest source of truth). Glue ETL (PySpark)
writes Apache Iceberg to the Silver catalog table and exports Parquet to
--silver_path for the Python Shell quality gate.
Source format: jsonl.
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
    from workloads.web_events.scripts.transform import local_runner, spark_transforms
except ImportError:
    import local_runner  # type: ignore
    try:
        import spark_transforms  # type: ignore
    except ImportError:  # pragma: no cover
        spark_transforms = None  # type: ignore


def run_local(bronze_jsonl: str, out_dir: str) -> dict:
    cfg = local_runner.load_config("transformations.yaml")
    bronze = local_runner.ingest_bronze(bronze_jsonl)
    unpacked = local_runner.bronze_to_silver(bronze, cfg)
    silver, quarantine = unpacked[0], unpacked[1]
    suppressed = unpacked[2] if len(unpacked) > 2 else None

    out = Path(out_dir)
    for sub in ("silver", "quarantine"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    silver.to_parquet(out / "silver" / "silver_web_events.parquet", index=False)
    quarantine.to_csv(out / "quarantine" / "quarantine.csv", index=False)
    if suppressed is not None:
        suppressed.to_csv(out / "quarantine" / "suppressed_no_consent.csv", index=False)
        print(
            f"[silver] clean rows: {len(silver)}  |  quarantined: {len(quarantine)}  |  "
            f"no-consent: {len(suppressed)}"
        )
        return {"silver": silver, "quarantine": quarantine, "suppressed_no_consent": suppressed}
    print(f"[silver] clean rows: {len(silver)}  |  quarantined: {len(quarantine)}")
    return {"silver": silver, "quarantine": quarantine}


def run_glue_spark():  # pragma: no cover
    from awsglue.context import GlueContext
    from awsglue.job import Job
    from awsglue.utils import getResolvedOptions
    from pyspark.context import SparkContext

    args = getResolvedOptions(
        sys.argv,
        ["JOB_NAME", "bronze_path", "silver_path", "database", "silver_table"],
    )
    database = args["database"]
    silver_table = args["silver_table"]
    bronze_path = args["bronze_path"].strip().rstrip("/")
    silver_path = args["silver_path"].strip().rstrip("/")

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    warehouse = spark_transforms._warehouse_from_s3_path(silver_path)
    spark_transforms.configure_iceberg_catalog(spark, warehouse)

    bronze_df = spark.read.json(bronze_path)
    input_rows = bronze_df.count()
    silver_df, quarantine_df = spark_transforms.bronze_to_silver_df(bronze_df)

    spark_transforms.write_iceberg_table(silver_df, database, silver_table, warehouse=warehouse)

    export_path = f"{silver_path}/quality_export"
    silver_df.write.mode("overwrite").parquet(export_path)
    print(f"[silver] parquet export for quality gate -> {export_path}")

    q_count = quarantine_df.count()
    if q_count:
        quarantine_path = bronze_path.replace("/bronze/", "/quarantine/") + "/csv_export"
        quarantine_df.coalesce(1).write.mode("overwrite").option("header", True).csv(
            quarantine_path
        )
        print(f"[silver] quarantined rows: {q_count} -> {quarantine_path}")

    clean_rows = silver_df.count()
    print(f"[silver] input={input_rows} clean={clean_rows} quarantined={q_count}")
    job.commit()


def run_glue():  # pragma: no cover - legacy Python Shell path if invoked without Spark
    try:
        from shared.utils import s3_io
    except ImportError:
        import s3_io  # type: ignore

    bronze_path = s3_io.get_arg("bronze_path")
    silver_path = s3_io.get_arg("silver_path")
    if not bronze_path or not silver_path:
        raise SystemExit("run_glue requires --bronze_path and --silver_path")

    cfg = local_runner.load_config("transformations.yaml")
    bronze = local_runner.ingest_bronze(bronze_path)
    unpacked = local_runner.bronze_to_silver(bronze, cfg)
    silver, quarantine = unpacked[0], unpacked[1]
    silver_target = silver_path.rstrip("/") + "/silver_web_events.parquet"
    s3_io.write_parquet(silver, silver_target)
    if len(quarantine):
        quarantine_target = silver_path.rstrip("/").replace("/silver/", "/quarantine/") + "/quarantine.csv"
        s3_io.write_csv(quarantine, quarantine_target)
    print(f"[silver] clean rows: {len(silver)}  |  quarantined: {len(quarantine)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument(
        "--bronze",
        default="output/web_events/bronze/bronze_web_events.jsonl",
    )
    ap.add_argument("--out", default="output/web_events")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.bronze, args.out)
    elif any(tok.startswith("--JOB_NAME") for tok in sys.argv):
        run_glue_spark()
    else:
        run_glue()
