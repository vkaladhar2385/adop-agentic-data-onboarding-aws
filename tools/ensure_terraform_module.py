"""Generate iac/terraform/workloads_{name}.tf from workload config."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.deploy.workload_tf import ensure_terraform_module, render_module_hcl  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auto-generate Terraform workload module file.")
    parser.add_argument("--workload", required=True)
    parser.add_argument("--dry-run", action="store_true", help="Print HCL preview only")
    parser.add_argument(
        "--no-update-compute",
        action="store_true",
        help="Do not flip terraform_sync.status to enforced in compute.yaml",
    )
    args = parser.parse_args(argv)

    try:
        if args.dry_run:
            print(render_module_hcl(args.workload))
            return 0
        ensure_terraform_module(
            args.workload,
            update_compute_sync=not args.no_update_compute,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
