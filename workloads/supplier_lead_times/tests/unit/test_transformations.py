"""Unit tests for supplier_lead_times Bronze -> Silver / Gold."""
import pandas as pd
import pytest

from workloads.supplier_lead_times.scripts.transform import local_runner


@pytest.fixture()
def cfg():
    return local_runner.load_config("transformations.yaml")


def _row(**overrides):
    base = {
        "supplier_id": "SUP-001",
        "supplier_name": "Northwind Components",
        "product_category": "electronics",
        "lead_time_days": "14",
        "min_order_qty": "100",
        "country_code": "us",
        "is_preferred": "true",
        "effective_date": "2026-09-08",
        "updated_at": "2026-09-08T12:00:00",
        "ingestion_date": "2026-09-08",
    }
    base.update(overrides)
    return base


def test_dedup_keeps_latest(cfg):
    df = pd.DataFrame([
        _row(updated_at="2026-09-08T08:00:00", lead_time_days="10"),
        _row(updated_at="2026-09-08T12:00:00", lead_time_days="14"),
    ])
    silver, quarantine = local_runner.bronze_to_silver(df, cfg)
    assert len(quarantine) == 0
    assert len(silver) == 1
    assert int(silver.iloc[0]["lead_time_days"]) == 14


def test_uppercase_category(cfg):
    df = pd.DataFrame([_row(product_category="  electronics  ", country_code=" us ")])
    silver, _ = local_runner.bronze_to_silver(df, cfg)
    assert silver.iloc[0]["product_category"] == "ELECTRONICS"
    assert silver.iloc[0]["country_code"] == "US"


def test_derived_lead_time_weeks(cfg):
    df = pd.DataFrame([_row(lead_time_days="14")])
    silver, _ = local_runner.bronze_to_silver(df, cfg)
    assert silver.iloc[0]["lead_time_weeks"] == pytest.approx(2.0)


def test_bad_rows_quarantined(cfg):
    df = pd.DataFrame([
        _row(supplier_id=""),
        _row(supplier_id="SUP-002", lead_time_days="-1"),
    ])
    silver, quarantine = local_runner.bronze_to_silver(df, cfg)
    assert len(silver) == 0
    assert len(quarantine) == 2


def test_gold_flat_table(cfg):
    df = pd.DataFrame([_row()])
    silver, _ = local_runner.bronze_to_silver(df, cfg)
    gold = local_runner.silver_to_gold(silver, cfg)
    assert list(gold.keys()) == ["gold_supplier_lead_times"]
    assert len(gold["gold_supplier_lead_times"]) == 1
