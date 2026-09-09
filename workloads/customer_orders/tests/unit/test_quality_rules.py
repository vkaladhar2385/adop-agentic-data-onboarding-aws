"""Unit tests for customer_orders quality gates."""
import pandas as pd

from shared.utils.quality import run_quality
from workloads.customer_orders.scripts.transform import local_runner


def _clean_df(n=10):
    rows = []
    for i in range(n):
        rows.append({
            "order_id": f"ORD-{i:05d}",
            "quantity": 1 + i,
            "order_total": 10.0 + i,
        })
    return pd.DataFrame(rows)


def test_clean_data_passes_gold_gate():
    cfg = local_runner.load_config("quality_rules.yaml")
    report = run_quality(_clean_df(), cfg["rules"], "gold", cfg["gates"]["gold"])
    assert report.passed
    assert report.overall_score >= 0.95


def test_duplicate_order_id_is_critical():
    cfg = local_runner.load_config("quality_rules.yaml")
    df = _clean_df()
    df.loc[1, "order_id"] = df.loc[0, "order_id"]
    report = run_quality(df, cfg["rules"], "silver", cfg["gates"]["silver"])
    assert "uniqueness_order_id" in report.critical_failures


def test_invalid_quantity_is_critical():
    cfg = local_runner.load_config("quality_rules.yaml")
    df = _clean_df()
    df.loc[0, "quantity"] = 0
    report = run_quality(df, cfg["rules"], "silver", cfg["gates"]["silver"])
    assert "validity_quantity_positive" in report.critical_failures
