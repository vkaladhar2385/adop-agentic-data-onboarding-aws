"""Persist and load sub-agent AgentOutput payloads for the factory orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shared.templates.agent_output_schema import AgentOutput
from shared.utils.agent_trace import append_trace

REPO_ROOT = Path(__file__).resolve().parents[2]


def agent_outputs_dir(workload: str) -> Path:
    return REPO_ROOT / "workloads" / workload / "logs" / "agent_outputs"


def save_agent_output(output: AgentOutput, *, trace: bool = True) -> Path:
    """Write validated AgentOutput JSON; optionally append factory trace line."""
    out_dir = agent_outputs_dir(output.workload_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{output.agent_type}.json"
    path.write_text(output.to_json() + "\n", encoding="utf-8")
    if trace:
        append_trace(
            output.workload_name,
            output.agent_type,
            "ok" if output.can_proceed else "blocked",
            agent=output.agent_type,
            run_id=output.run_id,
            agent_status=output.status,
        )
    return path


def load_agent_output(workload: str, agent_type: str) -> AgentOutput:
    path = agent_outputs_dir(workload) / f"{agent_type}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing agent output: {path}")
    return AgentOutput.from_json(path.read_text(encoding="utf-8"))


def parse_agent_output_payload(data: dict[str, Any]) -> AgentOutput:
    """Validate dict from sub-agent JSON; raise ValueError if orchestrator cannot proceed."""
    output = AgentOutput.from_dict(data)
    if not output.can_proceed:
        issues = "; ".join(output.blocking_issues) or output.status
        raise ValueError(f"Sub-agent {output.agent_type!r} cannot proceed: {issues}")
    return output


def extract_json_from_subagent_response(text: str) -> dict[str, Any]:
    """Best-effort parse when sub-agent wraps JSON in a fenced code block."""
    stripped = text.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)
    marker = "```json"
    if marker in stripped:
        start = stripped.index(marker) + len(marker)
        end = stripped.index("```", start)
        return json.loads(stripped[start:end].strip())
    if "```" in stripped:
        start = stripped.index("```") + 3
        if stripped[start : start + 1].isspace():
            start = stripped.find("\n", start) + 1
        end = stripped.index("```", start)
        return json.loads(stripped[start:end].strip())
    raise ValueError("Sub-agent response did not contain parseable AgentOutput JSON")
