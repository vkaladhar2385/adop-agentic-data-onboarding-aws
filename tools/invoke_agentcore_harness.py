#!/usr/bin/env python3
"""Invoke the ADOP AgentCore Harness (smoke test)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.deploy.agentcore_harness import invoke_harness  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Invoke ADOP AgentCore Harness")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--profile", default="aws-agent")
    ap.add_argument("--region", default=None)
    ap.add_argument("--session-id", default=None)
    args = ap.parse_args()

    try:
        text = invoke_harness(
            args.prompt,
            profile=args.profile,
            region=args.region,
            session_id=args.session_id,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # Windows consoles may not support emoji/Unicode from model output.
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
