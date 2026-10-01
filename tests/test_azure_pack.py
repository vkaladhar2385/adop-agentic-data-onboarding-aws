"""Phase 7.1 Gate A: Azure pack templates render via the profile-aware renderer."""
from __future__ import annotations

import json

import pytest

from shared.codegen.renderer import _load_template, render
from shared.codegen.spec_loader import compute_spec_hash

AZURE_TEMPLATES = ["ingest_to_bronze", "bronze_to_silver", "silver_to_gold", "quality_checks"]


def _spec(workload: str = "azure_demo") -> dict:
    return {"schema_version": "v1", "workload": workload}


@pytest.mark.parametrize("template_id", AZURE_TEMPLATES)
def test_azure_template_resolves_from_pack(template_id):
    source, _hash, ext = _load_template(template_id, profile="azure")
    assert ext == ".py.j2"
    assert f"template_id: {template_id}" in source


@pytest.mark.parametrize("template_id", AZURE_TEMPLATES)
def test_azure_template_renders(template_id):
    spec = _spec()
    content = render(spec, compute_spec_hash(spec), template_id, profile="azure")
    assert f"# template_id: {template_id}" in content
    assert "azure_demo" in content


def test_azure_transform_is_synapse_not_glue():
    spec = _spec()
    content = render(spec, compute_spec_hash(spec), "bronze_to_silver", profile="azure")
    assert "Synapse" in content
    assert "run_synapse_spark" in content
    assert "awsglue" not in content
    assert "GlueContext" not in content


def test_azure_and_aws_bronze_differ():
    spec = _spec("azure_demo")
    azure = render(spec, compute_spec_hash(spec), "bronze_to_silver", profile="azure")
    aws = render(spec, compute_spec_hash(spec), "bronze_to_silver", profile="aws")
    assert azure != aws
    assert "awsglue" in aws
    assert "awsglue" not in azure


def test_aws_profile_unaffected_by_azure_pack():
    """AWS still resolves its own templates (no cross-pack bleed)."""
    source, _hash, _ext = _load_template("state_machine", profile="aws")
    assert "States" in source or "StartAt" in source


def test_azure_demo_renders_via_render_workload():
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "tools/render_workload.py", "--workload", "azure_demo", "--all", "--write"],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    bronze = repo / "workloads/azure_demo/scripts/transform/bronze_to_silver.py"
    adf = repo / "workloads/azure_demo/orchestration/azure_demo_adf_pipeline.json"
    assert bronze.is_file()
    assert adf.is_file()
    text = bronze.read_text(encoding="utf-8")
    assert "Synapse" in text
    assert "awsglue" not in text


def test_azure_adf_pipeline_renders_valid_json():
    spec = _spec("azure_demo")
    content = render(spec, compute_spec_hash(spec), "adf_pipeline", profile="azure")
    doc = json.loads(content)
    assert doc["name"] == "azure_demo_pipeline"
    activity_names = {a["name"] for a in doc["properties"]["activities"]}
    assert {"IngestToBronze", "BronzeToSilver", "QualitySilver", "GateSilver"} <= activity_names
    # Gold promotion is gated behind the silver quality IfCondition.
    gate = next(a for a in doc["properties"]["activities"] if a["name"] == "GateSilver")
    assert gate["type"] == "IfCondition"
