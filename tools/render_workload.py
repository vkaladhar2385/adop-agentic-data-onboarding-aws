#!/usr/bin/env python3
"""Render codegen artifacts from config/codegen/*.spec.yaml (ADOP factory subset)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.codegen.drift_validator import verify_artifact  # noqa: E402
from shared.codegen.renderer import render  # noqa: E402
from shared.codegen.spec_loader import compute_spec_hash, load_yaml_spec  # noqa: E402
from shared.codegen.write_guard import TOKEN_ENV  # noqa: E402
from shared.utils.orchestrator import resolve_orchestration_artifacts  # noqa: E402

TEMPLATE_ALIASES = {
    "advisory_bronze_to_silver": "bronze_to_silver",
    "web_events_bronze_to_silver": "bronze_to_silver",
}

ARTIFACTS = {
    "bronze_to_silver": {
        "spec": "config/codegen/bronze_to_silver.spec.yaml",
        "template_id": "bronze_to_silver",
        "output": "scripts/transform/bronze_to_silver.py",
        "orchestration": False,
    },
    "ingest_to_bronze": {
        "spec": "config/codegen/ingest_to_bronze.spec.yaml",
        "template_id": "ingest_to_bronze",
        "output": "scripts/extract/ingest_to_bronze.py",
        "orchestration": False,
    },
    "silver_to_gold": {
        "spec": "config/codegen/silver_to_gold.spec.yaml",
        "template_id": "silver_to_gold",
        "output": "scripts/transform/silver_to_gold.py",
        "orchestration": False,
    },
    "quality_checks": {
        "spec": "config/codegen/quality_checks.spec.yaml",
        "template_id": "quality_checks",
        "output": "scripts/quality/run_quality_checks.py",
        "orchestration": False,
    },
    "state_machine": {
        "spec": "config/codegen/state_machine.spec.yaml",
        "template_id": "state_machine",
        "output": "orchestration/{workload}_state_machine.json",
        "orchestration": True,
        "artifact_key": "state_machine",
    },
    "airflow_dag": {
        "spec": "config/codegen/dag.spec.yaml",
        "template_id": "airflow_dag",
        "output": "dags/{workload}_pipeline.py",
        "orchestration": True,
        "artifact_key": "dag",
    },
    "eventbridge_schedule": {
        "spec": "config/codegen/eventbridge_schedule.spec.yaml",
        "template_id": "eventbridge_schedule",
        "output": "orchestration/eventbridge_schedule.json",
        "orchestration": True,
        "artifact_key": "eventbridge_schedule",
    },
    "adf_pipeline": {
        "spec": "config/codegen/adf_pipeline.spec.yaml",
        "template_id": "adf_pipeline",
        "output": "orchestration/{workload}_adf_pipeline.json",
        "orchestration": True,
        "artifact_key": "adf_pipeline",
    },
    "composer_dag": {
        "spec": "config/codegen/composer_dag.spec.yaml",
        "template_id": "composer_dag",
        "output": "dags/{workload}_pipeline.py",
        "orchestration": True,
        "artifact_key": "composer_dag",
    },
    "databricks_workflow": {
        "spec": "config/codegen/databricks_workflow.spec.yaml",
        "template_id": "databricks_workflow",
        "output": "orchestration/{workload}_databricks_workflow.json",
        "orchestration": True,
        "artifact_key": "databricks_workflow",
    },
    "snowflake_sink": {
        "spec": "config/codegen/snowflake_sink.spec.yaml",
        "template_id": "gold_iceberg_external",
        "output": "sql/snowflake/{workload}_gold_iceberg_external.sql",
        "orchestration": False,
        "sink": "snowflake",
    },
}


def _load_source(wl_dir: Path) -> dict:
    path = wl_dir / "config" / "source.yaml"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def _adf_pipeline_spec(workload: str) -> dict:
    return {
        "schema_version": "v1",
        "workload": workload,
        "template_id": "adf_pipeline",
    }


def _databricks_workflow_spec(workload: str) -> dict:
    return {
        "schema_version": "v1",
        "workload": workload,
        "template_id": "databricks_workflow",
    }


def _load_compute(wl_dir: Path) -> dict:
    path = wl_dir / "config" / "compute.yaml"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def _load_platform(wl_dir: Path) -> dict:
    path = wl_dir / "config" / "platform.yaml"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def _snowflake_sink_spec(workload: str, wl_dir: Path) -> dict:
    source = _load_source(wl_dir)
    gold = (source.get("zones") or {}).get("gold") or {}
    platform = _load_platform(wl_dir)
    host = str(platform.get("host_cloud") or "aws")
    table = str(gold.get("table") or f"gold_{workload}")
    return {
        "schema_version": "v1",
        "workload": workload,
        "template_id": "gold_iceberg_external",
        "database": str(gold.get("database") or f"{workload}_analytics").upper(),
        "schema": "GOLD",
        "table": table.upper(),
        "external_volume": f"ADOP_{workload.upper()}_GOLD_VOL",
        "catalog_integration": "SNOWFLAKE",
        "metadata_file_path": f"s3://<bucket>/gold/{workload}/{table}/metadata/",
        "host_cloud": host,
    }


def _composer_dag_spec(workload: str, wl_dir: Path) -> dict:
    schedule = _load_schedule(wl_dir)
    sched = schedule.get("schedule") or {}
    return {
        "schema_version": "v1",
        "workload": workload,
        "template_id": "composer_dag",
        "dataset_name": workload,
        "dag_id": f"{workload}_pipeline",
        "schedule": {
            "cron": sched.get("cron") or "0 6 * * MON",
            "timezone": sched.get("timezone") or "UTC",
        },
    }


def _eventbridge_spec(workload: str, wl_dir: Path) -> dict:
    schedule = _load_schedule(wl_dir)
    source = _load_source(wl_dir)
    sched = schedule.get("schedule") or {}
    execution = schedule.get("execution") or {}
    cadence = (source.get("cadence") or {}).get("frequency") or "scheduled"
    slug = workload.replace("_", "-")
    suffix = "hourly" if "hour" in str(cadence).lower() else "daily"
    if "week" in str(cadence).lower():
        suffix = "weekly"
    retries = execution.get("retries", 2)
    return {
        "schema_version": "v1",
        "workload": workload,
        "template_id": "eventbridge_schedule",
        "cron": sched.get("cron") or "cron(0 7 * * ? *)",
        "timezone": sched.get("timezone") or "UTC",
        "flexible_time_window": sched.get("flexible_time_window") or "OFF",
        "schedule_name": f"{slug}-{suffix}",
        "state_machine": execution.get("state_machine") or f"{workload}_pipeline",
        "scheduler_role": f"{slug}-scheduler-role",
        "cadence": cadence,
        "retries": retries,
        "max_event_age_seconds": 3600,
    }


def _resolve_template_id(spec: dict, meta: dict) -> str:
    raw = spec.get("template_id") or meta["template_id"]
    return TEMPLATE_ALIASES.get(raw, raw)


def _load_schedule(wl_dir: Path) -> dict:
    schedule_path = wl_dir / "config" / "schedule.yaml"
    if not schedule_path.is_file():
        return {}
    with schedule_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def _load_profile(wl_dir: Path) -> str:
    """Platform profile from config/platform.yaml (defaults to aws)."""
    path = wl_dir / "config" / "platform.yaml"
    if not path.is_file():
        return "aws"
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if isinstance(data, dict):
        return str(data.get("profile") or "aws")
    return "aws"


def _output_path(wl_dir: Path, workload: str, meta: dict) -> Path:
    return wl_dir / meta["output"].format(workload=workload)


def _artifact_allowed(artifact: str, orch_artifacts: frozenset[str]) -> bool:
    meta = ARTIFACTS[artifact]
    if not meta.get("orchestration"):
        return True
    key = meta.get("artifact_key", artifact)
    return key in orch_artifacts


def _render_one(
    workload: str,
    artifact: str,
    write: bool,
    check_drift: bool,
    orch_artifacts: frozenset[str],
) -> int:
    if not _artifact_allowed(artifact, orch_artifacts):
        print(f"SKIP {workload}/{artifact}: orchestrator does not emit this artifact")
        return 0

    meta = ARTIFACTS[artifact]
    wl_dir = REPO_ROOT / "workloads" / workload
    profile = _load_profile(wl_dir)
    if meta.get("sink"):
        sinks = (_load_compute(wl_dir).get("sinks") or {})
        if not sinks.get(meta["sink"]):
            print(f"SKIP {workload}/{artifact}: sinks.{meta['sink']} not enabled")
            return 0
        profile = "snowflake"
    spec_path = wl_dir / meta["spec"]
    if artifact == "snowflake_sink" and not spec_path.is_file():
        spec = _snowflake_sink_spec(workload, wl_dir)
        spec_hash = compute_spec_hash(spec)
        template_id = meta["template_id"]
        out_path = _output_path(wl_dir, workload, meta)
        content = render(spec, spec_hash, template_id, schema_version="v1", profile=profile)
        if write:
            os.environ[TOKEN_ENV] = "render"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8", newline="\n")
            print(f"Wrote {out_path.relative_to(REPO_ROOT)}")
        if check_drift:
            if not out_path.is_file():
                print(f"DRIFT: {out_path}: missing snowflake sink SQL", file=sys.stderr)
                return 1
            expected = render(spec, spec_hash, template_id, schema_version="v1", profile=profile)
            if out_path.read_text(encoding="utf-8") != expected:
                print(f"DRIFT: {out_path}: snowflake sink SQL does not match synthesized spec", file=sys.stderr)
                return 1
            print(f"OK no drift: {out_path}")
        if not write and not check_drift:
            print(content)
        return 0

    if artifact == "databricks_workflow" and not spec_path.is_file():
        spec = _databricks_workflow_spec(workload)
        spec_hash = compute_spec_hash(spec)
        template_id = "databricks_workflow"
        out_path = _output_path(wl_dir, workload, meta)
        content = render(spec, spec_hash, template_id, schema_version="v1", profile=profile)
        if write:
            os.environ[TOKEN_ENV] = "render"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8", newline="\n")
            print(f"Wrote {out_path.relative_to(REPO_ROOT)}")
        if check_drift:
            if not out_path.is_file():
                print(f"DRIFT: {out_path}: missing databricks workflow json", file=sys.stderr)
                return 1
            expected = render(spec, spec_hash, template_id, schema_version="v1", profile=profile)
            if out_path.read_text(encoding="utf-8") != expected:
                print(f"DRIFT: {out_path}: databricks workflow does not match synthesized spec", file=sys.stderr)
                return 1
            print(f"OK no drift: {out_path}")
        if not write and not check_drift:
            print(content)
        return 0

    if artifact == "composer_dag" and not spec_path.is_file():
        spec = _composer_dag_spec(workload, wl_dir)
        spec_hash = compute_spec_hash(spec)
        template_id = "composer_dag"
        out_path = _output_path(wl_dir, workload, meta)
        content = render(spec, spec_hash, template_id, schema_version="v1", profile=profile)
        if write:
            os.environ[TOKEN_ENV] = "render"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8", newline="\n")
            print(f"Wrote {out_path.relative_to(REPO_ROOT)}")
        if check_drift:
            if not out_path.is_file():
                print(f"DRIFT: {out_path}: missing composer DAG", file=sys.stderr)
                return 1
            expected = render(spec, spec_hash, template_id, schema_version="v1", profile=profile)
            if out_path.read_text(encoding="utf-8") != expected:
                print(f"DRIFT: {out_path}: composer DAG does not match synthesized spec", file=sys.stderr)
                return 1
            print(f"OK no drift: {out_path}")
        if not write and not check_drift:
            print(content)
        return 0

    if artifact == "adf_pipeline" and not spec_path.is_file():
        spec = _adf_pipeline_spec(workload)
        spec_hash = compute_spec_hash(spec)
        template_id = "adf_pipeline"
        out_path = _output_path(wl_dir, workload, meta)
        content = render(spec, spec_hash, template_id, schema_version="v1", profile=profile)
        if write:
            os.environ[TOKEN_ENV] = "render"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8", newline="\n")
            print(f"Wrote {out_path.relative_to(REPO_ROOT)}")
        if check_drift:
            if not out_path.is_file():
                print(f"DRIFT: {out_path}: missing adf_pipeline.json", file=sys.stderr)
                return 1
            expected = render(spec, spec_hash, template_id, schema_version="v1", profile=profile)
            if out_path.read_text(encoding="utf-8") != expected:
                print(f"DRIFT: {out_path}: adf_pipeline.json does not match synthesized spec", file=sys.stderr)
                return 1
            print(f"OK no drift: {out_path}")
        if not write and not check_drift:
            print(content)
        return 0

    if artifact == "eventbridge_schedule" and not spec_path.is_file():
        spec = _eventbridge_spec(workload, wl_dir)
        spec_hash = compute_spec_hash(spec)
        template_id = "eventbridge_schedule"
        out_path = _output_path(wl_dir, workload, meta)
        content = render(spec, spec_hash, template_id, schema_version="v1", profile=profile)
        if write:
            os.environ[TOKEN_ENV] = "render"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8", newline="\n")
            print(f"Wrote {out_path.relative_to(REPO_ROOT)}")
        if check_drift:
            if not out_path.is_file():
                print(f"DRIFT: {out_path}: missing eventbridge_schedule.json", file=sys.stderr)
                return 1
            expected = render(spec, spec_hash, template_id, schema_version="v1", profile=profile)
            if out_path.read_text(encoding="utf-8") != expected:
                print(f"DRIFT: {out_path}: eventbridge_schedule.json does not match schedule.yaml", file=sys.stderr)
                return 1
            print(f"OK no drift: {out_path}")
        if not write and not check_drift:
            print(content)
        return 0

    if not spec_path.is_file():
        print(f"SKIP {workload}/{artifact}: no spec at {spec_path.relative_to(REPO_ROOT)}")
        return 0

    spec = load_yaml_spec(spec_path)
    spec_hash = compute_spec_hash(spec)
    template_id = _resolve_template_id(spec, meta)
    out_path = _output_path(wl_dir, spec.get("workload", workload), meta)
    content = render(
        spec, spec_hash, template_id, schema_version=spec.get("schema_version", "v1"), profile=profile
    )

    if write:
        os.environ[TOKEN_ENV] = "render"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8", newline="\n")
        print(f"Wrote {out_path.relative_to(REPO_ROOT)}")

    if check_drift:
        report = verify_artifact(out_path, spec_path, "", template_id=template_id, profile=profile)
        if not report.ok:
            print(f"DRIFT: {report.path}: {report.reason}", file=sys.stderr)
            return 1
        print(f"OK no drift: {report.path}")

    if not write and not check_drift:
        print(content)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workload", required=True)
    ap.add_argument("--artifact", choices=sorted(ARTIFACTS), default=None)
    ap.add_argument("--all", action="store_true", help="Render every artifact that has a spec")
    ap.add_argument("--write", action="store_true", help="Write rendered file to disk")
    ap.add_argument("--check-drift", action="store_true", help="Fail if artifact drifted from spec")
    args = ap.parse_args(argv)

    wl_dir = REPO_ROOT / "workloads" / args.workload
    orch_artifacts = resolve_orchestration_artifacts(_load_schedule(wl_dir))
    print(f"Orchestration artifacts for {args.workload}: {sorted(orch_artifacts)}")

    names = list(ARTIFACTS) if args.all else [args.artifact or "bronze_to_silver"]
    rc = 0
    for name in names:
        rc = max(rc, _render_one(args.workload, name, args.write, args.check_drift, orch_artifacts))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
