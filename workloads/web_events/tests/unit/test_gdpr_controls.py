"""GDPR-specific unit tests for web_events."""
from datetime import datetime, timezone

import pandas as pd
import pytest

from workloads.web_events.scripts.transform import local_runner


@pytest.fixture()
def cfg():
    return local_runner.load_config("transformations.yaml")


def _event(**over):
    base = {
        "event_id": "EVT0000001",
        "user_id": "U1001",
        "session_id": "SES1001-20260903",
        "event_type": "page_view",
        "event_ts": datetime(2026, 9, 3, 12, 1, tzinfo=timezone.utc).isoformat(),
        "page_path": "/",
        "traffic_source": "organic",
        "ip_address": "203.0.113.45",
        "user_email": "user1001@example.com",
        "consent_analytics": True,
        "country": "US",
        "ingestion_ts": datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc).isoformat(),
    }
    base.update(over)
    return base


def test_no_consent_never_enters_silver(cfg):
    df = pd.DataFrame([_event(), _event(event_id="EVT0000002", consent_analytics=False)])
    silver, quarantine, suppressed = local_runner.bronze_to_silver(df, cfg)
    assert len(suppressed) == 1
    assert "EVT0000002" not in set(silver["event_id"])
    assert "EVT0000002" not in set(quarantine["event_id"])


def test_user_id_hashed_and_ip_masked(cfg):
    df = pd.DataFrame([_event()])
    silver, _, _ = local_runner.bronze_to_silver(df, cfg)
    row = silver.iloc[0]
    assert row["user_id"] != "U1001"
    assert row["ip_address"] == "203.0.113.0"
    assert row["user_email"].startswith("u***@")


def test_invalid_type_quarantined(cfg):
    df = pd.DataFrame([_event(), _event(event_id="EVT0000002", event_type="not-a-type")])
    silver, quarantine, _ = local_runner.bronze_to_silver(df, cfg)
    assert "EVT0000002" in set(quarantine["event_id"])
    assert "invalid_event_type" in quarantine.iloc[0]["quarantine_reason"]


def test_gold_suppresses_email_and_ip(cfg):
    df = pd.DataFrame([_event()])
    silver, _, _ = local_runner.bronze_to_silver(df, cfg)
    gold = local_runner.silver_to_gold(silver, cfg)
    for name, tbl in gold.items():
        assert "user_email" not in tbl.columns, name
        assert "ip_address" not in tbl.columns, name


def test_erasure_index_uses_hashed_token(cfg):
    df = pd.DataFrame([_event(), _event(event_id="EVT0000002")])
    silver, _, _ = local_runner.bronze_to_silver(df, cfg)
    gold = local_runner.silver_to_gold(silver, cfg)
    idx = gold["gold_erasure_index"]
    assert len(idx) == 1
    assert idx.iloc[0]["user_id"] == silver.iloc[0]["user_id"]
    assert "DELETE FROM silver_web_events" in idx.iloc[0]["erasure_hook"]
