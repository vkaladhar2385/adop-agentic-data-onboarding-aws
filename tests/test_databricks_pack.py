"""Phase 7.3 Gate A: Databricks pack templates render via profile-aware renderer."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from shared.codegen.renderer import _load_template, render
from shared.codegen.spec_loader import compute_spec_hash

DATABRICKS_TEMPLATES = [
    "ingest_to_bronze",
    "bronze_to_silver",
    "silver_to_gold",
    "quality_checks",
    "databricks_workflow",
]


def _spec(workload: str = "databricks_demo") -> dict:
    return {
        "schema_version": "v1",
        "workload": workload,
        "catalog": "main",
        "database": "databricks_demo_db",
        "lake_format": "delta",
    }


@pytest.mark.parametrize("template_id", DATABRICKS_TEMPLATES)
def test_databricks_template_resolves(template_id):
    source, _hash, ext = _load_template(template_id, profile="databricks")
    if template_id == "databricks_workflow":
        assert ext == ".json.j2"
    else:
        assert ext == ".py.j2"
    assert f"template_id: {template_id}" in source


def test_databricks_bronze_is_uc_not_glue():
    spec = _spec()
    content = render(spec, compute_spec_hash(spec), "bronze_to_silver", profile="databricks")
    assert "Unity Catalog" in content
    assert "run_databricks_spark" in content
    assert "awsglue" not in content
    assert 'LAKE_FORMAT = "delta"' in content


def test_databricks_workflow_renders_valid_json():
    spec = {"schema_version": "v1", "workload": "databricks_demo"}
    content = render(spec, compute_spec_hash(spec), "databricks_workflow", profile="databricks")
    doc = json.loads(content)
    assert doc["name"] == "databricks_demo_pipeline"
    task_keys = {t["task_key"] for t in doc["tasks"]}
    assert {"ingest_to_bronze", "bronze_to_silver", "quality_silver", "silver_to_gold", "quality_gold"} <= task_keys


def test_databricks_demo_render_workload_e2e():
    repo = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "tools/render_workload.py", "--workload", "databricks_demo", "--all", "--write"],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    bronze = repo / "workloads/databricks_demo/scripts/transform/bronze_to_silver.py"
    wf = repo / "workloads/databricks_demo/orchestration/databricks_demo_databricks_workflow.json"
    assert bronze.is_file() and "Unity Catalog" in bronze.read_text(encoding="utf-8")
    assert wf.is_file()
    doc = json.loads(wf.read_text(encoding="utf-8"))
    assert doc["name"] == "databricks_demo_pipeline"
