"""Unit tests for the SOX quality gates."""
import pandas as pd
import pytest

from shared.utils.quality import run_quality
from workloads.advisory_transactions.scripts.transform import local_runner


@pytest.fixture()
def rules_cfg():
    return local_runner.load_config("quality_rules.yaml")


def _clean_df(n=10):
    rows = []
    for i in range(n):
        qty, price = 10.0, 100.0
        gross = qty * price
        comm, fees = 1.0, 0.5
        rows.append({
            "transaction_id": f"TXN{i:07d}", "account_id": "ACC1",
            "trade_date": "2026-09-01", "settlement_date": "2026-09-03",
            "quantity": qty, "unit_price": price, "gross_amount": gross,
            "commission": comm, "fees": fees, "net_amount": gross - comm - fees,
            "transaction_type": "BUY", "currency": "USD",
        })
    return pd.DataFrame(rows)


def test_clean_data_passes_gold_gate(rules_cfg):
    report = run_quality(_clean_df(), rules_cfg["rules"], "gold", rules_cfg["gates"]["gold"])
    assert report.passed
    assert report.overall_score >= 0.95
    assert report.critical_failures == []


def test_broken_gross_is_critical_failure(rules_cfg):
    df = _clean_df()
    df.loc[0, "gross_amount"] = 12345.0  # gross != qty*price
    report = run_quality(df, rules_cfg["rules"], "gold", rules_cfg["gates"]["gold"])
    assert not report.passed
    assert "accuracy_gross_amount" in report.critical_failures


def test_broken_net_is_critical_failure(rules_cfg):
    df = _clean_df()
    df.loc[0, "net_amount"] = 0.0  # net != gross - comm - fees
    report = run_quality(df, rules_cfg["rules"], "gold", rules_cfg["gates"]["gold"])
    assert not report.passed
    assert "consistency_net_amount" in report.critical_failures


def test_duplicate_id_fails_uniqueness(rules_cfg):
    df = _clean_df()
    df.loc[1, "transaction_id"] = df.loc[0, "transaction_id"]
    report = run_quality(df, rules_cfg["rules"], "silver", rules_cfg["gates"]["silver"])
    assert "uniqueness_transaction_id" in report.critical_failures


def test_critical_failure_blocks_even_with_high_score(rules_cfg):
    # One broken row among many -> overall score high, but gate must still fail.
    df = _clean_df(100)
    df.loc[0, "net_amount"] = 999999.0
    report = run_quality(df, rules_cfg["rules"], "gold", rules_cfg["gates"]["gold"])
    assert report.overall_score > 0.95   # score alone would pass
    assert not report.passed             # but critical failure blocks promotion
