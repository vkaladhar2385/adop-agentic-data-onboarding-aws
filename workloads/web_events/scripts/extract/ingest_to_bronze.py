"""Bronze ingestion for `web_events`.

Copies the hourly JSONL landing file into the immutable Bronze zone. On AWS
this is a Glue job reading the Kinesis-flushed S3 prefix and writing JSON/
Parquet to Bronze; locally it materialises the same file under the workload
output dir. Bronze is NEVER transformed (ADOP `bronze-immutable`).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from workloads.web_events.scripts.transform.local_runner import ingest_bronze  # noqa: E402


def run_local(jsonl_path: str, out_dir: str) -> str:
    df = ingest_bronze(jsonl_path)
    out = Path(out_dir) / "bronze"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "bronze_web_events.jsonl"
    df.to_json(target, orient="records", lines=True)
    print(f"[bronze] ingested {len(df)} events (immutable) -> {target}")
    return str(target)


def run_glue():  # pragma: no cover - requires Glue runtime
    """Production path. Reads job args, writes JSON/Parquet to the Bronze S3 prefix.

    from awsglue.context import GlueContext
    from awsglue.utils import getResolvedOptions
    from pyspark.context import SparkContext
    args = getResolvedOptions(sys.argv, ["source_path", "bronze_path"])
    gc = GlueContext(SparkContext.getOrCreate())
    df = gc.spark_session.read.json(args["source_path"])
    (df.write.mode("append")            # append-only: Bronze is immutable
        .option("compression", "snappy")
        .json(args["bronze_path"]))
    """
    raise SystemExit("Glue path runs inside AWS Glue; use --local for the demo.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--source", default="demo/sample_data/web_events.jsonl")
    ap.add_argument("--out", default="output/web_events")
    args = ap.parse_args()
    if args.local:
        run_local(args.source, args.out)
    else:
        run_glue()
