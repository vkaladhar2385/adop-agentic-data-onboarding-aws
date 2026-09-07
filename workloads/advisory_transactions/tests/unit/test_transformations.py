"""Unit tests for the Bronze -> Silver transform (config-driven)."""
import pandas as pd
import pytest

from workloads.advisory_transactions.scripts.transform import local_runner


@pytest.fixture()
def cfg():
    return local_runner.load_config("transformations.yaml")


def _row(**overrides):
    base = {
        "transaction_id": "TXN0000001", "account_id": "ACC10001",
        "advisor_id": "ADV501", "client_id": "CLI90001",
        "client_name": "James Smith", "client_email": "james.smith1@example.com",
        "client_ssn": "123-45-6789", "security_id": "AAPL",
        "security_name": "Apple Inc.", "asset_class": "equity",
        "transaction_type": "buy", "trade_date": "2026-09-01",
        "settlement_date": "2026-09-03", "quantity": "10.00",
        "unit_price": "100.00", "gross_amount": "1000.00",
        "commission": "1.00", "fees": "0.50", "net_amount": "998.50",
        "currency": "usd", "account_type": "brokerage",
        "advisor_name": "Mary Jones", "branch_code": "BR-NYC-01",
        "ingestion_date": "2026-09-03",
    }
    base.update(overrides)
    return base


def test_dedup_keeps_single_row(cfg):
    # Same id, differ only on a non-financial attribute so both stay valid;
    # dedup must collapse them to exactly one clean Silver row.
    df = pd.DataFrame([_row(), _row(advisor_name="Updated Advisor")])
    silver, quarantine = local_runner.bronze_to_silver(df, cfg)
    assert len(quarantine) == 0
    assert (silver["transaction_id"] == "TXN0000001").sum() == 1


def test_uppercase_and_trim(cfg):
    df = pd.DataFrame([_row(currency="  usd  ", transaction_type="buy")])
    silver, _ = local_runner.bronze_to_silver(df, cfg)
    assert silver.iloc[0]["currency"] == "USD"
    assert silver.iloc[0]["transaction_type"] == "BUY"


def test_pii_masking(cfg):
    df = pd.DataFrame([_row()])
    silver, _ = local_runner.bronze_to_silver(df, cfg)
    row = silver.iloc[0]
    assert row["client_ssn"] == "***-**-6789"
    assert row["client_email"].startswith("j***@")
    assert row["client_id"] != "CLI90001"  # hashed


def test_derived_columns(cfg):
    df = pd.DataFrame([_row(trade_date="2026-07-15")])
    silver, _ = local_runner.bronze_to_silver(df, cfg)
    assert int(silver.iloc[0]["trade_year"]) == 2026
    assert int(silver.iloc[0]["trade_month"]) == 7


@pytest.mark.parametrize("bad,reason", [
    ({"trade_date": "2026-13-40"}, "invalid_trade_date"),
    ({"quantity": "-5.00"}, "negative_quantity"),
    ({"gross_amount": "9999.00"}, "broken_gross_formula"),
    ({"net_amount": "0.00"}, "broken_net_formula"),
    ({"net_amount": ""}, "missing_net_amount"),
])
def test_bad_rows_are_quarantined_not_dropped(cfg, bad, reason):
    df = pd.DataFrame([_row(), _row(transaction_id="TXN0000002", **bad)])
    silver, quarantine = local_runner.bronze_to_silver(df, cfg)
    assert "TXN0000002" not in set(silver["transaction_id"])          # not in clean
    assert "TXN0000002" in set(quarantine["transaction_id"])          # not dropped
    assert reason in quarantine.iloc[0]["quarantine_reason"]


def test_clean_row_survives(cfg):
    df = pd.DataFrame([_row()])
    silver, quarantine = local_runner.bronze_to_silver(df, cfg)
    assert len(silver) == 1 and len(quarantine) == 0
