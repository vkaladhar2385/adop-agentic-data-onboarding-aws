"""Start Step Functions and poll until SUCCEEDED (post-deploy smoke test)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.deploy.sfn_e2e import start_and_wait  # noqa: E402
from shared.deploy.sync_landing import sync_landing_data  # noqa: E402
from shared.utils.agent_trace import append_trace  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run SFN E2E: optional landing sync + start + poll.")
    parser.add_argument("--workload", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--region", default=None)
    parser.add_argument("--skip-landing-sync", action="store_true")
    parser.add_argument("--execution-name", default=None)
    args = parser.parse_args(argv)

    try:
        if not args.skip_landing_sync:
            sync_landing_data(args.workload, args.bucket, profile=args.profile)
        result = start_and_wait(
            args.workload,
            args.bucket,
            region=args.region,
            profile=args.profile,
            execution_name=args.execution_name,
        )
    except (LookupError, TimeoutError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        append_trace(args.workload, "e2e", "failed", agent="deploy", reason=str(exc))
        return 1

    status = result["status"]
    append_trace(
        args.workload,
        "e2e",
        "ok" if status == "SUCCEEDED" else "failed",
        agent="deploy",
        execution_arn=result["execution_arn"],
        status=status,
    )
    print(f"E2E {status}: {result['execution_arn']}")
    return 0 if status == "SUCCEEDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
