"""Integration test: full Bronze -> Silver -> Gold on generated sample data."""
from pathlib import Path

import pytest

from demo.data_generators.generate_advisory_transactions import generate, HEADER
from workloads.advisory_transactions.scripts.transform import local_runner
from workloads.advisory_transactions.scripts.quality.run_quality_checks import evaluate

from datetime import date
import csv


@pytest.fixture()
def sample_csv(tmp_path):
    records = generate(rows=200, seed=42, ingestion_day=date(2026, 9, 3))
    path = tmp_path / "advisory_transactions.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER)
        w.writeheader()
        w.writerows(records)
    return path


def test_end_to_end_gates_pass_and_star_schema_shapes(sample_csv):
    result = local_runner.run_pipeline(sample_csv)

    # Dirty rows were quarantined, not dropped silently.
    assert len(result["quarantine"]) >= 5
    assert "quarantine_reason" in result["quarantine"].columns

    # Silver + Gold gates both pass on clean data.
    silver_report = evaluate(result["silver"], "silver")
    assert silver_report["passed"], silver_report["critical_failures"]

    gold = result["gold"]
    gold_report = evaluate(gold["fact_transactions"], "gold")
    assert gold_report["passed"], gold_report["critical_failures"]

    # Star schema present with expected tables.
    for tbl in ["fact_transactions", "dim_account", "dim_advisor",
                "dim_security", "dim_date", "gold_advisor_daily_summary"]:
        assert tbl in gold
        assert len(gold[tbl]) > 0

    # Fact row count matches Silver clean row count (no leakage).
    assert len(gold["fact_transactions"]) == len(result["silver"])


def test_gold_suppresses_pii(sample_csv):
    result = local_runner.run_pipeline(sample_csv)
    for name, tbl in result["gold"].items():
        for col in ["client_ssn", "client_email", "client_name"]:
            assert col not in tbl.columns, f"{col} leaked into gold.{name}"
