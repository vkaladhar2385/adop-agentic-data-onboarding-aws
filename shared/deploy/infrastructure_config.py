"""Load MCP-first infrastructure ownership from workload compute.yaml.

Default: MCP owns catalog, KMS, IAM, and Lake Formation (servers can create them).
Terraform owns Glue jobs and orchestration (no MCP create tool in the official 13).
Opt out a data-plane slice with ``owner: terraform`` — never leave both creating
the same ARN (enforced by tools/validate_compute.py).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
VALID_OWNERS = frozenset({"terraform", "mcp"})

# MCP can create these today (glue-athena, core KMS, iam, lakeformation).
DATA_PLANE_OWNER_KEYS = ("catalog_owner", "kms_owner", "iam_owner", "lakeformation_owner")
DEFAULT_DATA_PLANE_OWNER = "mcp"

# No MCP create tool — keep Terraform until P2-5 (create_job / CreateStateMachine).
CONTROL_PLANE_OWNER_KEYS = ("glue_jobs_owner", "orchestration_owner")
DEFAULT_CONTROL_PLANE_OWNER = "terraform"

HCL_OWNER_ATTRS = {
    "catalog_owner": "catalog_owner",
    "kms_owner": "kms_owner",
    "iam_owner": "iam_owner",
    "lakeformation_owner": "lakeformation_owner",
}


def load_compute(workload: str, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    path = root / "workloads" / workload / "config" / "compute.yaml"
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected mapping")
    return data


def _owner(section: dict[str, Any] | None, *, legacy: str | None = None, default: str) -> str:
    if section and section.get("owner") in VALID_OWNERS:
        return str(section["owner"])
    if legacy in VALID_OWNERS:
        return legacy
    return default


def owners_from_compute(compute: dict[str, Any], workload: str) -> dict[str, Any]:
    """Normalize ownership flags from an already-loaded compute.yaml mapping."""
    infra = compute.get("infrastructure") or {}
    catalog_legacy = (compute.get("catalog") or {}).get("owner")

    catalog = infra.get("catalog") or compute.get("catalog") or {}
    kms = infra.get("kms") or {}
    iam = infra.get("iam") or {}
    lakeformation = infra.get("lakeformation") or {}
    glue_jobs = infra.get("glue_jobs") or {}
    orchestration = infra.get("orchestration") or {}

    environment = str(compute.get("environment") or "dev")
    name_prefix = f"{workload}-{environment}"
    database = catalog.get("database") or f"{workload}_db" if isinstance(catalog, dict) else f"{workload}_db"
    zones = kms.get("zones") or ["bronze", "silver", "gold"] if isinstance(kms, dict) else ["bronze", "silver", "gold"]

    owners = {
        "workload": workload,
        "environment": environment,
        "name_prefix": name_prefix,
        "database": database,
        "zones": list(zones),
        "catalog_owner": _owner(
            catalog if isinstance(catalog, dict) else None,
            legacy=catalog_legacy,
            default=DEFAULT_DATA_PLANE_OWNER,
        ),
        "kms_owner": _owner(kms if isinstance(kms, dict) else None, default=DEFAULT_DATA_PLANE_OWNER),
        "iam_owner": _owner(iam if isinstance(iam, dict) else None, default=DEFAULT_DATA_PLANE_OWNER),
        "lakeformation_owner": _owner(
            lakeformation if isinstance(lakeformation, dict) else None,
            default=DEFAULT_DATA_PLANE_OWNER,
        ),
        "glue_jobs_owner": _owner(
            glue_jobs if isinstance(glue_jobs, dict) else None,
            default=DEFAULT_CONTROL_PLANE_OWNER,
        ),
        "orchestration_owner": _owner(
            orchestration if isinstance(orchestration, dict) else None,
            default=DEFAULT_CONTROL_PLANE_OWNER,
        ),
    }

    for key in (*DATA_PLANE_OWNER_KEYS, *CONTROL_PLANE_OWNER_KEYS):
        if owners[key] not in VALID_OWNERS:
            raise ValueError(f"{workload}: invalid {key}={owners[key]!r}")

    return owners


def load_infrastructure_owners(workload: str, repo_root: Path | None = None) -> dict[str, Any]:
    """Return normalized ownership flags and names for MCP deploy + Terraform."""
    compute = load_compute(workload, repo_root)
    return owners_from_compute(compute, workload)
