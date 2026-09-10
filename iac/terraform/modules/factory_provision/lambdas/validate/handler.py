"""Factory provision SFN step — validate workload + bucket (allowlist gate)."""

from __future__ import annotations

import os
import sys
from typing import Any

# Bundled at deploy time: shared/deploy/factory_provision.py
sys.path.insert(0, os.path.dirname(__file__))

from shared.deploy.factory_provision import validate_request  # noqa: E402


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    payload = {
        "workload": event["workload"],
        "bucket": event["bucket"],
        "approve": True,
        "run_e2e": bool(event.get("run_e2e", True)),
    }
    errors = validate_request(payload)
    if errors:
        raise ValueError("; ".join(errors))
    return event
