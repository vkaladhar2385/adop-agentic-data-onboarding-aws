"""Unit tests for product_inventory quality gates."""
import pandas as pd

from shared.utils.quality import run_quality
from workloads.product_inventory.scripts.transform import local_runner


def _clean_df(n=10):
    rows = []
    for i in range(n):
        rows.append({
            "sku": f"SKU{i:06d}",
            "product_name": f"Item {i}",
            "on_hand_qty": 10,
            "reserved_qty": 2,
            "unit_cost": 4.0,
            "list_price": 8.0,
        })
    return pd.DataFrame(rows)


def test_clean_data_passes_gold_gate():
    cfg = local_runner.load_config("quality_rules.yaml")
    report = run_quality(_clean_df(), cfg["rules"], "gold", cfg["gates"]["gold"])
    assert report.passed
    assert report.overall_score >= 0.95
    assert report.critical_failures == []


def test_duplicate_sku_is_critical():
    cfg = local_runner.load_config("quality_rules.yaml")
    df = _clean_df()
    df.loc[1, "sku"] = df.loc[0, "sku"]
    report = run_quality(df, cfg["rules"], "silver", cfg["gates"]["silver"])
    assert "uniqueness_sku" in report.critical_failures
    assert not report.passed


def test_negative_on_hand_is_critical():
    cfg = local_runner.load_config("quality_rules.yaml")
    df = _clean_df()
    df.loc[0, "on_hand_qty"] = -1
    report = run_quality(df, cfg["rules"], "silver", cfg["gates"]["silver"])
    assert "validity_on_hand_non_negative" in report.critical_failures


def test_blank_name_is_warning_not_critical():
    cfg = local_runner.load_config("quality_rules.yaml")
    df = _clean_df(20)
    df.loc[0, "product_name"] = ""
    report = run_quality(df, cfg["rules"], "silver", cfg["gates"]["silver"])
    assert "completeness_product_name" not in report.critical_failures
    failed = [r for r in report.results if r.rule_id == "completeness_product_name"]
    assert failed and not failed[0].passed
