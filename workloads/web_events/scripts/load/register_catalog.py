"""Catalog registration + LF-Tag application for `web_events`.

Production: registers Silver/Gold Iceberg tables in the Glue Data Catalog and
applies Lake Formation LF-Tags on PII columns (user_id/email/IP) for TBAC.
Local mode: prints the plan so the demo can show governance intent without
touching AWS.

This module is also the AWS Lambda entrypoint invoked by the Step Functions
`RegisterCatalog` state (`lambda_handler`). It intentionally avoids importing
the pandas-based `local_runner` module so the Lambda deployment package stays
small (pyyaml + boto3 only) -- see docs/ARCHITECTURE.md#packaging.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.utils.pii import PII_CLASSIFICATION  # noqa: E402

WORKLOAD = "web_events"
SILVER_TABLE = "silver_web_events"

# Only these columns are actually present on this workload's Silver table.
_WEB_EVENTS_PII_COLUMNS = {"user_id", "user_email", "ip_address"}


def plan_lf_tags(database: str | None = None) -> list[dict]:
    if database is None:
        # CLI/local/test path only -- lazy import so the Lambda path never
        # needs pandas just to read a database name.
        from workloads.web_events.scripts.transform import local_runner
        src = local_runner.load_config("source.yaml")
        database = src["zones"]["silver"]["database"]
    tags = []
    for column, (pii_type, sensitivity) in PII_CLASSIFICATION.items():
        if column not in _WEB_EVENTS_PII_COLUMNS:
            continue
        tags.append({
            "database": database,
            "table": SILVER_TABLE,
            "column": column,
            "lf_tags": {"PII_Type": pii_type, "Data_Sensitivity": sensitivity},
        })
    return tags


def run_local() -> None:
    print("[load] Glue catalog registration plan (Iceberg):")
    for zone in ("silver", "gold"):
        print(f"  - register {zone} tables from sql/{zone}/*.sql")
    print("[load] Lake Formation LF-Tag plan (TBAC on PII columns):")
    for t in plan_lf_tags():
        print(f"  - {t['table']}.{t['column']} -> {t['lf_tags']}")
    print("[load] NOTE: Gold suppresses user_email/ip_address entirely; erasure")
    print("[load]       index carries only the hashed user_id token.")


def apply_lf_tags(tags: list[dict]) -> list[dict]:  # pragma: no cover - requires AWS
    """Idempotently create+associate each LF-Tag via boto3. Returns per-tag results."""
    import boto3
    lf = boto3.client("lakeformation")
    results = []
    for t in tags:
        try:
            for key, value in t["lf_tags"].items():
                try:
                    lf.create_lf_tag(TagKey=key, TagValues=[value])
                except lf.exceptions.AlreadyExistsException:
                    pass
                lf.add_lf_tags_to_resource(
                    Resource={"TableWithColumns": {
                        "DatabaseName": t["database"],
                        "Name": t["table"],
                        "ColumnNames": [t["column"]],
                    }},
                    LFTags=[{"TagKey": key, "TagValues": [value]}],
                )
            results.append({**t, "status": "applied"})
        except Exception as exc:  # noqa: BLE001
            results.append({**t, "status": "failed", "error": str(exc)})
    return results


def run_glue():  # pragma: no cover - requires AWS
    """Production path via glue-athena + lakeformation MCP servers / boto3."""
    raise SystemExit("Catalog registration runs against AWS; use --local for the demo.")


def lambda_handler(event: dict, context) -> dict:  # pragma: no cover - requires AWS
    """Step Functions `RegisterCatalog` task target.

    event = {"action": "register_and_tag", "database": "<optional override>"}
    """
    database = (event or {}).get("database") or os.environ.get("GLUE_DATABASE")
    tags = plan_lf_tags(database=database)
    try:
        import boto3  # noqa: F401
        results = apply_lf_tags(tags)
    except ImportError:
        results = [{**t, "status": "planned (boto3 unavailable, dry-run)"} for t in tags]
    failed = [r for r in results if r["status"] == "failed"]
    return {"workload": WORKLOAD, "tagged": len(results), "failed": len(failed), "results": results}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()
    run_local() if args.local else run_glue()
