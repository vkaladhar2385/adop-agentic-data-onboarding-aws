import json

from shared.utils.structured_logger import StructuredLogger


def test_info_emits_json_line_on_stderr(capsys):
    log = StructuredLogger("quality", "web_events", "run-1")
    log.info("quality_gate", zone="silver", passed=True, score=0.99)
    err = capsys.readouterr().err.strip()
    rec = json.loads(err)
    assert rec["level"] == "INFO"
    assert rec["agent"] == "quality"
    assert rec["workload"] == "web_events"
    assert rec["run_id"] == "run-1"
    assert rec["message"] == "quality_gate"
    assert rec["zone"] == "silver"
    assert rec["passed"] is True


def test_phase_boundary(capsys):
    log = StructuredLogger("main", "product_inventory")
    log.phase_boundary("deploy", "ok")
    rec = json.loads(capsys.readouterr().err.strip())
    assert rec["level"] == "PHASE"
    assert rec["phase"] == "deploy"
    assert rec["status"] == "ok"
