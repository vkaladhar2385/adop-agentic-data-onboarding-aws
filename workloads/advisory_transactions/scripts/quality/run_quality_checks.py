"""Quality gate runner for `advisory_transactions`.

Grades a zone's dataframe against config/quality_rules.yaml using the shared
quality engine and enforces SOX gates (Silver >= 0.80, Gold >= 0.95). Any
critical-rule failure blocks promotion regardless of overall score.
Exit code is non-zero when a gate fails -> the Step Functions task fails ->
promotion stops.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

import sys
# On Glue this file is deployed standalone (flat); `shared`/`workloads` come
# from --extra-py-files (glue.tf) in that case, and this insert is a no-op.
_self = Path(__file__).resolve()
_REPO_ROOT = _self.parents[4] if len(_self.parents) > 4 else _self.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from shared.utils.quality import run_quality  # noqa: E402
    from workloads.advisory_transactions.scripts.transform import local_runner  # noqa: E402
except ImportError:
    # Glue Python Shell: both deployed flat via --extra-py-files (glue.tf).
    from quality import run_quality  # type: ignore  # noqa: E402
    import local_runner  # type: ignore  # noqa: E402


def evaluate(df: pd.DataFrame, zone: str, rules_cfg: dict | None = None) -> dict:
    cfg = rules_cfg if rules_cfg is not None else local_runner.load_config("quality_rules.yaml")
    gate = float(cfg["gates"][zone])
    report = run_quality(df, cfg["rules"], zone=zone, gate_threshold=gate)
    return report.to_dict()


def _print_report(report: dict) -> None:
    status = "PASS" if report["passed"] else "FAIL"
    print(f"\n=== Quality Gate [{report['zone'].upper()}] : {status} ===")
    print(f"overall_score={report['overall_score']:.4f}  gate>={report['gate_threshold']}")
    if report["critical_failures"]:
        print(f"CRITICAL FAILURES (block promotion): {report['critical_failures']}")
    for r in report["results"]:
        mark = "ok " if r["passed"] else "XX "
        crit = "*" if r["critical"] else " "
        print(f"  {mark}{crit} {r['rule_id']:<34} rate={r['pass_rate']:.3f} failed={r['failed_rows']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--zone", choices=["silver", "gold"], required=True)
    ap.add_argument("--parquet", default=None, help="local/dev: path to the zone parquet to grade")
    ap.add_argument("--data_lake_bucket", default=None,
                     help="AWS: bucket to read s3://<bucket>/<zone>/advisory_transactions/ from")
    ap.add_argument("--json-out", default=None)
    # parse_known_args: Glue always injects extra flags (--JOB_NAME, --JOB_RUN_ID,
    # --additional-python-modules, ...) that this job has no use for.
    args, _unknown = ap.parse_known_args()

    if args.parquet:
        df = pd.read_parquet(args.parquet)
    else:
        try:
            from shared.utils import s3_io
        except ImportError:
            import s3_io  # type: ignore
        bucket = args.data_lake_bucket or os.environ.get("DATA_LAKE_BUCKET")
        if not bucket:
            raise SystemExit("run_glue requires --parquet, or --data_lake_bucket / DATA_LAKE_BUCKET env var")
        if args.zone == "gold":
            # Gold has 6 star-schema tables (fact + 4 dims + a summary) with
            # different columns each -- concatenating all of them would corrupt
            # completeness/uniqueness stats (a column absent from one table
            # reads as all-NaN for that table's rows). Grade the fact table
            # only, matching run_local_pipeline.py's evaluate(gold["fact_transactions"], "gold").
            df = s3_io.read_parquet_object(
                f"s3://{bucket}/gold/advisory_transactions/fact_transactions/fact_transactions.parquet"
            )
        else:
            # Silver has exactly one object at this prefix.
            df = s3_io.read_parquet_prefix(f"s3://{bucket}/silver/advisory_transactions/")

    report = evaluate(df, args.zone)
    _print_report(report)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(report, indent=2, default=str))

    # Sidecar for the Redis cache Lambda (VPC-attached, can't see Glue job
    # output because ResultPath is null). Only written on the AWS path.
    bucket = args.data_lake_bucket or os.environ.get("DATA_LAKE_BUCKET")
    if bucket and not args.parquet:
        try:
            from shared.utils import s3_io
        except ImportError:
            import s3_io  # type: ignore
        s3_io.write_json(
            {"zone": args.zone, "overall_score": report["overall_score"], "passed": report["passed"]},
            f"s3://{bucket}/quality-scores/advisory_transactions/{args.zone}.json",
        )

    raise SystemExit(0 if report["passed"] else 1)
