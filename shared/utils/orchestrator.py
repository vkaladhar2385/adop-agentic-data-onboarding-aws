"""Resolve workload orchestrator from schedule config."""

from __future__ import annotations

from typing import Any

DEFAULT_ORCHESTRATOR = "step_functions"
VALID_ORCHESTRATORS = frozenset({"step_functions", "mwaa", "both"})
ORCHESTRATION_ARTIFACTS = frozenset({"state_machine", "dag"})


def resolve_orchestrator(schedule_config: dict[str, Any] | None) -> str:
    """Return orchestrator id; default Step Functions when omitted."""
    if not schedule_config:
        return DEFAULT_ORCHESTRATOR
    raw = schedule_config.get("orchestrator")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return DEFAULT_ORCHESTRATOR
    value = str(raw).strip().lower()
    if value not in VALID_ORCHESTRATORS:
        raise ValueError(
            f"Invalid orchestrator {raw!r}; expected one of {sorted(VALID_ORCHESTRATORS)}"
        )
    return value


def resolve_orchestration_artifacts(schedule_config: dict[str, Any] | None) -> frozenset[str]:
    """Return which orchestration artifacts codegen should emit for a workload."""
    if not schedule_config:
        return frozenset({"state_machine"})
    if schedule_config.get("emit_both_orchestrators"):
        return frozenset({"state_machine", "dag"})
    orch = resolve_orchestrator(schedule_config)
    if orch == "both":
        return frozenset({"state_machine", "dag"})
    if orch == "mwaa":
        return frozenset({"dag"})
    return frozenset({"state_machine"})
