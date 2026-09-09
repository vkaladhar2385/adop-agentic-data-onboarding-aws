"""Start Step Functions pipeline and poll until terminal state."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

TERMINAL = frozenset({"SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"})


def _load_schedule(workload: str, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    path = root / "workloads" / workload / "config" / "schedule.yaml"
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def build_state_machine_input(workload: str, bucket: str) -> dict[str, str]:
    return {
        "source_path": f"s3://{bucket}/landing/{workload}/",
        "bronze_path": f"s3://{bucket}/bronze/{workload}/",
        "silver_path": f"s3://{bucket}/silver/{workload}/",
        "gold_path": f"s3://{bucket}/gold/{workload}/",
    }


def state_machine_name(workload: str, repo_root: Path | None = None) -> str:
    schedule = _load_schedule(workload, repo_root)
    name = (schedule.get("execution") or {}).get("state_machine")
    return str(name or f"{workload}_pipeline")


def poll_interval_seconds(workload: str, repo_root: Path | None = None) -> int:
    schedule = _load_schedule(workload, repo_root)
    return int((schedule.get("execution") or {}).get("interval_seconds") or 30)


def poll_timeout_seconds(workload: str, repo_root: Path | None = None) -> int:
    schedule = _load_schedule(workload, repo_root)
    minutes = int((schedule.get("execution") or {}).get("timeout_minutes") or 60)
    return minutes * 60


def resolve_state_machine_arn(
    workload: str,
    *,
    region: str | None = None,
    profile: str | None = None,
    repo_root: Path | None = None,
) -> str:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 required for SFN E2E") from exc

    session_kwargs: dict[str, Any] = {}
    if profile:
        session_kwargs["profile_name"] = profile
    if region:
        session_kwargs["region_name"] = region
    sfn = boto3.Session(**session_kwargs).client("stepfunctions")
    name = state_machine_name(workload, repo_root)
    paginator = sfn.get_paginator("list_state_machines")
    for page in paginator.paginate():
        for sm in page.get("stateMachines", []):
            if sm.get("name") == name:
                return sm["stateMachineArn"]
    raise LookupError(f"Step Functions state machine not found: {name}")


def start_and_wait(
    workload: str,
    bucket: str,
    *,
    region: str | None = None,
    profile: str | None = None,
    repo_root: Path | None = None,
    execution_name: str | None = None,
) -> dict[str, Any]:
    """Start pipeline execution and poll until SUCCEEDED or failure."""
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 required for SFN E2E") from exc

    session_kwargs: dict[str, Any] = {}
    if profile:
        session_kwargs["profile_name"] = profile
    if region:
        session_kwargs["region_name"] = region
    sfn = boto3.Session(**session_kwargs).client("stepfunctions")

    sm_arn = resolve_state_machine_arn(workload, region=region, profile=profile, repo_root=repo_root)
    payload = build_state_machine_input(workload, bucket)
    exec_name = execution_name or f"{workload}-e2e-{uuid.uuid4().hex[:12]}"
    resp = sfn.start_execution(
        stateMachineArn=sm_arn,
        name=exec_name,
        input=json.dumps(payload),
    )
    execution_arn = resp["executionArn"]
    print(f"Started execution: {execution_arn}", flush=True)

    interval = poll_interval_seconds(workload, repo_root)
    deadline = time.time() + poll_timeout_seconds(workload, repo_root)
    status = "RUNNING"
    while time.time() < deadline:
        desc = sfn.describe_execution(executionArn=execution_arn)
        status = desc["status"]
        print(f"  status={status}", flush=True)
        if status in TERMINAL:
            result = {
                "execution_arn": execution_arn,
                "status": status,
                "state_machine_arn": sm_arn,
                "input": payload,
            }
            if status != "SUCCEEDED":
                result["cause"] = desc.get("cause", "")
                result["error"] = desc.get("error", "")
            return result
        time.sleep(interval)

    raise TimeoutError(
        f"Execution {execution_arn} did not finish within timeout (last status={status})"
    )
