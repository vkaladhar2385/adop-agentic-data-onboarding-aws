"""Phase 7.4 Gate A: Snowflake Mode A Gold sink pack."""
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
