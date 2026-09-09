"""Unit tests for product_inventory Bronze -> Silver / Gold."""
import pandas as pd
import pytest

from workloads.product_inventory.scripts.transform import local_runner


@pytest.fixture()
def cfg():
    return local_runner.load_config("transformations.yaml")


def _row(**overrides):
    base = {
        "sku": "SKU000001",
        "product_name": "Wireless Mouse v1",
        "category": "electronics",
        "warehouse_id": "wh-east-01",
        "on_hand_qty": "100",
        "reserved_qty": "10",
        "unit_cost": "4.00",
        "list_price": "8.00",
        "supplier_id": "SUP-100",
        "supplier_name": "Northwind Goods",
        "status": "active",
        "updated_at": "2026-09-08T12:00:00",
        "ingestion_date": "2026-09-08",
    }
    base.update(overrides)
    return base


def test_dedup_keeps_latest(cfg):
    df = pd.DataFrame([
        _row(updated_at="2026-09-08T08:00:00", on_hand_qty="50"),
        _row(updated_at="2026-09-08T12:00:00", on_hand_qty="100"),
    ])
    silver, quarantine = local_runner.bronze_to_silver(df, cfg)
    assert len(quarantine) == 0
    assert len(silver) == 1
    assert int(silver.iloc[0]["on_hand_qty"]) == 100


def test_uppercase_and_trim(cfg):
    df = pd.DataFrame([_row(category="  electronics  ", status="active", warehouse_id="wh-east-01")])
    silver, _ = local_runner.bronze_to_silver(df, cfg)
    assert silver.iloc[0]["category"] == "ELECTRONICS"
    assert silver.iloc[0]["status"] == "ACTIVE"
    assert silver.iloc[0]["warehouse_id"] == "WH-EAST-01"


def test_derived_columns(cfg):
    df = pd.DataFrame([_row()])
    silver, _ = local_runner.bronze_to_silver(df, cfg)
    row = silver.iloc[0]
    assert int(row["available_qty"]) == 90
    assert float(row["inventory_value"]) == pytest.approx(400.0)
    assert float(row["margin_pct"]) == pytest.approx(0.5)


@pytest.mark.parametrize("bad,reason", [
    ({"sku": ""}, "missing_sku"),
    ({"on_hand_qty": "-8"}, "negative_on_hand"),
])
def test_bad_rows_are_quarantined_not_dropped(cfg, bad, reason):
    second = {"sku": "SKU000002"}
    second.update(bad)
    df = pd.DataFrame([_row(), _row(**second)])
    silver, quarantine = local_runner.bronze_to_silver(df, cfg)
    assert "SKU000002" not in set(silver["sku"].astype(str))
    assert reason in quarantine.iloc[0]["quarantine_reason"]


def test_blank_product_name_is_kept(cfg):
    df = pd.DataFrame([_row(product_name="")])
    silver, quarantine = local_runner.bronze_to_silver(df, cfg)
    assert len(silver) == 1
    assert len(quarantine) == 0


def test_over_reserved_is_kept(cfg):
    df = pd.DataFrame([_row(on_hand_qty="5", reserved_qty="20")])
    silver, quarantine = local_runner.bronze_to_silver(df, cfg)
    assert len(silver) == 1
    assert len(quarantine) == 0
    assert int(silver.iloc[0]["available_qty"]) == -15


def test_gold_is_flat_one_table(cfg):
    silver, _ = local_runner.bronze_to_silver(pd.DataFrame([_row()]), cfg)
    gold = local_runner.silver_to_gold(silver, cfg)
    assert list(gold) == ["gold_product_inventory"]
    assert "sku" in gold["gold_product_inventory"].columns
    assert "available_qty" in gold["gold_product_inventory"].columns
