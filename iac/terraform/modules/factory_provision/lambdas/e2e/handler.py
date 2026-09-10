"""Factory provision SFN step — start workload pipeline SFN and poll to terminal."""

from __future__ import annotations

import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))

from shared.deploy.sfn_e2e import start_and_wait  # noqa: E402


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    workload = event["workload"]
    bucket = event["bucket"]
    provision_id = event.get("provision_id", "factory")
    exec_name = f"{workload}-{provision_id}"[:80]
    result = start_and_wait(workload, bucket, execution_name=exec_name)
    return {
        "status": result["status"],
        "execution_arn": result["execution_arn"],
        "state_machine_arn": result["state_machine_arn"],
        "workload": workload,
        "bucket": bucket,
    }
