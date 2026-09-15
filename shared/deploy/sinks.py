"""Opt-in extension sinks (Redshift / OpenSearch / Redis).

MCP has no create tool for these services — Terraform owns the modules.
A sink is instantiated only when compute.yaml (or the SFN codegen spec) enables it.
Do not edit iac/terraform/main.tf to add a sink.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

VALID_SINKS = ("redshift", "opensearch", "redis")
SINK_LAMBDA_KEY = {
    "redshift": "register_redshift_spectrum",
    "opensearch": "index_gold_to_opensearch",
    "redis": "cache_quality_scores",
}
SPEC_FLAG = {
    "redshift": "enable_redshift",
    "opensearch": "enable_opensearch",
    "redis": "enable_redis",
}


def enabled_sinks_from_mapping(sinks: Any) -> list[str]:
    if not isinstance(sinks, dict):
        return []
    return [name for name in VALID_SINKS if sinks.get(name) is True]


def enabled_sinks_from_spec(spec: dict[str, Any]) -> list[str]:
    return [name for name, flag in SPEC_FLAG.items() if spec.get(flag) is True]


def load_state_machine_spec(workload: str, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    path = root / "workloads" / workload / "config" / "codegen" / "state_machine.spec.yaml"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def load_enabled_sinks(workload: str, compute: dict[str, Any] | None = None, repo_root: Path | None = None) -> list[str]:
    """compute.yaml sinks.* wins when present; otherwise SFN codegen spec flags."""
    root = repo_root or REPO_ROOT
    if compute is None:
        from shared.deploy.infrastructure_config import load_compute

        compute = load_compute(workload, root)
    if "sinks" in compute:
        return enabled_sinks_from_mapping(compute.get("sinks"))
    return enabled_sinks_from_spec(load_state_machine_spec(workload, root))
