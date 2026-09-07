from datetime import datetime, timezone
from pathlib import Path

from demo.data_generators.generate_web_events import generate
from workloads.web_events.scripts.quality.run_quality_checks import evaluate
from workloads.web_events.scripts.transform import local_runner

import json


def test_end_to_end_gdpr_pipeline(tmp_path: Path):
    events = generate(240, 7, datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc))
    src = tmp_path / "web_events.jsonl"
    src.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")

    result = local_runner.run_pipeline(src)
    assert len(result["suppressed_no_consent"]) >= 1
    assert len(result["quarantine"]) >= 2

    rules = local_runner.load_config("quality_rules.yaml")
    silver_report = evaluate(result["silver"], "silver", rules)
    assert silver_report["passed"], silver_report["critical_failures"]

    gold = result["gold"]
    assert "gold_hourly_traffic" in gold and len(gold["gold_hourly_traffic"]) > 0
    for tbl in gold.values():
        assert "user_email" not in tbl.columns
        assert "ip_address" not in tbl.columns

    gold_report = evaluate(gold["gold_hourly_traffic"], "gold", rules)
    assert gold_report["passed"], gold_report["critical_failures"]
