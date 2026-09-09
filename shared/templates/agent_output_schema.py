"""
Enforced output schema for ALL sub-agent responses.

Every sub-agent MUST finish with an AgentOutput payload. The main onboarding agent
validates via ``AgentOutput.from_dict`` before advancing to the next station.

Reference: official ADOP ``shared/templates/agent_output_schema.py``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any

VALID_AGENT_TYPES = {
    "dedup",
    "metadata",
    "transformation",
    "quality",
    "dag",
    "analysis",
    "devops",
}
VALID_STATUSES = {"success", "failed", "partial"}

SUBMIT_OUTPUT_TOOL = {
    "toolSpec": {
        "name": "submit_agent_output",
        "description": (
            "Submit your completed work. You MUST call this tool to finish. "
            "Do not respond in plain text — call this tool with a JSON payload."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string"},
                    "agent_type": {
                        "type": "string",
                        "enum": sorted(VALID_AGENT_TYPES),
                    },
                    "workload_name": {"type": "string"},
                    "run_id": {"type": "string"},
                    "started_at": {"type": "string"},
                    "completed_at": {"type": "string"},
                    "status": {"type": "string", "enum": sorted(VALID_STATUSES)},
                    "artifacts": {"type": "array", "items": {"type": "object"}},
                    "tests": {"type": "object"},
                    "blocking_issues": {"type": "array", "items": {"type": "string"}},
                    "warnings": {"type": "array", "items": {"type": "string"}},
                    "next_steps": {"type": "array", "items": {"type": "string"}},
                    "decisions": {"type": "array", "items": {"type": "object"}},
                    "memory_hints": {"type": "array", "items": {"type": "object"}},
                    "input_hash": {"type": "string"},
                    "output_hash": {"type": "string"},
                },
                "required": [
                    "agent_name",
                    "agent_type",
                    "workload_name",
                    "run_id",
                    "started_at",
                    "completed_at",
                    "status",
                    "artifacts",
                    "blocking_issues",
                    "tests",
                ],
            }
        },
    }
}


@dataclass
class AgentOutput:
    """Enforced schema for ALL sub-agent responses."""

    agent_name: str
    agent_type: str
    workload_name: str
    run_id: str
    started_at: str
    completed_at: str
    status: str

    artifacts: list[dict[str, str]] = field(default_factory=list)
    tests: dict[str, dict[str, int]] = field(default_factory=dict)
    blocking_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    memory_hints: list[dict[str, str]] = field(default_factory=list)
    input_hash: str = ""
    output_hash: str = ""

    def __post_init__(self) -> None:
        if self.agent_type not in VALID_AGENT_TYPES:
            raise ValueError(
                f"agent_type must be one of {sorted(VALID_AGENT_TYPES)}, got {self.agent_type!r}"
            )
        if self.status not in VALID_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(VALID_STATUSES)}, got {self.status!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentOutput:
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_json(cls, raw: str) -> AgentOutput:
        return cls.from_dict(json.loads(raw))

    @classmethod
    def from_bedrock_tool_call(cls, tool_use_block: dict[str, Any]) -> AgentOutput:
        if tool_use_block.get("name") != "submit_agent_output":
            raise ValueError(
                f"Expected tool 'submit_agent_output', got {tool_use_block.get('name')!r}"
            )
        return cls.from_dict(tool_use_block["input"])

    @property
    def can_proceed(self) -> bool:
        return self.status == "success" and len(self.blocking_issues) == 0

    @property
    def needs_retry(self) -> bool:
        return self.status == "failed" and len(self.blocking_issues) > 0

    def add_decision(
        self,
        category: str,
        reasoning: str,
        choice: str,
        alternatives: list[str] | None = None,
        rejection_reasons: dict[str, str] | None = None,
        confidence: str = "high",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        decision = {
            "decision_id": f"d-{len(self.decisions) + 1:03d}",
            "category": category,
            "reasoning": reasoning,
            "choice_made": choice,
            "alternatives_considered": alternatives or [],
            "rejection_reasons": rejection_reasons or {},
            "confidence": confidence,
            "context": context or {},
        }
        self.decisions.append(decision)
        return decision

    @property
    def total_tests_passed(self) -> int:
        return sum(phase.get("passed", 0) for phase in self.tests.values())

    @property
    def total_tests_failed(self) -> int:
        return sum(phase.get("failed", 0) for phase in self.tests.values())

    @property
    def total_tests(self) -> int:
        return sum(phase.get("total", 0) for phase in self.tests.values())

    @staticmethod
    def header(agent_name: str, workload: str, run_id: str) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return (
            "\n"
            "================================================================\n"
            f"  AGENT: {agent_name}\n"
            f"  WORKLOAD: {workload}\n"
            f"  RUN_ID: {run_id}\n"
            f"  STARTED: {now}\n"
            "================================================================\n"
        )

    def footer(self) -> str:
        icon = "PASS" if self.status == "success" else "FAIL"
        return (
            "\n"
            "----------------------------------------------------------------\n"
            f"  STATUS: {icon} ({self.status})\n"
            f"  TESTS: {self.total_tests_passed} passed, {self.total_tests_failed} failed\n"
            f"  ARTIFACTS: {len(self.artifacts)}\n"
            f"  BLOCKING: {len(self.blocking_issues)}\n"
            "----------------------------------------------------------------\n"
        )


def compute_input_hash(inputs: dict[str, Any]) -> str:
    raw = json.dumps(inputs, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def compute_file_checksum(filepath: str) -> str:
    digest = hashlib.sha256()
    with open(filepath, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()
