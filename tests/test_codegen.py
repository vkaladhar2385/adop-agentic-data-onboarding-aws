"""Schema validation for workload configs."""
from pathlib import Path

import subprocess
import sys


def test_validate_configs_passes():
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(repo / "tools" / "validate_configs.py")],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_bronze_to_silver_no_codegen_drift():
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(repo / "tools" / "render_workload.py"),
            "--workload",
            "advisory_transactions",
            "--artifact",
            "bronze_to_silver",
            "--check-drift",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_advisory_m2_artifacts_no_drift():
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(repo / "tools" / "render_workload.py"),
            "--workload",
            "advisory_transactions",
            "--all",
            "--check-drift",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_product_inventory_m2_artifacts_no_drift():
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(repo / "tools" / "render_workload.py"),
            "--workload",
            "product_inventory",
            "--all",
            "--check-drift",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_all_workloads_codegen_drift_clean():
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(repo / "tools" / "check_codegen_drift.py")],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_state_machine_template_can_enable_opensearch_and_redis():
    from shared.codegen.renderer import render
    from shared.codegen.spec_loader import compute_spec_hash, load_yaml_spec

    repo = Path(__file__).resolve().parents[1]
    spec = load_yaml_spec(repo / "workloads/product_inventory/config/codegen/state_machine.spec.yaml")
    spec["enable_opensearch"] = True
    spec["enable_redis"] = True
    spec["verifier_checks"] = list(spec["verifier_checks"]) + [
        "opensearch_index_has_docs",
        "redis_quality_score_cached",
    ]
    body = render(spec, compute_spec_hash(spec), "state_machine", schema_version="v1")
    assert "IndexGoldToOpenSearch" in body
    assert "CacheQualityScores" in body
    assert "opensearch_index_has_docs" in body
