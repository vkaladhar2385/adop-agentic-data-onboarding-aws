"""Unit tests for the catalog/LF-Tag registration script (symmetry with web_events)."""
from workloads.advisory_transactions.scripts.load.register_catalog import plan_lf_tags


def test_lf_tag_plan_only_covers_advisory_pii_columns():
    tags = plan_lf_tags()
    columns = {t["column"] for t in tags}
    assert columns == {"client_ssn", "client_email", "client_name"}
    for t in tags:
        assert t["table"] == "silver_advisory_transactions"


def test_lf_tag_plan_with_explicit_database_skips_yaml_load():
    tags = plan_lf_tags(database="advisory_transactions_db")
    assert all(t["database"] == "advisory_transactions_db" for t in tags)
