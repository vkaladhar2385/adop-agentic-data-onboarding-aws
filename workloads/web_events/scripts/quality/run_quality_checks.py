"""Quality gate runner for `web_events`.

Grades a zone's dataframe against config/quality_rules.yaml using the shared
quality engine and enforces GDPR/quality gates (Silver >= 0.80, Gold >= 0.95).
Any critical-rule failure blocks promotion regardless of overall score.
Mirrors advisory_transactions' quality runner but points at this workload's
own config, so the two workloads never cross-import each other.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.utils.quality import run_quality  # noqa: E402
from workloads.web_events.scripts.transform import local_runner  # noqa: E402


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
    ap.add_argument("--parquet", required=True, help="path to the zone parquet to grade")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    df = pd.read_parquet(args.parquet)
    report = evaluate(df, args.zone)
    _print_report(report)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(report, indent=2, default=str))

    raise SystemExit(0 if report["passed"] else 1)
