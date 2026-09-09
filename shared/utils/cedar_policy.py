"""Lightweight Cedar authorization helper for sub-agent MCP boundaries (Track B)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

POLICIES_DIR = Path(__file__).resolve().parents[1] / "policies"
AGENT_AUTH_DIR = POLICIES_DIR / "agent_authorization"
SCHEMA_FILE = POLICIES_DIR / "schema.cedarschema"

SUB_AGENTS = frozenset(
    {"metadata", "transformation", "quality", "dag", "ontology_staging", "router"}
)


@dataclass
class AgentPrincipal:
    agent_type: str
    execution_context: str = "sub_agent"
    workload_name: str = ""


@dataclass
class WorkloadFile:
    file_type: str
    zone: str = "staging"


@dataclass
class DataZone:
    zone: str
    workload_name: str = ""


@dataclass
class McpTool:
    server_name: str
    tool_name: str


class CedarPolicyEvaluator:
    """Evaluate agent authorization; cedarpy when available, structural fallback otherwise."""

    def is_authorized(
        self,
        agent: AgentPrincipal,
        action: str,
        resource: Any,
    ) -> tuple[bool, str]:
        try:
            return self._evaluate_cedarpy(agent, action, resource)
        except Exception as exc:
            return self._fallback_agent_auth(agent, action, resource, str(exc))

    def _evaluate_cedarpy(
        self,
        agent: AgentPrincipal,
        action: str,
        resource: Any,
    ) -> tuple[bool, str]:
        import cedarpy  # optional dependency

        if not hasattr(cedarpy, "is_authorized"):
            raise ImportError("cedarpy missing is_authorized")

        policies = self._load_policy_texts()
        entities = [
            {
                "uid": {
                    "type": "DataOnboarding::AgentPrincipal",
                    "id": agent.agent_type,
                },
                "attrs": {
                    "agentType": agent.agent_type,
                    "executionContext": agent.execution_context,
                    "workloadName": agent.workload_name,
                },
                "parents": [],
            }
        ]
        resource_uid = self._resource_uid(resource)
        authz = cedarpy.is_authorized(
            entities,
            f"DataOnboarding::Action::\"{action}\"",
            resource_uid,
            policies,
            self._schema_text(),
        )
        allowed = bool(getattr(authz, "allowed", authz))
        return allowed, "Cedar: ALLOW" if allowed else "Cedar: DENY"

    def _load_policy_texts(self) -> list[str]:
        texts: list[str] = []
        for path in sorted(AGENT_AUTH_DIR.glob("*.cedar")):
            texts.append(path.read_text(encoding="utf-8"))
        return texts

    def _schema_text(self) -> str:
        if SCHEMA_FILE.is_file():
            return SCHEMA_FILE.read_text(encoding="utf-8")
        return ""

    def _resource_uid(self, resource: Any) -> dict:
        if isinstance(resource, McpTool):
            return {
                "type": "DataOnboarding::McpTool",
                "id": f"{resource.server_name}/{resource.tool_name}",
            }
        if isinstance(resource, WorkloadFile):
            return {"type": "DataOnboarding::WorkloadFile", "id": resource.file_type}
        if isinstance(resource, DataZone):
            return {"type": "DataOnboarding::DataZone", "id": resource.zone}
        return {"type": "DataOnboarding::WorkloadFile", "id": "unknown"}

    def _fallback_agent_auth(
        self,
        agent: AgentPrincipal,
        action: str,
        resource: Any,
        error: str = "",
    ) -> tuple[bool, str]:
        prefix = "Fallback"
        agent_type = agent.agent_type

        if agent_type == "router":
            if action in ("ReadFile", "ReadData"):
                return True, f"{prefix}: router can read"
            return False, f"{prefix}: router is read-only"

        if agent_type == "onboarding" and agent.execution_context == "main_conversation":
            return True, f"{prefix}: onboarding has full access in main conversation"

        if action == "InvokeTool" and agent_type not in ("onboarding",):
            return False, f"{prefix}: sub-agent cannot invoke MCP"

        if agent_type == "metadata":
            if action == "WriteFile" and isinstance(resource, WorkloadFile):
                if resource.file_type != "config":
                    return False, f"{prefix}: metadata can only write config"
            if action == "WriteData" and isinstance(resource, DataZone):
                if resource.zone == "publish":
                    return False, f"{prefix}: metadata cannot write publish"

        if agent_type == "transformation":
            if action == "WriteData" and isinstance(resource, DataZone):
                if resource.zone == "publish":
                    return False, f"{prefix}: transformation cannot write publish"
            if action == "WriteFile" and isinstance(resource, WorkloadFile):
                if resource.file_type not in ("script", "sql"):
                    return False, f"{prefix}: transformation can only write scripts/sql"

        if agent_type == "quality":
            if action in ("WriteData", "PromoteData"):
                return False, f"{prefix}: quality cannot modify data"
            if action == "WriteFile" and isinstance(resource, WorkloadFile):
                if resource.file_type != "config":
                    return False, f"{prefix}: quality can only write config"

        if agent_type == "dag":
            if action in ("ReadData", "WriteData"):
                return False, f"{prefix}: dag cannot access data directly"
            if action == "WriteFile" and isinstance(resource, WorkloadFile):
                if resource.file_type != "dag":
                    return False, f"{prefix}: dag can only write dag files"

        if agent_type == "ontology_staging":
            if action == "InvokeTool":
                return False, f"{prefix}: ontology staging cannot invoke MCP"
            if action == "WriteFile" and isinstance(resource, WorkloadFile):
                if resource.file_type not in ("config",):
                    return False, f"{prefix}: ontology staging writes config TTL only"

        return True, f"{prefix}: ALLOW"


def sub_agent_mcp_denied(agent_type: str) -> tuple[bool, str]:
    """Simulate a sub-agent MCP call — should be denied for build sub-agents."""
    evaluator = CedarPolicyEvaluator()
    agent = AgentPrincipal(agent_type=agent_type, execution_context="sub_agent")
    tool = McpTool(server_name="glue-athena", tool_name="run_query")
    return evaluator.is_authorized(agent, "InvokeTool", tool)
