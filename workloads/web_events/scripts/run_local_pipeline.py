"""Local GDPR clickstream demo driver for `web_events`.

Symmetric with advisory_transactions/run_local_pipeline.py: Bronze -> Silver ->
Silver gate -> Gold -> Gold gate -> Catalog/LF-Tag plan. Uses this workload's
own quality + load modules (no cross-workload imports).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from workloads.web_events.scripts.load.register_catalog import run_local as lf_plan  # noqa: E402
from workloads.web_events.scripts.quality.run_quality_checks import evaluate, _print_report  # noqa: E402
from workloads.web_events.scripts.transform import local_runner  # noqa: E402


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
    ap.add_argument("--source", default="demo/sample_data/web_events.jsonl")
    ap.add_argument("--out", default="output/web_events")
    args = ap.parse_args()

    cfg = local_runner.load_config("transformations.yaml")

    bronze = local_runner.ingest_bronze(args.source)
    _box("PHASE: BRONZE (immutable JSONL ingest)", [
        f"source : {args.source}",
        f"events : {len(bronze)}",
    ])

    silver, quarantine, suppressed = local_runner.bronze_to_silver(bronze, cfg)
    _box("PHASE: SILVER (consent + mask + quarantine)", [
        f"clean (consented) : {len(silver)}",
        f"no-consent (GDPR suppressed, not processed): {len(suppressed)}",
        f"quarantined       : {len(quarantine)}",
        "PII: user_id hashed, email masked, IP last-octet zeroed",
    ])

    rules = local_runner.load_config("quality_rules.yaml")
    silver_report = evaluate(silver, "silver", rules)
    _print_report(silver_report)
    if not silver_report["passed"]:
        _box("GATE BLOCKED", ["Silver GDPR/quality gate failed -> promotion stopped"])
        return 1

    gold = local_runner.silver_to_gold(silver, cfg)
    _box("PHASE: GOLD (hourly rollup + erasure index)", [
        f"{name:<22}: {len(tbl)} rows" for name, tbl in gold.items()
    ])
    gold_report = evaluate(gold["gold_hourly_traffic"], "gold", rules)
    _print_report(gold_report)
    if not gold_report["passed"]:
        _box("GATE BLOCKED", ["Gold quality gate failed -> promotion stopped"])
        return 1

    out = Path(args.out)
    for zone in ("bronze", "silver", "gold", "quarantine"):
        (out / zone).mkdir(parents=True, exist_ok=True)
    bronze.to_json(out / "bronze" / "bronze_web_events.jsonl", orient="records", lines=True)
    silver.to_parquet(out / "silver" / "silver_web_events.parquet", index=False)
    quarantine.to_csv(out / "quarantine" / "quarantine.csv", index=False)
    suppressed.to_csv(out / "quarantine" / "suppressed_no_consent.csv", index=False)
    for name, tbl in gold.items():
        tbl.to_parquet(out / "gold" / f"{name}.parquet", index=False)

    print()
    lf_plan()

    _box("PIPELINE COMPLETE", [
        "GDPR: no-consent events never entered Silver/Gold",
        "Gold has no email/IP columns",
        "Silver gate: PASS   Gold gate: PASS",
        f"outputs: {out}/",
    ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
