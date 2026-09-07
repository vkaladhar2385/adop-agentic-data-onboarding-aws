"""Unit tests for the extract / quality / load scripts (symmetry with advisory_transactions)."""
import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from workloads.web_events.scripts.extract.ingest_to_bronze import run_local as ingest_local
from workloads.web_events.scripts.load.register_catalog import plan_lf_tags
from workloads.web_events.scripts.quality.run_quality_checks import evaluate


def test_ingest_local_writes_bronze(tmp_path):
    events = [{
        "event_id": "EVT0000001", "user_id": "U1001", "session_id": "SES1001",
        "event_type": "page_view", "event_ts": datetime(2026, 9, 3, 12, tzinfo=timezone.utc).isoformat(),
        "page_path": "/", "traffic_source": "organic", "ip_address": "203.0.113.1",
        "user_email": "u1001@example.com", "consent_analytics": True, "country": "US",
        "ingestion_ts": datetime(2026, 9, 3, 12, tzinfo=timezone.utc).isoformat(),
    }]
    src = tmp_path / "web_events.jsonl"
    src.write_text(json.dumps(events[0]) + "\n", encoding="utf-8")

    target = ingest_local(str(src), str(tmp_path / "out"))
    assert target.endswith("bronze_web_events.jsonl")
    written = pd.read_json(target, lines=True)
    assert len(written) == 1
    assert written.iloc[0]["event_id"] == "EVT0000001"


def test_lf_tag_plan_only_covers_web_events_pii_columns():
    tags = plan_lf_tags()
    columns = {t["column"] for t in tags}
    assert columns == {"user_id", "user_email", "ip_address"}
    for t in tags:
        assert t["table"] == "silver_web_events"


def test_quality_evaluate_matches_gate_thresholds():
    df = pd.DataFrame([{
        "event_id": "EVT1", "event_type": "page_view", "traffic_source": "organic",
    }])
    report = evaluate(df, "silver")
    assert report["zone"] == "silver"
    assert report["gate_threshold"] == pytest.approx(0.80)
