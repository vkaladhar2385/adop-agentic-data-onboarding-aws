"""Structured JSON logger for pipeline scripts (Track A / official ADOP).

Emits one JSON object per line to stderr for CloudWatch Logs Insights.

    from shared.utils.structured_logger import StructuredLogger

    log = StructuredLogger(agent="quality", workload="product_inventory", run_id="local")
    log.info("quality_gate", zone="silver", passed=True, score=0.99)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any


class StructuredLogger:
    def __init__(self, agent: str, workload: str, run_id: str = "local"):
        self.context = {"agent": agent, "workload": workload, "run_id": run_id}

    def log(self, level: str, message: str, **extra: Any) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            **self.context,
            "message": message,
            **extra,
        }
        print(json.dumps(entry, default=str), file=sys.stderr)

    def info(self, message: str, **extra: Any) -> None:
        self.log("INFO", message, **extra)

    def warn(self, message: str, **extra: Any) -> None:
        self.log("WARN", message, **extra)

    def error(self, message: str, **extra: Any) -> None:
        self.log("ERROR", message, **extra)

    def debug(self, message: str, **extra: Any) -> None:
        self.log("DEBUG", message, **extra)

    def phase_boundary(self, phase: str, status: str) -> None:
        self.log("PHASE", f"{phase}: {status}", phase=phase, status=status)
