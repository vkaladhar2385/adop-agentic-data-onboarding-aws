# spec_hash: 777d6ce4be5bbdd5e1601c8cac14fa360116814f9e387b0496b62d39fe4ec54e
# template_id: quality_checks
# template_hash: ad105c88d04422ad0fecb6fd16d46fefeb7af70807681676d5541aa66b17f771
# schema_version: v1
# rendered_at: 2026-09-09T05:17:05Z
"""Quality gate runner for `supplier_lead_times`."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

_self = Path(__file__).resolve()
_REPO_ROOT = _self.parents[4] if len(_self.parents) > 4 else _self.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from shared.utils.quality import run_quality
    from shared.utils.structured_logger import StructuredLogger
    from workloads.supplier_lead_times.scripts.transform import local_runner
except ImportError:
    from quality import run_quality  # type: ignore
    import local_runner  # type: ignore
    try:
        from structured_logger import StructuredLogger  # type: ignore
    except ImportError:
        StructuredLogger = None  # type: ignore

_LOG = StructuredLogger("quality", "supplier_lead_times", "gate") if StructuredLogger else None


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
        print(f"  {mark}{crit} {r['rule_id']:<42} rate={r['pass_rate']:.3f} failed={r['failed_rows']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--zone", choices=["silver", "gold"], required=True)
    ap.add_argument("--parquet", default=None)
    ap.add_argument("--data_lake_bucket", default=None)
    ap.add_argument("--json-out", default=None)
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
            raise SystemExit("requires --parquet or --data_lake_bucket")
        prefix = "gold/supplier_lead_times/gold_supplier_lead_times/" if args.zone == "gold" else "silver/supplier_lead_times/quality_export/"
        df = s3_io.read_parquet_prefix(f"s3://{bucket}/{prefix}")

    report = evaluate(df, args.zone)
    if _LOG:
        _LOG.info(
            "quality_gate",
            zone=args.zone,
            passed=report["passed"],
            score=report["overall_score"],
        )
    _print_report(report)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(report, indent=2, default=str))
    raise SystemExit(0 if report["passed"] else 1)
