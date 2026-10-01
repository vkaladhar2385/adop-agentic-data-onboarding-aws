"""Phase 7.2 Gate A: GCP pack templates render via profile-aware renderer."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from shared.codegen.renderer import _load_template, render
from shared.codegen.spec_loader import compute_spec_hash

GCP_TEMPLATES = ["ingest_to_bronze", "bronze_to_silver", "silver_to_gold", "quality_checks", "composer_dag"]


def _spec(workload: str = "gcp_demo") -> dict:
    return {
        "schema_version": "v1",
        "workload": workload,
        "dataset_name": workload,
        "dag_id": f"{workload}_pipeline",
        "schedule": {"cron": "0 6 * * MON", "timezone": "UTC"},
    }


@pytest.mark.parametrize("template_id", GCP_TEMPLATES)
def test_gcp_template_resolves(template_id):
    source, _hash, ext = _load_template(template_id, profile="gcp")
    assert ext == ".py.j2"
    assert f"template_id: {template_id}" in source


def test_gcp_bronze_is_dataproc_not_glue():
    spec = {"schema_version": "v1", "workload": "gcp_demo"}
    content = render(spec, compute_spec_hash(spec), "bronze_to_silver", profile="gcp")
    assert "Dataproc" in content
    assert "run_dataproc_spark" in content
    assert "awsglue" not in content


def test_gcp_composer_dag_renders():
    spec = _spec()
    content = render(spec, compute_spec_hash(spec), "composer_dag", profile="gcp")
    assert "DataprocSubmitJobOperator" in content
    assert "gcp_demo_pipeline" in content


def test_gcp_demo_render_workload_e2e():
    repo = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "tools/render_workload.py", "--workload", "gcp_demo", "--all", "--write"],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    bronze = repo / "workloads/gcp_demo/scripts/transform/bronze_to_silver.py"
    dag = repo / "workloads/gcp_demo/dags/gcp_demo_pipeline.py"
    assert bronze.is_file() and "Dataproc" in bronze.read_text(encoding="utf-8")
    assert dag.is_file() and "Composer" in dag.read_text(encoding="utf-8") or "DataprocSubmitJobOperator" in dag.read_text(encoding="utf-8")
