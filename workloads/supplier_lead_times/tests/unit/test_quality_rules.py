"""Unit tests for supplier_lead_times quality gates."""
import pandas as pd

from shared.utils.quality import run_quality
from workloads.supplier_lead_times.scripts.transform import local_runner


def _clean_df(n=10):
    rows = []
    for i in range(n):
        rows.append({
            "supplier_id": f"SUP-{i:03d}",
            "product_category": "ELECTRONICS",
            "supplier_name": f"Supplier {i}",
            "lead_time_days": 10 + i,
        })
    return pd.DataFrame(rows)


def test_clean_data_passes_gold_gate():
    cfg = local_runner.load_config("quality_rules.yaml")
    report = run_quality(_clean_df(), cfg["rules"], "gold", cfg["gates"]["gold"])
    assert report.passed
    assert report.overall_score >= 0.95


def test_duplicate_composite_is_critical():
    cfg = local_runner.load_config("quality_rules.yaml")
    df = _clean_df()
    df.loc[1, "supplier_id"] = df.loc[0, "supplier_id"]
    df.loc[1, "product_category"] = df.loc[0, "product_category"]
    report = run_quality(df, cfg["rules"], "silver", cfg["gates"]["silver"])
    assert "uniqueness_supplier_category" in report.critical_failures


def test_negative_lead_time_is_critical():
    cfg = local_runner.load_config("quality_rules.yaml")
    df = _clean_df()
    df.loc[0, "lead_time_days"] = -1
    report = run_quality(df, cfg["rules"], "silver", cfg["gates"]["silver"])
    assert "validity_lead_time_non_negative" in report.critical_failures
