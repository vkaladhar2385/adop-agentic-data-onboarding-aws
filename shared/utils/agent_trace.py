"""Append one JSON line per factory phase to workloads/{name}/logs/trace_events.jsonl."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def append_trace(workload: str, phase: str, status: str, **extra: object) -> Path:
    workload_dir = REPO_ROOT / "workloads" / workload
    log_dir = workload_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "trace_events.jsonl"
    record = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "phase": phase,
        "status": status,
        "workload": workload,
        **extra,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")
    return path
