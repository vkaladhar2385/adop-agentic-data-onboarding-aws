"""Unit tests for customer_orders Bronze -> Silver / Gold."""
import pandas as pd
import pytest

from workloads.customer_orders.scripts.transform import local_runner


@pytest.fixture()
def cfg():
    return local_runner.load_config("transformations.yaml")


def _row(**overrides):
    base = {
        "order_id": "ORD-00001",
        "customer_id": "CUST-1001",
        "product_sku": "SKU-100",
        "quantity": "2",
        "order_date": "2026-01-15",
        "order_status": "pending",
        "order_total": "49.99",
        "updated_at": "2026-01-15T12:00:00Z",
        "ingestion_date": "2026-01-15",
    }
    base.update(overrides)
    return base


def test_dedup_keeps_latest(cfg):
    df = pd.DataFrame([
        _row(updated_at="2026-01-15T08:00:00Z", quantity="1"),
        _row(updated_at="2026-01-15T12:00:00Z", quantity="2"),
    ])
    silver, quarantine = local_runner.bronze_to_silver(df, cfg)
    assert len(quarantine) == 0
    assert len(silver) == 1
    assert int(silver.iloc[0]["quantity"]) == 2


def test_uppercase_status(cfg):
    df = pd.DataFrame([_row(order_status=" shipped ")])
    silver, _ = local_runner.bronze_to_silver(df, cfg)
    assert silver.iloc[0]["order_status"] == "SHIPPED"


def test_derived_line_value(cfg):
    df = pd.DataFrame([_row(order_total="100.00")])
    silver, _ = local_runner.bronze_to_silver(df, cfg)
    assert silver.iloc[0]["line_value"] == pytest.approx(100.0)


def test_bad_rows_quarantined(cfg):
    df = pd.DataFrame([
        _row(order_id=""),
        _row(order_id="ORD-00002", quantity="0"),
    ])
    silver, quarantine = local_runner.bronze_to_silver(df, cfg)
    assert len(silver) == 0
    assert len(quarantine) == 2


def test_gold_flat_table(cfg):
    df = pd.DataFrame([_row()])
    silver, _ = local_runner.bronze_to_silver(df, cfg)
    gold = local_runner.silver_to_gold(silver, cfg)
    assert list(gold.keys()) == ["gold_customer_orders"]
    assert "customer_id" not in gold["gold_customer_orders"].columns
