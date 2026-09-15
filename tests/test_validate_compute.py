"""Tests for tools/validate_compute.py"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

# Import from tools/ without installing as package
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import validate_compute as vc  # noqa: E402


def test_iceberg_transform_requires_glueetl(tmp_path: Path):
    wl = tmp_path / "demo"
    (wl / "scripts" / "transform").mkdir(parents=True)
    (wl / "scripts" / "transform" / "bronze_to_silver.py").write_text("# stub")
    data = {
        "workload": "demo",
        "profile": {"silver_format": "iceberg", "gold_format": "iceberg"},
        "pipeline_steps": {
            "bronze_to_silver": {
                "job_type": "pythonshell",
                "script": "scripts/transform/bronze_to_silver.py",
            }
        },
    }
    (wl / "config").mkdir()
    (wl / "config" / "compute.yaml").write_text(yaml.dump(data))
    issues = vc.validate_compute_rules(wl, data)
    assert any("requires job_type=glueetl" in i.message for i in issues)


def test_parse_terraform_glue_jobs():
    hcl = textwrap.dedent(
        '''
        module "advisory_transactions" {
          glue_jobs = {
            ingest_to_bronze = { script_path = "scripts/extract/ingest.py", job_type = "pythonshell" }
            bronze_to_silver = { script_path = "scripts/transform/b2s.py", job_type = "glueetl" }
          }
        }
        '''
    )
    path = Path("fake.tf")
    path.write_text(hcl, encoding="utf-8")
    try:
        parsed = vc.parse_terraform_glue_jobs(path)
        assert "advisory_transactions" in parsed
        assert parsed["advisory_transactions"]["bronze_to_silver"]["job_type"] == "glueetl"
    finally:
        path.unlink(missing_ok=True)


def test_parse_all_terraform_glue_jobs_merges_generated_modules(tmp_path: Path):
    (tmp_path / "main.tf").write_text(
        '# module "web_events" {\n'
        '#   glue_jobs = {\n'
        '#     ingest_to_bronze = { script_path = "scripts/extract/ingest.py", job_type = "glueetl" }\n'
        "#   }\n"
        "# }\n"
        'module "advisory_transactions" {\n'
        '  glue_jobs = {\n'
        '    ingest_to_bronze = { script_path = "scripts/extract/ingest.py", job_type = "pythonshell" }\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "workloads_supplier_lead_times.tf").write_text(
        'module "supplier_lead_times" {\n'
        '  glue_jobs = {\n'
        '    bronze_to_silver = { script_path = "scripts/transform/b2s.py", job_type = "glueetl" }\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    parsed = vc.parse_all_terraform_glue_jobs(tmp_path)
    names = vc.parse_terraform_module_names(tmp_path)
    assert set(parsed) == {"advisory_transactions", "supplier_lead_times"}
    assert names == {"advisory_transactions", "supplier_lead_times"}
    assert "web_events" not in names
    assert parsed["supplier_lead_times"]["bronze_to_silver"]["job_type"] == "glueetl"


def test_enforced_sync_fails_without_module(tmp_path: Path):
    wl = tmp_path / "customer_orders"
    (wl / "scripts" / "extract").mkdir(parents=True)
    (wl / "scripts" / "extract" / "ingest.py").write_text("# stub")
    data = {
        "workload": "customer_orders",
        "terraform_sync": {"status": "enforced"},
        "profile": {"silver_format": "iceberg", "gold_format": "iceberg"},
        "pipeline_steps": {
            "ingest_to_bronze": {
                "job_type": "pythonshell",
                "script": "scripts/extract/ingest.py",
            }
        },
    }
    (wl / "config").mkdir()
    (wl / "config" / "compute.yaml").write_text(yaml.dump(data))
    report = vc.validate_workload(wl, {}, False, tf_module_names=set())
    assert not report.ok
    assert any('no module "customer_orders"' in i.message for i in report.issues)


def test_drift_detected_between_yaml_and_tf(tmp_path: Path):
    wl = tmp_path / "advisory_transactions"
    for rel in (
        "scripts/extract/ingest_to_bronze.py",
        "scripts/transform/bronze_to_silver.py",
        "scripts/quality/run_quality_checks.py",
        "scripts/transform/silver_to_gold.py",
    ):
        p = wl / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# stub")

    compute = yaml.safe_load(
        (Path(__file__).parents[1] / "workloads/advisory_transactions/config/compute.yaml").read_text()
    )
    compute["terraform_sync"] = {"status": "enforced"}
    (wl / "config").mkdir()
    (wl / "config" / "compute.yaml").write_text(yaml.dump(compute))

    tf_modules = {
        "advisory_transactions": {
            "bronze_to_silver": {
                "script_path": "scripts/transform/bronze_to_silver.py",
                "job_type": "pythonshell",
            }
        }
    }
    issues = vc.compare_terraform(
        "advisory_transactions",
        compute,
        tf_modules["advisory_transactions"],
    )
    assert any(i.message.startswith("DRIFT bronze_to_silver") for i in issues)
