"""Phase 7.4/7.5 Gate A: Snowflake Mode A sink + Mode B platform pack."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from shared.codegen.renderer import _load_template, render
from shared.codegen.spec_loader import compute_spec_hash


def _spec(workload: str = "snowflake_sink_demo") -> dict:
    return {
        "schema_version": "v1",
        "workload": workload,
        "database": "SNOWFLAKE_SINK_DEMO_DB",
        "schema": "GOLD",
        "table": "GOLD_SNOWFLAKE_SINK_DEMO",
        "external_volume": "ADOP_SNOWFLAKE_SINK_DEMO_GOLD_VOL",
        "catalog_integration": "SNOWFLAKE",
        "metadata_file_path": "s3://<bucket>/gold/snowflake_sink_demo/metadata/",
        "host_cloud": "aws",
    }


def test_snowflake_sql_template_resolves():
    source, _hash, ext = _load_template("gold_iceberg_external", profile="snowflake")
    assert ext == ".sql.j2"
    assert "template_id: gold_iceberg_external" in source


def test_snowflake_gold_iceberg_sql_renders():
    spec = _spec()
    content = render(spec, compute_spec_hash(spec), "gold_iceberg_external", profile="snowflake")
    assert "CREATE OR REPLACE ICEBERG TABLE GOLD_SNOWFLAKE_SINK_DEMO" in content
    assert "EXTERNAL_VOLUME" in content
    assert "Mode A" in content


def test_snowflake_sink_demo_render_e2e():
    repo = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [
            sys.executable,
            "tools/render_workload.py",
            "--workload",
            "snowflake_sink_demo",
            "--artifact",
            "snowflake_sink",
            "--write",
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    sql_path = repo / "workloads/snowflake_sink_demo/sql/snowflake/snowflake_sink_demo_gold_iceberg_external.sql"
    assert sql_path.is_file()
    text = sql_path.read_text(encoding="utf-8")
    assert "CREATE OR REPLACE ICEBERG TABLE GOLD_SNOWFLAKE_SINK_DEMO" in text


SNOWFLAKE_MODE_B_TEMPLATES = [
    "ingest_to_bronze",
    "bronze_to_silver",
    "silver_to_gold",
    "quality_checks",
    "snowflake_tasks",
]


@pytest.mark.parametrize("template_id", SNOWFLAKE_MODE_B_TEMPLATES)
def test_snowflake_mode_b_template_resolves(template_id):
    source, _hash, ext = _load_template(template_id, profile="snowflake")
    if template_id == "snowflake_tasks":
        assert ext == ".sql.j2"
    else:
        assert ext == ".py.j2"
    assert f"template_id: {template_id}" in source


def test_snowflake_bronze_is_snowpark_not_glue():
    spec = {"schema_version": "v1", "workload": "snowflake_demo", "database": "snowflake_demo_db"}
    content = render(spec, compute_spec_hash(spec), "bronze_to_silver", profile="snowflake")
    assert "Snowpark" in content
    assert "run_snowpark" in content
    assert "awsglue" not in content


def test_snowflake_tasks_sql_renders():
    spec = {
        "schema_version": "v1",
        "workload": "snowflake_demo",
        "database": "SNOWFLAKE_DEMO_DB",
        "schema": "PIPELINE",
        "warehouse": "ADOP_WH",
        "schedule_cron": "USING CRON 0 6 * * MON UTC",
    }
    content = render(spec, compute_spec_hash(spec), "snowflake_tasks", profile="snowflake")
    assert "CREATE OR REPLACE TASK snowflake_demo_ingest_to_bronze" in content
    assert "AFTER snowflake_demo_ingest_to_bronze" in content


def test_snowflake_demo_render_workload_e2e():
    repo = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "tools/render_workload.py", "--workload", "snowflake_demo", "--all", "--write"],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    bronze = repo / "workloads/snowflake_demo/scripts/transform/bronze_to_silver.py"
    tasks = repo / "workloads/snowflake_demo/orchestration/snowflake_demo_snowflake_tasks.sql"
    assert bronze.is_file() and "Snowpark" in bronze.read_text(encoding="utf-8")
    assert tasks.is_file() and "CREATE OR REPLACE TASK" in tasks.read_text(encoding="utf-8")


def test_snowflake_deploy_compile_sql():
    repo = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [
            sys.executable,
            "platform-packs/snowflake/deploy/deploy_snowflake.py",
            "--workload",
            "snowflake_sink_demo",
            "--compile-sql",
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "OK SQL compile" in proc.stdout
