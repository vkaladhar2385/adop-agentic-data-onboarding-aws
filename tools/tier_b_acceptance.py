#!/usr/bin/env python3
"""Local Tier B acceptance checklist (steps 13–15 preflight, no AWS required)."""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.utils.cedar_policy import sub_agent_mcp_denied  # noqa: E402
from shared.utils.orchestrator import resolve_orchestration_artifacts, resolve_orchestrator  # noqa: E402


def _load_schedule(workload_dir: Path) -> dict:
    path = workload_dir / "config" / "schedule.yaml"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def check_workload(workload: str) -> dict:
    wl_dir = REPO_ROOT / "workloads" / workload
    schedule = _load_schedule(wl_dir)
    orch = resolve_orchestrator(schedule)
    artifacts = resolve_orchestration_artifacts(schedule)
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})

    add("discovery_complete", (wl_dir / ".discovery_complete").is_file())
    add("schedule_orchestrator", orch in ("mwaa", "step_functions", "both"), orch)

    if "dag" in artifacts:
        dag_files = list((wl_dir / "dags").glob("*_pipeline.py"))
        add("mwaa_dag_rendered", bool(dag_files), str(dag_files[0] if dag_files else "missing"))
        if dag_files:
            try:
                ast.parse(dag_files[0].read_text(encoding="utf-8"))
                add("mwaa_dag_syntax", True)
            except SyntaxError as exc:
                add("mwaa_dag_syntax", False, str(exc))

    if "state_machine" in artifacts:
        sfn = wl_dir / "orchestration" / f"{workload}_state_machine.json"
        add("sfn_json_present", sfn.is_file(), str(sfn))

    if schedule.get("ontology_staging"):
        for name in ("ontology.ttl", "mappings.ttl", "ontology_manifest.json"):
            path = wl_dir / "config" / name
            add(f"ontology_{name}", path.is_file(), str(path.relative_to(REPO_ROOT)))

    for agent in ("metadata", "transformation", "quality"):
        allowed, reason = sub_agent_mcp_denied(agent)
        add(f"cedar_denies_mcp_{agent}", not allowed, reason)

    add(
        "gateway_runbook",
        (REPO_ROOT / "prompts/environment-setup/09-deploy-agentcore-gateway.md").is_file(),
    )
    add(
        "gateway_config_tool",
        (REPO_ROOT / "tools/generate_mcp_gateway_config.py").is_file(),
    )
    add("mwaa_sync_tool", (REPO_ROOT / "tools/sync_mwaa_dags.py").is_file())

    local_ok = all(c["ok"] for c in checks if not c["check"].startswith("aws_"))
    pending_aws = [
        "Step 13: Deploy AgentCore Gateway OR --skip-gateway for local MCP",
        "Step 13 verify: mcp_health_check.py --config .mcp.gateway.json",
        "Step 14 (optional demo): MWAA DAG sync for customer_orders only",
        "Step 15: SFN E2E on supplier_lead_times (default) — terraform apply + start-execution",
    ]
    pending_aws = [p for p in pending_aws if p]

    return {
        "workload": workload,
        "orchestrator": orch,
        "artifacts": sorted(artifacts),
        "local_pass": local_ok,
        "checks": checks,
        "pending_aws": pending_aws,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workload", default="customer_orders")
    args = ap.parse_args()
    report = check_workload(args.workload)
    print(json.dumps(report, indent=2))
    if not report["local_pass"]:
        print("\nTier B local acceptance: FAIL", file=sys.stderr)
        return 1
    print("\nTier B local acceptance: PASS (AWS steps still pending)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
