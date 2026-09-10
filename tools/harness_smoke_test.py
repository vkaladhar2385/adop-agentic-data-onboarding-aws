#!/usr/bin/env python3
"""Harness smoke prompts for M2 dual-route verification (optional live AWS).

Unit mode (default): validates prompt pack + harness config load.
Live mode (--live): invokes Harness for each prompt (requires AWS profile + READY harness).

Usage:
  python tools/harness_smoke_test.py
  python tools/harness_smoke_test.py --live --profile aws-agent
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.deploy.agentcore_harness import invoke_harness, load_harness_config  # noqa: E402

SMOKE_PROMPTS = [
    {
        "id": "discovery_glue",
        "prompt": "Use Gateway tools to list Glue databases in this account. Reply in 3 bullets max.",
        "expect_substrings": ["database"],
        "requires_tools": True,
    },
    {
        "id": "deploy_assist",
        "prompt": (
            "A client wants a catalog-only Step Functions pipeline for weekly CSV ingest. "
            "What Phase 1 discovery questions must I ask before generating specs? Bullet list only."
        ),
        "expect_substrings": ["PII", "quality", "schedule"],
        "requires_tools": False,
    },
]


def _check_response(text: str, expect: list[str]) -> list[str]:
    lower = text.lower()
    missing = [s for s in expect if s.lower() not in lower]
    return missing


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Harness smoke tests (M2)")
    ap.add_argument("--live", action="store_true", help="Invoke live Harness (AWS spend)")
    ap.add_argument("--profile", default="aws-agent")
    ap.add_argument("--region", default="us-east-1")
    args = ap.parse_args(argv)

    cfg = load_harness_config()
    print(f"Harness config: {cfg.get('name')} model={cfg.get('model', {}).get('model_id')}")
    print(f"Smoke prompts: {len(SMOKE_PROMPTS)}")

    if not args.live:
        print("\nDry run OK (config + prompts). Re-run with --live to invoke Harness.")
        return 0

    failures = 0
    for item in SMOKE_PROMPTS:
        print(f"\n--- {item['id']} ---", flush=True)
        try:
            text = invoke_harness(
                item["prompt"],
                profile=args.profile,
                region=args.region,
            )
        except Exception as exc:
            msg = str(exc)
            print(f"FAIL {item['id']}: {msg}", flush=True)
            if item.get("requires_tools") and "ToolUse" in msg:
                print(
                    "  hint: Gateway tool-use needs Claude (us.anthropic.claude-sonnet-4-6) in harness.yaml",
                    flush=True,
                )
            failures += 1
            continue
        print(text[:500] + ("..." if len(text) > 500 else ""), flush=True)
        missing = _check_response(text, item["expect_substrings"])
        if missing:
            print(f"WARN {item['id']}: response missing hints: {missing}", flush=True)
            failures += 1
        else:
            print(f"PASS {item['id']}", flush=True)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
