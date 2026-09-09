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

ARTIFACTS = {
    "bronze_to_silver": {
        "spec": "config/codegen/bronze_to_silver.spec.yaml",
        "template_id": "advisory_bronze_to_silver",
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
}


def _load_schedule(wl_dir: Path) -> dict:
    schedule_path = wl_dir / "config" / "schedule.yaml"
    if not schedule_path.is_file():
        return {}
    with schedule_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


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
    spec_path = wl_dir / meta["spec"]
    if not spec_path.is_file():
        print(f"SKIP {workload}/{artifact}: no spec at {spec_path.relative_to(REPO_ROOT)}")
        return 0

    spec = load_yaml_spec(spec_path)
    spec_hash = compute_spec_hash(spec)
    template_id = spec.get("template_id") or meta["template_id"]
    out_path = _output_path(wl_dir, spec.get("workload", workload), meta)
    content = render(spec, spec_hash, template_id, schema_version=spec.get("schema_version", "v1"))

    if write:
        os.environ[TOKEN_ENV] = "render"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8", newline="\n")
        print(f"Wrote {out_path.relative_to(REPO_ROOT)}")

    if check_drift:
        report = verify_artifact(out_path, spec_path, "", template_id=template_id)
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
