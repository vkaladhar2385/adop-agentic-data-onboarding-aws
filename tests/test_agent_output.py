"""Tests for AgentOutput schema and I/O helpers."""

from __future__ import annotations

import json

import pytest

from shared.templates.agent_output_schema import (
    AgentOutput,
    compute_input_hash,
    compute_file_checksum,
)
from shared.utils.agent_output_io import (
    extract_json_from_subagent_response,
    parse_agent_output_payload,
    save_agent_output,
)


def _sample_output(**overrides) -> AgentOutput:
    base = {
        "agent_name": "Metadata Agent",
        "agent_type": "metadata",
        "workload_name": "demo_wl",
        "run_id": "run-001",
        "started_at": "2026-09-08T10:00:00Z",
        "completed_at": "2026-09-08T10:05:00Z",
        "status": "success",
        "artifacts": [{"path": "config/source.yaml", "type": "config", "checksum": "abc"}],
        "tests": {"unit": {"passed": 2, "failed": 0, "total": 2}},
        "blocking_issues": [],
    }
    base.update(overrides)
    return AgentOutput(**base)


def test_agent_output_round_trip():
    out = _sample_output()
    restored = AgentOutput.from_json(out.to_json())
    assert restored.agent_name == out.agent_name
    assert restored.can_proceed is True


def test_invalid_agent_type():
    with pytest.raises(ValueError, match="agent_type"):
        _sample_output(agent_type="invalid")


def test_can_proceed_false_on_blocking_issues():
    out = _sample_output(blocking_issues=["missing PK"])
    assert out.can_proceed is False


def test_from_bedrock_tool_call():
    payload = _sample_output().to_dict()
    block = {"name": "submit_agent_output", "input": payload}
    parsed = AgentOutput.from_bedrock_tool_call(block)
    assert parsed.workload_name == "demo_wl"


def test_compute_input_hash_stable():
    h1 = compute_input_hash({"b": 2, "a": 1})
    h2 = compute_input_hash({"a": 1, "b": 2})
    assert h1 == h2


def test_save_and_parse(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shared.utils.agent_output_io.REPO_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        "shared.utils.agent_trace.REPO_ROOT",
        tmp_path,
    )
    out = _sample_output(workload_name="wl1")
    path = save_agent_output(out, trace=True)
    assert path.is_file()
    parsed = parse_agent_output_payload(json.loads(path.read_text(encoding="utf-8")))
    assert parsed.agent_type == "metadata"


def test_parse_agent_output_payload_blocks_on_failure():
    out = _sample_output(status="failed", blocking_issues=["boom"])
    with pytest.raises(ValueError, match="cannot proceed"):
        parse_agent_output_payload(out.to_dict())


def test_extract_json_from_fenced_block():
    payload = _sample_output().to_dict()
    text = "Here is the result:\n```json\n" + json.dumps(payload) + "\n```"
    extracted = extract_json_from_subagent_response(text)
    assert extracted["agent_type"] == "metadata"


def test_compute_file_checksum(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("hello", encoding="utf-8")
    assert len(compute_file_checksum(str(f))) == 64
