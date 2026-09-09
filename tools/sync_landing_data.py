"""Upload synthetic landing data for a workload (generator or sample CSV)."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.deploy.sync_landing import sync_landing_data  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate and upload landing demo data.")
    parser.add_argument("--workload", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--date", default=None, help="Ingestion date YYYY-MM-DD (default: today)")
    parser.add_argument("--profile", default=None, help="AWS profile name")
    args = parser.parse_args(argv)

    ingestion = date.fromisoformat(args.date) if args.date else None
    try:
        uri = sync_landing_data(
            args.workload,
            args.bucket,
            ingestion_date=ingestion,
            profile=args.profile,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(uri)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
