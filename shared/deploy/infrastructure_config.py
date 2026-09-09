"""Load MCP-first infrastructure ownership from workload compute.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
VALID_OWNERS = frozenset({"terraform", "mcp"})


def load_compute(workload: str, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    path = root / "workloads" / workload / "config" / "compute.yaml"
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected mapping")
    return data


def _owner(section: dict[str, Any] | None, *, legacy: str | None = None) -> str:
    if section and section.get("owner") in VALID_OWNERS:
        return str(section["owner"])
    if legacy in VALID_OWNERS:
        return legacy
    return "terraform"


def load_infrastructure_owners(workload: str, repo_root: Path | None = None) -> dict[str, Any]:
    """Return normalized ownership flags and names for MCP deploy + Terraform."""
    compute = load_compute(workload, repo_root)
    infra = compute.get("infrastructure") or {}
    catalog_legacy = (compute.get("catalog") or {}).get("owner")

    catalog = infra.get("catalog") or compute.get("catalog") or {}
    kms = infra.get("kms") or {}
    iam = infra.get("iam") or {}
    lakeformation = infra.get("lakeformation") or {}

    environment = str(compute.get("environment") or "dev")
    name_prefix = f"{workload}-{environment}"
    database = catalog.get("database") or f"{workload}_db"
    zones = kms.get("zones") or ["bronze", "silver", "gold"]

    owners = {
        "workload": workload,
        "environment": environment,
        "name_prefix": name_prefix,
        "database": database,
        "zones": list(zones),
        "catalog_owner": _owner(catalog if isinstance(catalog, dict) else None, legacy=catalog_legacy),
        "kms_owner": _owner(kms if isinstance(kms, dict) else None),
        "iam_owner": _owner(iam if isinstance(iam, dict) else None),
        "lakeformation_owner": _owner(lakeformation if isinstance(lakeformation, dict) else None),
    }

    for key in ("catalog_owner", "kms_owner", "iam_owner", "lakeformation_owner"):
        if owners[key] not in VALID_OWNERS:
            raise ValueError(f"{workload}: invalid {key}={owners[key]!r}")

    return owners
