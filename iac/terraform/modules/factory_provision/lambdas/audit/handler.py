"""Factory provision SFN step — write audit JSON to s3://bucket/provision-runs/{id}.json."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))

from shared.deploy.factory_provision import (  # noqa: E402
    build_audit_record,
    factory_execution_arn,
    write_provision_audit,
)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    state = event.get("state") or event
    status = event.get("status", "SUCCEEDED")
    sm_arn = event["state_machine_arn"]
    exec_name = event["execution_name"]
    started_at = event.get("started_at")
    if isinstance(started_at, str):
        started_iso = started_at
    elif started_at is not None:
        started_iso = str(started_at)
    else:
        started_iso = None

    exec_arn = factory_execution_arn(sm_arn, exec_name)
    completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    record = build_audit_record(
        status=status,
        workload=state["workload"],
        bucket=state["bucket"],
        provision_id=state["provision_id"],
        run_e2e=bool(state.get("run_e2e", True)),
        factory_execution_arn=exec_arn,
        factory_state_machine_arn=sm_arn,
        started_at=started_iso,
        completed_at=completed_at,
        session_id=state.get("session_id"),
        requested_by=state.get("requested_by"),
        codebuild=state.get("codebuild"),
        pipeline_e2e=state.get("pipeline_e2e"),
        error=state.get("error"),
    )
    uri = write_provision_audit(record)
    return {
        "status": status,
        "provision_id": state["provision_id"],
        "audit_s3_uri": uri,
        "factory_execution_arn": exec_arn,
    }
