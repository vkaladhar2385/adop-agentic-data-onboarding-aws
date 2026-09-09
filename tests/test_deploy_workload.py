"""Preflight and apply-gate tests for the M3 deploy wrapper (no AWS)."""
from pathlib import Path

import tools.deploy_workload as deploy


def test_advisory_module_is_declared():
    assert deploy.terraform_module_declared("advisory_transactions")


def test_product_inventory_module_is_not_declared():
    assert not deploy.terraform_module_declared("product_inventory")


def test_apply_blocked_when_terraform_sync_pending():
    reason = deploy.apply_block_reason("product_inventory", approve_apply=True)
    assert reason and "pending" in reason
    assert "ensure_terraform_module" in reason


def test_apply_allowed_for_advisory_when_approved():
    assert deploy.apply_block_reason("advisory_transactions", approve_apply=True) is None


def test_plan_only_never_blocked():
    assert deploy.apply_block_reason("product_inventory", approve_apply=False) is None


def test_preflight_missing_workload():
    errors = deploy.preflight("does_not_exist_xyz")
    assert errors and "not found" in errors[0]


def test_dry_run_product_inventory_exits_zero():
    rc = deploy.main(["--workload", "product_inventory", "--dry-run"])
    assert rc == 0
    trace = Path("workloads/product_inventory/logs/trace_events.jsonl").read_text(encoding="utf-8")
    assert "dry-run" in trace


def test_customer_orders_mwaa_orchestrator():
    wl_dir = Path("workloads/customer_orders")
    assert deploy.workload_orchestrator(wl_dir) == "mwaa"
    assert deploy.orchestration_artifacts(wl_dir) == frozenset({"dag"})


def test_dry_run_customer_orders_tier_b():
    rc = deploy.main(["--workload", "customer_orders", "--dry-run", "--tier-b-check"])
    assert rc == 0
