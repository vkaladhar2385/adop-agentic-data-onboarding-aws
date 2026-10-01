"""Tests for tools/validate_platform.py capability resolution rules."""
from __future__ import annotations

import textwrap
from pathlib import Path

from tools.validate_platform import main, validate_workload


def _write(wl_dir: Path, platform_yaml: str, compute_yaml: str = "", schedule_yaml: str = "") -> None:
    cfg = wl_dir / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "platform.yaml").write_text(textwrap.dedent(platform_yaml), encoding="utf-8")
    if compute_yaml:
        (cfg / "compute.yaml").write_text(textwrap.dedent(compute_yaml), encoding="utf-8")
    if schedule_yaml:
        (cfg / "schedule.yaml").write_text(textwrap.dedent(schedule_yaml), encoding="utf-8")


def test_real_workloads_pass():
    assert main([]) == 0


def test_aws_iceberg_spark_ok(tmp_path):
    wl = tmp_path / "demo"
    _write(
        wl,
        """
        profile: aws
        storage: { lake_format: iceberg }
        capabilities: { transform_engine: spark }
        deploy_adapter: terraform
        """,
    )
    assert validate_workload(wl) == []


def test_sql_engine_rejected_on_aws(tmp_path):
    wl = tmp_path / "demo"
    _write(
        wl,
        """
        profile: aws
        storage: { lake_format: iceberg }
        capabilities: { transform_engine: sql }
        """,
    )
    errors = validate_workload(wl)
    assert any("transform_engine 'sql' not allowed" in e for e in errors)


def test_delta_rejected_on_aws(tmp_path):
    wl = tmp_path / "demo"
    _write(
        wl,
        """
        profile: aws
        storage: { lake_format: delta }
        capabilities: { transform_engine: spark }
        """,
    )
    errors = validate_workload(wl)
    assert any("lake_format 'delta' not allowed" in e for e in errors)


def test_snowflake_requires_mode(tmp_path):
    wl = tmp_path / "demo"
    _write(
        wl,
        """
        profile: snowflake
        storage: { lake_format: native }
        capabilities: { transform_engine: sql }
        deploy_adapter: snowflake_cli
        """,
    )
    errors = validate_workload(wl)
    assert any("requires snowflake_mode" in e for e in errors)


def test_snowflake_sink_mode_iceberg_sql_ok(tmp_path):
    wl = tmp_path / "demo"
    _write(
        wl,
        """
        profile: snowflake
        snowflake_mode: sink
        storage: { lake_format: iceberg }
        capabilities: { transform_engine: sql }
        deploy_adapter: snowflake_cli
        """,
    )
    assert validate_workload(wl) == []


def test_snowflake_native_sql_with_mode_ok(tmp_path):
    wl = tmp_path / "demo"
    _write(
        wl,
        """
        profile: snowflake
        snowflake_mode: platform
        storage: { lake_format: native }
        capabilities: { transform_engine: sql }
        deploy_adapter: snowflake_cli
        """,
    )
    assert validate_workload(wl) == []


def test_databricks_delta_spark_ok(tmp_path):
    wl = tmp_path / "demo"
    _write(
        wl,
        """
        profile: databricks
        storage: { lake_format: delta }
        capabilities: { transform_engine: spark }
        deploy_adapter: bundle
        """,
    )
    assert validate_workload(wl) == []


def test_iceberg_transform_must_be_glueetl(tmp_path):
    wl = tmp_path / "demo"
    _write(
        wl,
        """
        profile: aws
        storage: { lake_format: iceberg }
        capabilities: { transform_engine: spark }
        """,
        compute_yaml="""
        pipeline_steps:
          bronze_to_silver: { job_type: pythonshell, script: x.py }
        """,
    )
    errors = validate_workload(wl)
    assert any("must be glueetl" in e for e in errors)


def test_orchestrator_mismatch_detected(tmp_path):
    wl = tmp_path / "demo"
    _write(
        wl,
        """
        profile: aws
        storage: { lake_format: iceberg }
        capabilities:
          transform_engine: spark
          orchestrator: { type: step_functions }
        """,
        schedule_yaml="orchestrator: mwaa\n",
    )
    errors = validate_workload(wl)
    assert any("!= schedule.yaml" in e for e in errors)
