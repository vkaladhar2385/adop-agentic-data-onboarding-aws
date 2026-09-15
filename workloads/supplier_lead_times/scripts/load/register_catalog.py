"""Catalog registration shim — implementation in shared.catalog.register."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.catalog import register as _reg  # noqa: E402

WORKLOAD = "supplier_lead_times"


def plan_lf_tags(database: str | None = None):
    return _reg.plan_lf_tags(WORKLOAD, database=database)


def run_local() -> None:
    _reg.run_local(WORKLOAD)


def register_tables(database: str, bucket: str):
    return _reg.register_tables(WORKLOAD, database, bucket)


def lambda_handler(event: dict, context):
    return _reg.lambda_handler_for(WORKLOAD, event, context)


if __name__ == "__main__":
    raise SystemExit(_reg.cli_main(WORKLOAD))
