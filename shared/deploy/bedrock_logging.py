"""Disable Bedrock model invocation logging (sandbox teardown)."""

from __future__ import annotations

from typing import Any


def disable_invocation_logging(
    session: Any,
    *,
    dry_run: bool = False,
) -> dict[str, str]:
    """Turn off account-level Bedrock model invocation logging."""
    client = session.client("bedrock")
    try:
        current = client.get_model_invocation_logging_configuration()
    except client.exceptions.ValidationException:
        return {"status": "skipped", "reason": "logging not configured"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}

    if not current.get("loggingConfig"):
        return {"status": "skipped", "reason": "already disabled"}

    if dry_run:
        print("[dry-run] disable Bedrock model invocation logging")
        return {"status": "planned"}

    client.put_model_invocation_logging_configuration(loggingConfig={})
    print("Disabled Bedrock model invocation logging")
    return {"status": "disabled"}
