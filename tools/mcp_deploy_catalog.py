#!/usr/bin/env python3
"""MCP Phase 5 catalog deploy — Glue database + optional LF-Tags (boto3 / MCP fallback).

When compute.yaml infrastructure.catalog.owner=mcp (the factory default), Terraform
does not create aws_glue_catalog_database.
This tool performs the MCP-equivalent create_database step before or after terraform apply.

Agents with live MCP should prefer glue-athena create_database + lakeformation tags;
this script is the deterministic CLI fallback and CI-safe dry-run.

Usage:
  python tools/mcp_deploy_catalog.py --workload advisory_transactions --dry-run
  python tools/mcp_deploy_catalog.py --workload advisory_transactions --ensure-database
  python tools/mcp_deploy_catalog.py --workload advisory_transactions --apply-lf-tags
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def load_catalog_config(workload: str, repo_root: Path | None = None) -> dict[str, Any]:
    from shared.deploy.infrastructure_config import load_infrastructure_owners

    owners = load_infrastructure_owners(workload, repo_root)
    if owners["catalog_owner"] != "mcp":
        raise ValueError(
            f"{workload}: catalog owner is not mcp in compute.yaml — "
            "Terraform still owns the Glue database."
        )
    return {"owner": "mcp", "database": owners["database"], "workload": workload}


from shared.deploy.mcp_catalog import ensure_database  # noqa: E402


def apply_lf_tags(workload: str, database: str, *, dry_run: bool) -> list[dict]:
    mod_path = f"workloads.{workload}.scripts.load.register_catalog"
    try:
        mod = importlib.import_module(mod_path)
    except ImportError as exc:
        raise RuntimeError(f"Cannot import {mod_path}: {exc}") from exc

    plan_fn = getattr(mod, "plan_lf_tags", None)
    apply_fn = getattr(mod, "apply_lf_tags", None)
    if not plan_fn or not apply_fn:
        raise RuntimeError(f"{mod_path} missing plan_lf_tags / apply_lf_tags")

    tags = plan_fn(database=database)
    if dry_run:
        for t in tags:
            print(f"[dry-run] LF tag {t['table']}.{t['column']} -> {t['lf_tags']}")
        return [{**t, "status": "planned"} for t in tags]

    return apply_fn(tags)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workload", required=True)
    ap.add_argument("--dry-run", action="store_true", help="Print plan only")
    ap.add_argument(
        "--ensure-database",
        action="store_true",
        help="Create Glue database if missing (MCP create_database equivalent)",
    )
    ap.add_argument(
        "--apply-lf-tags",
        action="store_true",
        help="Apply LF-Tags from workload register_catalog plan (after Iceberg tables exist)",
    )
    args = ap.parse_args(argv)

    if not args.ensure_database and not args.apply_lf_tags and not args.dry_run:
        print("Specify --ensure-database and/or --apply-lf-tags (or --dry-run).", file=sys.stderr)
        return 2

    try:
        cfg = load_catalog_config(args.workload)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    database = cfg["database"]
    dry = args.dry_run
    rc = 0

    if args.ensure_database or (dry and not args.apply_lf_tags):
        ensure_database(database, dry_run=dry)

    if args.apply_lf_tags or dry:
        try:
            results = apply_lf_tags(args.workload, database, dry_run=dry)
            failed = [r for r in results if r.get("status") == "failed"]
            if failed:
                print(f"WARNING: {len(failed)} LF tag failures", file=sys.stderr)
                rc = 1
            else:
                print(f"LF tags: {len(results)} column(s) processed")
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    print("mcp_deploy_catalog: OK")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
