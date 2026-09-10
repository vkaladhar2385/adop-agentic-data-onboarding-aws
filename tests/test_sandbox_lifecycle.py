"""Unit tests for sandbox lifecycle (no AWS)."""

from shared.deploy.sandbox_lifecycle import (
    _terraform_targets,
    discover_mcp_workloads,
    resolve_bucket,
)


def test_terraform_targets_include_core_modules():
    core = _terraform_targets(include_extensions=False)
    assert "module.advisory_transactions" in core
    assert "module.supplier_lead_times" in core
    assert "module.advisory_transactions_redshift" not in core


def test_terraform_targets_include_extensions():
    ext = _terraform_targets(include_extensions=True)
    assert "module.advisory_transactions_opensearch" in ext


def test_discover_mcp_workloads_includes_advisory():
    workloads = discover_mcp_workloads()
    assert "advisory_transactions" in workloads


def test_resolve_bucket_explicit():
    assert resolve_bucket(profile=None, region="us-east-1", bucket="my-bucket") == "my-bucket"
