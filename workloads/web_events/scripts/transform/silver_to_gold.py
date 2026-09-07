"""Silver -> Gold transform entrypoint for `web_events` (Glue job wrapper).

Builds the Gold hourly-traffic rollup and the right-to-erasure index, and
enforces PII suppression (email/IP dropped from Gold). Production writes
Iceberg to the Gold zone on Glue; local writes Parquet. Kept as a separate
file (mirroring advisory_transactions) so it maps 1:1 to a Glue job script.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from workloads.web_events.scripts.transform import local_runner  # noqa: E402


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


def run_glue():  # pragma: no cover - requires Glue runtime
    """Production path (AWS Glue + Iceberg rollups on S3 Tables)."""
    raise SystemExit("Glue path runs inside AWS Glue; use --local for the demo.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--silver", default="output/web_events/silver/silver_web_events.parquet")
    ap.add_argument("--out", default="output/web_events")
    args = ap.parse_args()
    if args.local:
        run_local(args.silver, args.out)
    else:
        run_glue()
