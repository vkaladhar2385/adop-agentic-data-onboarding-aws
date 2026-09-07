"""End-to-end LOCAL demo driver for `advisory_transactions`.

Runs the full medallion lifecycle with zero AWS:
    Bronze (ingest) -> Silver (clean+mask+quarantine) -> Quality Gate
                    -> Gold (star schema) -> Quality Gate -> Catalog/LF-Tag plan

Prints ADOP-style status boxes after each phase and writes Parquet outputs under
`output/advisory_transactions/`. This is the artifact you screen-record for the
client demo. It mirrors exactly what the Step Functions state machine runs on AWS.

Usage:
    python workloads/advisory_transactions/scripts/run_local_pipeline.py
"""
from __future__ import annotations

import argparse
from pathlib import Path

import sys
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from workloads.advisory_transactions.scripts.transform import local_runner  # noqa: E402
from workloads.advisory_transactions.scripts.quality.run_quality_checks import (  # noqa: E402
    evaluate, _print_report,
)
from workloads.advisory_transactions.scripts.load.register_catalog import run_local as lf_plan  # noqa: E402


def _box(title: str, lines: list[str]) -> None:
    width = max([len(title)] + [len(l) for l in lines]) + 4
    bar = "+" + "-" * (width - 2) + "+"
    print("\n" + bar)
    print("| " + title.ljust(width - 4) + " |")
    print(bar)
    for l in lines:
        print("| " + l.ljust(width - 4) + " |")
    print(bar)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="demo/sample_data/advisory_transactions.csv")
    ap.add_argument("--out", default="output/advisory_transactions")
    args = ap.parse_args()

    cfg = local_runner.load_config("transformations.yaml")

    # Phase: Bronze
    bronze = local_runner.ingest_bronze(args.source)
    _box("PHASE: BRONZE (immutable ingest)", [
        f"source        : {args.source}",
        f"rows ingested : {len(bronze)}",
        f"columns       : {len(bronze.columns)}",
    ])

    # Phase: Silver
    silver, quarantine = local_runner.bronze_to_silver(bronze, cfg)
    _box("PHASE: SILVER (clean + mask + quarantine)", [
        f"clean rows    : {len(silver)}",
        f"quarantined   : {len(quarantine)}  (bad rows set aside, not dropped)",
        f"PII masked    : client_ssn, client_email, client_id",
    ])
    if len(quarantine):
        reasons = quarantine["quarantine_reason"].tolist()
        print("  quarantine reasons:")
        for txn, reason in zip(quarantine["transaction_id"], reasons):
            print(f"    - {txn}: {reason}")

    silver_report = evaluate(silver, "silver")
    _print_report(silver_report)
    if not silver_report["passed"]:
        _box("GATE BLOCKED", ["Silver quality gate failed -> promotion stopped"])
        return 1

    # Phase: Gold
    gold = local_runner.silver_to_gold(silver, cfg)
    _box("PHASE: GOLD (star schema)", [f"{name:<28}: {len(tbl)} rows" for name, tbl in gold.items()])

    gold_report = evaluate(gold["fact_transactions"], "gold")
    _print_report(gold_report)
    if not gold_report["passed"]:
        _box("GATE BLOCKED", ["Gold quality gate failed -> promotion stopped"])
        return 1

    # Persist outputs
    out = Path(args.out)
    (out / "bronze").mkdir(parents=True, exist_ok=True)
    (out / "silver").mkdir(parents=True, exist_ok=True)
    (out / "gold").mkdir(parents=True, exist_ok=True)
    (out / "quarantine").mkdir(parents=True, exist_ok=True)
    bronze.to_parquet(out / "bronze" / "bronze_advisory_transactions.parquet", index=False)
    silver.to_parquet(out / "silver" / "silver_advisory_transactions.parquet", index=False)
    quarantine.to_csv(out / "quarantine" / "quarantine.csv", index=False)
    for name, tbl in gold.items():
        tbl.to_parquet(out / "gold" / f"{name}.parquet", index=False)

    # Phase: Catalog / governance plan
    print()
    lf_plan()

    _box("PIPELINE COMPLETE", [
        f"outputs written under: {out}/",
        "Silver gate: PASS   Gold gate: PASS",
        "SOX critical checks (gross/net formulas): enforced",
    ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
