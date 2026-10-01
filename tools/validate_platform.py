#!/usr/bin/env python3
"""Validate workload platform.yaml profiles and capability resolution.

Phase 7 multi-platform backbone. Enforces that each workload's platform profile
is internally consistent (profile <-> table format <-> transform engine <->
orchestrator <-> deploy adapter) and consistent with its compute.yaml SKU.

Rules are intentionally declarative (PROFILE_RULES + VALID_FORMAT_ENGINE) so new
profiles (azure, gcp, databricks, snowflake) extend data, not code.

Default profile is `aws`; a workload without platform.yaml is treated as aws and
must still satisfy the aws rules via its compute.yaml.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

# Allowed capability values per platform profile.
PROFILE_RULES: dict[str, dict] = {
    "aws": {
        "transform_engines": {"spark"},
        "lake_formats": {"iceberg", "parquet"},
        "deploy_adapters": {"terraform", "mcp"},
        "orchestrators": {"step_functions", "mwaa"},
    },
    "azure": {
        "transform_engines": {"spark"},
        "lake_formats": {"iceberg", "delta"},
        "deploy_adapters": {"terraform", "bundle"},
        "orchestrators": {"adf", "durable_functions", "composer", "mwaa"},
    },
    "gcp": {
        "transform_engines": {"spark"},
        "lake_formats": {"iceberg", "delta"},
        "deploy_adapters": {"terraform"},
        "orchestrators": {"composer", "workflows"},
    },
    "databricks": {
        "transform_engines": {"spark"},
        "lake_formats": {"iceberg", "delta"},
        "deploy_adapters": {"bundle", "terraform"},
        "orchestrators": {"workflows", "mwaa"},
    },
    "snowflake": {
        "transform_engines": {"snowpark", "sql"},
        "lake_formats": {"iceberg", "native"},
        "deploy_adapters": {"snowflake_cli", "terraform"},
        "orchestrators": {"snowflake_tasks"},
        "requires_mode": True,
    },
}

# Valid (lake_format, transform_engine) pairs across all profiles.
VALID_FORMAT_ENGINE: set[tuple[str, str]] = {
    ("iceberg", "spark"),
    ("delta", "spark"),
    ("parquet", "spark"),
    ("iceberg", "snowpark"),
    ("iceberg", "sql"),
    ("native", "sql"),
}

# Transform steps that must honor the Iceberg-on-Spark hard rule on AWS.
SPARK_TRANSFORM_STEPS = ("bronze_to_silver", "silver_to_gold")


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def validate_workload(wl_dir: Path) -> list[str]:
    name = wl_dir.name
    platform = _load_yaml(wl_dir / "config" / "platform.yaml")
    compute = _load_yaml(wl_dir / "config" / "compute.yaml")
    errors: list[str] = []

    # Default to aws when platform.yaml is absent.
    profile = str(platform.get("profile") or "aws")
    rules = PROFILE_RULES.get(profile)
    if rules is None:
        return [f"{name}: unknown platform profile '{profile}'"]

    storage = platform.get("storage") or {}
    capabilities = platform.get("capabilities") or {}
    lake_format = str(storage.get("lake_format") or "iceberg")
    transform_engine = str(capabilities.get("transform_engine") or "spark")
    orchestrator = (capabilities.get("orchestrator") or {}).get("type")
    deploy_adapter = platform.get("deploy_adapter")

    if transform_engine not in rules["transform_engines"]:
        errors.append(
            f"{name}: transform_engine '{transform_engine}' not allowed for profile "
            f"'{profile}' (allowed: {sorted(rules['transform_engines'])})"
        )
    if lake_format not in rules["lake_formats"]:
        errors.append(
            f"{name}: lake_format '{lake_format}' not allowed for profile "
            f"'{profile}' (allowed: {sorted(rules['lake_formats'])})"
        )
    if (lake_format, transform_engine) not in VALID_FORMAT_ENGINE:
        errors.append(
            f"{name}: invalid (lake_format={lake_format}, transform_engine={transform_engine}) pair"
        )
    if deploy_adapter and deploy_adapter not in rules["deploy_adapters"]:
        errors.append(
            f"{name}: deploy_adapter '{deploy_adapter}' not allowed for profile "
            f"'{profile}' (allowed: {sorted(rules['deploy_adapters'])})"
        )
    if orchestrator and orchestrator not in rules["orchestrators"]:
        errors.append(
            f"{name}: orchestrator '{orchestrator}' not allowed for profile "
            f"'{profile}' (allowed: {sorted(rules['orchestrators'])})"
        )
    if rules.get("requires_mode") and not platform.get("snowflake_mode"):
        errors.append(f"{name}: profile 'snowflake' requires snowflake_mode (sink|platform)")

    # Orchestrator must match schedule.yaml (single source of truth for codegen routing).
    if orchestrator:
        schedule = _load_yaml(wl_dir / "config" / "schedule.yaml")
        sched_orch = schedule.get("orchestrator") or "step_functions"
        if sched_orch != orchestrator:
            errors.append(
                f"{name}: platform orchestrator '{orchestrator}' != schedule.yaml "
                f"orchestrator '{sched_orch}'"
            )

    # Cross-file: Iceberg + Spark transforms must be glueetl in compute.yaml (aws hard rule).
    if transform_engine == "spark" and lake_format == "iceberg" and profile == "aws":
        steps = compute.get("pipeline_steps") or {}
        for step in SPARK_TRANSFORM_STEPS:
            step_cfg = steps.get(step)
            if step_cfg and step_cfg.get("job_type") not in (None, "glueetl"):
                errors.append(
                    f"{name}: step '{step}' must be glueetl for iceberg+spark "
                    f"(found job_type={step_cfg.get('job_type')})"
                )
    return errors


def main(argv: list[str] | None = None) -> int:
    del argv
    wl_dirs = sorted(p.parent.parent for p in REPO_ROOT.glob("workloads/*/config/platform.yaml"))
    # Also include workloads without platform.yaml (treated as aws).
    all_wl = sorted(
        p for p in (REPO_ROOT / "workloads").glob("*") if (p / "config").is_dir()
    )
    seen = set()
    ordered: list[Path] = []
    for p in list(wl_dirs) + all_wl:
        if p not in seen:
            seen.add(p)
            ordered.append(p)

    errors: list[str] = []
    for wl_dir in ordered:
        errors.extend(validate_workload(wl_dir))

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        print("validate_platform: FAIL", file=sys.stderr)
        return 1

    for wl_dir in ordered:
        platform = _load_yaml(wl_dir / "config" / "platform.yaml")
        profile = platform.get("profile", "aws (default)")
        print(f"OK {wl_dir.name}: profile={profile}")
    print(f"validate_platform: PASS ({len(ordered)} workloads)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
