# spec_hash: 8a91d3facac5ca41b14a4a9d6a7bb31192c5a6a4ed9d4c277820a93a6278468a
# template_id: web_events_bronze_to_silver
# template_hash: 58372cf45557fad4b867b91f688534ef0bdb2fedbc0d40f1b7a95ea54d7cf7c9
# schema_version: v1
# rendered_at: 2026-09-09T05:13:34Z
"""Bronze -> Silver transform entrypoint for `web_events` (GDPR clickstream).

Consent-filter, masking, and quarantine rules live in config/transformations.yaml
and local_runner.bronze_to_silver — local demo and future Glue path share logic.
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
    from workloads.web_events.scripts.transform import local_runner
except ImportError:
    import local_runner  # type: ignore


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
    print(
        f"[silver] clean rows: {len(silver)}  |  quarantined: {len(quarantine)}  |  "
        f"no-consent: {len(suppressed)}"
    )
    return {"silver": silver, "quarantine": quarantine, "suppressed_no_consent": suppressed}


def run_glue():  # pragma: no cover
    """Production path (AWS Glue + Iceberg). Rules identical to local_runner."""
    raise SystemExit("Glue path runs inside AWS Glue; use --local for the demo.")


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
    else:
        run_glue()
