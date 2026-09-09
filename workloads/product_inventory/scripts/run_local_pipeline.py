"""Local medallion driver for `product_inventory` (no AWS)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from workloads.product_inventory.scripts.load.register_catalog import run_local as lf_plan
from workloads.product_inventory.scripts.quality.run_quality_checks import _print_report, evaluate
from workloads.product_inventory.scripts.transform import local_runner


def _box(title: str, lines: list[str]) -> None:
    width = max([len(title)] + [len(line) for line in lines]) + 4
    bar = "+" + "-" * (width - 2) + "+"
    print("\n" + bar)
    print("| " + title.ljust(width - 4) + " |")
    print(bar)
    for line in lines:
        print("| " + line.ljust(width - 4) + " |")
    print(bar)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="demo/sample_data/product_inventory.csv")
    ap.add_argument("--out", default="output/product_inventory")
    args = ap.parse_args()

    cfg = local_runner.load_config("transformations.yaml")
    bronze = local_runner.ingest_bronze(args.source)
    _box("PHASE: BRONZE (immutable ingest)", [
        f"source        : {args.source}",
        f"rows ingested : {len(bronze)}",
    ])

    silver, quarantine = local_runner.bronze_to_silver(bronze, cfg)
    _box("PHASE: SILVER (clean + quarantine)", [
        f"clean rows    : {len(silver)}",
        f"quarantined   : {len(quarantine)}",
    ])

    silver_report = evaluate(silver, "silver")
    _print_report(silver_report)
    if not silver_report["passed"]:
        _box("GATE BLOCKED", ["Silver quality gate failed -> promotion stopped"])
        return 1

    gold = local_runner.silver_to_gold(silver, cfg)
    _box("PHASE: GOLD (flat Iceberg)", [f"{name}: {len(tbl)} rows" for name, tbl in gold.items()])
    gold_df = next(iter(gold.values()))
    gold_report = evaluate(gold_df, "gold")
    _print_report(gold_report)
    if not gold_report["passed"]:
        _box("GATE BLOCKED", ["Gold quality gate failed -> promotion stopped"])
        return 1

    lf_plan()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
