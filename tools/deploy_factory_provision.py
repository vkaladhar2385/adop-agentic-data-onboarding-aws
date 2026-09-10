#!/usr/bin/env python3
"""Apply Terraform factory_provision module only (Option B Step 3).

Usage:
  python tools/package_factory_artifact.py --bucket my-lake
  python tools/deploy_factory_provision.py --profile aws-agent-terraform
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TF_DIR = REPO_ROOT / "iac" / "terraform"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Terraform apply module.factory_provision")
    ap.add_argument("--profile", default="aws-agent-terraform")
    ap.add_argument("--init-backend", action="store_true", help="Run terraform init with backend.hcl")
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args(argv)

    env = os.environ.copy()
    env["AWS_SDK_LOAD_CONFIG"] = "1"
    env["AWS_PROFILE"] = args.profile

    init_cmd = ["terraform", "-chdir=iac/terraform", "init", "-input=false"]
    if args.init_backend:
        backend_hcl = TF_DIR / "backend.hcl"
        if not backend_hcl.is_file():
            print("error: create iac/terraform/backend.hcl from backend.hcl.example", file=sys.stderr)
            return 1
        init_cmd.extend(["-backend-config=backend.hcl"])
    else:
        init_cmd.append("-backend=false")

    subprocess.run(init_cmd, cwd=REPO_ROOT, check=True, env=env)

    target = ["-target=module.factory_provision"]
    if args.plan_only:
        subprocess.run(
            ["terraform", "-chdir=iac/terraform", "plan", *target],
            cwd=REPO_ROOT,
            check=True,
            env=env,
        )
        return 0

    subprocess.run(
        ["terraform", "-chdir=iac/terraform", "apply", "-auto-approve", *target],
        cwd=REPO_ROOT,
        check=True,
        env=env,
    )
    print("\nNext:")
    print("  python tools/start_provision_api.py --workload supplier_lead_times --bucket <lake> --approve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
