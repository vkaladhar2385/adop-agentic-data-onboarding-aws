#!/usr/bin/env python3
"""Summarize agent trace logs and suggest prompt improvements (Tier B9)."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_events(path: Path) -> list[dict]:
    events: list[dict] = []
    if not path.is_file():
        return events
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def analyze_workload(workload: str) -> dict:
    trace_path = REPO_ROOT / "workloads" / workload / "logs" / "trace_events.jsonl"
    events = _load_events(trace_path)
    agents = Counter(e.get("agent_name", "unknown") for e in events)
    statuses = Counter(e.get("status", e.get("agent_status", "unknown")) for e in events)
    failures = [e for e in events if str(e.get("status", "")).lower() in ("failed", "error")]
    suggestions: list[str] = []
    if failures:
        suggestions.append(
            f"Review failures in {trace_path.name} ({len(failures)} events) — "
            "add explicit examples to the matching sub-agent prompt."
        )
    if agents.get("unknown", 0) > 0:
        suggestions.append("Ensure all sub-agents emit agent_name in trace events.")
    if not events:
        suggestions.append("No trace events — wire StructuredLogger / agent_trace in build phase.")
    return {
        "workload": workload,
        "event_count": len(events),
        "agents": dict(agents),
        "statuses": dict(statuses),
        "failure_count": len(failures),
        "suggestions": suggestions,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workload", default=None, help="Single workload; default all with logs/")
    args = ap.parse_args()

    workloads = [args.workload] if args.workload else [
        p.parents[1].name for p in REPO_ROOT.glob("workloads/*/logs")
    ]
    reports = [analyze_workload(w) for w in sorted(set(workloads))]
    print(json.dumps(reports, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
