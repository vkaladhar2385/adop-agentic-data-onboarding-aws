"""Factory provision orchestration (Option B — no-laptop API path).

Harness → Gateway factory tools → Step Functions ``adop_factory_provision``.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUEST_SCHEMA = REPO_ROOT / "contracts" / "v1" / "factory_provision_request.schema.json"
FACTORY_SFN_NAME = os.getenv("ADOP_FACTORY_SFN_NAME", "adop_factory_provision")

# v1: pre-onboarded demo workloads only (expand after API onboarding exists).
DEFAULT_ALLOWED_WORKLOADS = frozenset(
    {"supplier_lead_times", "product_inventory", "advisory_transactions", "web_events"}
)


def _load_schema() -> dict[str, Any]:
    return json.loads(REQUEST_SCHEMA.read_text(encoding="utf-8"))


def allowed_workloads() -> frozenset[str]:
    raw = os.getenv("ADOP_FACTORY_ALLOWED_WORKLOADS", "")
    if raw.strip():
        return frozenset(w.strip() for w in raw.split(",") if w.strip())
    return DEFAULT_ALLOWED_WORKLOADS


def validate_request(payload: dict[str, Any]) -> list[str]:
    """Return human-readable validation errors; empty list means OK."""
    errors: list[str] = []
    try:
        jsonschema.validate(instance=payload, schema=_load_schema())
    except jsonschema.ValidationError as exc:
        return [exc.message]

    workload = payload["workload"]
    if workload not in allowed_workloads():
        errors.append(
            f"workload '{workload}' not in factory allowlist: {sorted(allowed_workloads())}"
        )

    workload_dir = REPO_ROOT / "workloads" / workload
    if not workload_dir.is_dir():
        errors.append(f"workload directory missing: workloads/{workload}")
    elif not (workload_dir / ".discovery_complete").is_file():
        errors.append(f"workloads/{workload}/.discovery_complete missing (Phase 1 not done)")

    if not payload.get("approve"):
        errors.append("approve must be true (human must type APPROVE in Harness)")

    bucket = payload["bucket"]
    if bucket.startswith("s3://"):
        errors.append("bucket must not include s3:// prefix")

    return errors


def build_factory_input(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize request for Step Functions execution input."""
    return {
        "workload": payload["workload"],
        "bucket": payload["bucket"],
        "run_e2e": bool(payload.get("run_e2e", True)),
        "session_id": payload.get("session_id"),
        "requested_by": payload.get("requested_by"),
        "provision_id": f"factory-{uuid.uuid4().hex[:12]}",
    }


def factory_state_machine_arn(
    *,
    region: str,
    account_id: str,
    name: str | None = None,
) -> str:
    sm_name = name or FACTORY_SFN_NAME
    return f"arn:aws:states:{region}:{account_id}:stateMachine:{sm_name}"


def resolve_factory_state_machine_arn(
    *,
    region: str | None = None,
    profile: str | None = None,
    name: str | None = None,
) -> str:
    import boto3

    session_kwargs: dict[str, Any] = {}
    if profile:
        session_kwargs["profile_name"] = profile
    if region:
        session_kwargs["region_name"] = region
    session = boto3.Session(**session_kwargs)
    account_id = session.client("sts").get_caller_identity()["Account"]
    region = region or session.region_name or "us-east-1"
    sm_name = name or FACTORY_SFN_NAME

    sfn = session.client("stepfunctions")
    paginator = sfn.get_paginator("list_state_machines")
    for page in paginator.paginate():
        for sm in page.get("stateMachines", []):
            if sm.get("name") == sm_name:
                return sm["stateMachineArn"]

    # Expected until Terraform module is applied (Step 3).
    return factory_state_machine_arn(region=region, account_id=account_id, name=sm_name)


def start_factory_provision(
    payload: dict[str, Any],
    *,
    region: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    """Validate and start factory provision Step Functions execution."""
    errors = validate_request(payload)
    if errors:
        raise ValueError("; ".join(errors))

    import boto3

    session_kwargs: dict[str, Any] = {}
    if profile:
        session_kwargs["profile_name"] = profile
    if region:
        session_kwargs["region_name"] = region
    session = boto3.Session(**session_kwargs)
    sfn = session.client("stepfunctions")

    sm_arn = resolve_factory_state_machine_arn(region=region, profile=profile)
    body = build_factory_input(payload)
    exec_name = re.sub(r"[^a-zA-Z0-9-_]", "-", f"{body['workload']}-{body['provision_id']}")[:80]

    try:
        resp = sfn.start_execution(
            stateMachineArn=sm_arn,
            name=exec_name,
            input=json.dumps(body),
        )
    except sfn.exceptions.StateMachineDoesNotExist:
        raise LookupError(
            f"Factory state machine not deployed: {FACTORY_SFN_NAME}. "
            "Apply iac/terraform/modules/factory_provision (Option B Step 3)."
        ) from None

    return {
        "status": "STARTED",
        "execution_arn": resp["executionArn"],
        "provision_id": body["provision_id"],
        "workload": body["workload"],
        "bucket": body["bucket"],
        "run_e2e": body["run_e2e"],
    }


def describe_factory_provision(
    execution_arn: str,
    *,
    region: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    import boto3

    session_kwargs: dict[str, Any] = {}
    if profile:
        session_kwargs["profile_name"] = profile
    if region:
        session_kwargs["region_name"] = region
    sfn = boto3.Session(**session_kwargs).client("stepfunctions")
    desc = sfn.describe_execution(executionArn=execution_arn)
    out: dict[str, Any] = {
        "execution_arn": execution_arn,
        "status": desc["status"],
        "start_date": desc.get("startDate").isoformat() if desc.get("startDate") else None,
        "stop_date": desc.get("stopDate").isoformat() if desc.get("stopDate") else None,
    }
    if desc.get("input"):
        try:
            out["input"] = json.loads(desc["input"])
        except json.JSONDecodeError:
            out["input"] = desc["input"]
    if desc.get("output"):
        try:
            out["output"] = json.loads(desc["output"])
        except json.JSONDecodeError:
            out["output"] = desc["output"]
    if desc["status"] in ("FAILED", "TIMED_OUT", "ABORTED"):
        out["error"] = desc.get("error")
        out["cause"] = desc.get("cause")
    return out
