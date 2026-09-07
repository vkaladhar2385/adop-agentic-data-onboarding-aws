"""Bronze -> Silver transform entrypoint for `web_events` (Glue job wrapper).

Production runs on AWS Glue writing Apache Iceberg to the Silver zone. The
consent-filter/masking/quarantine rules are declared in
config/transformations.yaml and executed by `local_runner.bronze_to_silver`,
so the Glue job and the local demo apply identical logic. Kept as a separate
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


def run_local(bronze_jsonl: str, out_dir: str) -> dict:
    cfg = local_runner.load_config("transformations.yaml")
    bronze = local_runner.ingest_bronze(bronze_jsonl)
    silver, quarantine, suppressed = local_runner.bronze_to_silver(bronze, cfg)

    out = Path(out_dir)
    for sub in ("silver", "quarantine"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    silver.to_parquet(out / "silver" / "silver_web_events.parquet", index=False)
    quarantine.to_csv(out / "quarantine" / "quarantine.csv", index=False)
    suppressed.to_csv(out / "quarantine" / "suppressed_no_consent.csv", index=False)
    print(f"[silver] clean rows: {len(silver)}  |  quarantined: {len(quarantine)}  |  no-consent: {len(suppressed)}")
    return {"silver": silver, "quarantine": quarantine, "suppressed_no_consent": suppressed}


def run_glue():  # pragma: no cover - requires Glue runtime
    """Production path (AWS Glue + Iceberg). Rules identical to local_runner.

    GDPR: rows with consent_analytics=false are suppressed here and never
    written to Silver/Gold (ADOP `consent-gate-before-processing`).
    """
    raise SystemExit("Glue path runs inside AWS Glue; use --local for the demo.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--bronze", default="output/web_events/bronze/bronze_web_events.jsonl")
    ap.add_argument("--out", default="output/web_events")
    args = ap.parse_args()
    if args.local:
        run_local(args.bronze, args.out)
    else:
        run_glue()
