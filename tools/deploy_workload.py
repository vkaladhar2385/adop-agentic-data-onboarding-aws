"""Deploy wrapper for Track A Agent Factory (Phase 5 / M3).

Default: validate + codegen drift + pytest + sync + terraform plan.
Apply only with --approve-apply after the user approves in chat.

    python tools/deploy_workload.py --workload advisory_transactions --bucket my-lake --dry-run
    python tools/deploy_workload.py --workload advisory_transactions --bucket my-lake
    python tools/deploy_workload.py --workload advisory_transactions --bucket my-lake --approve-apply
    python tools/deploy_workload.py --workload product_inventory --bucket my-lake --auto-provision
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
TERRAFORM_DIR = REPO_ROOT / "iac" / "terraform"

sys.path.insert(0, str(REPO_ROOT))
from shared.deploy.sfn_e2e import start_and_wait  # noqa: E402
from shared.deploy.sync_landing import sync_landing_data  # noqa: E402
from shared.deploy.workload_tf import ensure_terraform_module, terraform_module_declared  # noqa: E402
from shared.utils.agent_trace import append_trace  # noqa: E402
from shared.utils.orchestrator import resolve_orchestration_artifacts, resolve_orchestrator  # noqa: E402


def _terraform_env(aws_profile: str | None) -> dict[str, str]:
    """Terraform needs credential_process profile; boto3 uses aws login profile."""
    env = os.environ.copy()
    env["AWS_SDK_LOAD_CONFIG"] = "1"
    # CodeBuild / Lambda use the instance role — no profile override.
    if os.getenv("CODEBUILD_BUILD_ID") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        return env
    if aws_profile == "aws-agent":
        env["AWS_PROFILE"] = "aws-agent-terraform"
    elif aws_profile:
        env["AWS_PROFILE"] = aws_profile
    return env


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd or REPO_ROOT, check=True, env=env or os.environ)


def load_compute(workload_dir: Path) -> dict:
    path = workload_dir / "config" / "compute.yaml"
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def load_schedule(workload_dir: Path) -> dict:
    path = workload_dir / "config" / "schedule.yaml"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def workload_orchestrator(workload_dir: Path) -> str:
    return resolve_orchestrator(load_schedule(workload_dir))


def orchestration_artifacts(workload_dir: Path) -> frozenset[str]:
    return resolve_orchestration_artifacts(load_schedule(workload_dir))


def catalog_owner_mcp(workload_dir: Path) -> bool:
    compute = load_compute(workload_dir)
    catalog = compute.get("catalog") or {}
    infra_catalog = (compute.get("infrastructure") or {}).get("catalog") or {}
    return catalog.get("owner") == "mcp" or infra_catalog.get("owner") == "mcp"


def mcp_infrastructure_enabled(workload_dir: Path) -> bool:
    """True when any infrastructure slice is MCP-owned (run mcp_deploy_infrastructure before TF)."""
    compute = load_compute(workload_dir)
    infra = compute.get("infrastructure") or {}
    if not infra:
        return catalog_owner_mcp(workload_dir)
    for key in ("catalog", "kms", "iam", "lakeformation"):
        section = infra.get(key) or {}
        if section.get("owner") == "mcp":
            return True
    return catalog_owner_mcp(workload_dir)


def apply_block_reason(workload: str, approve_apply: bool, workload_dir: Path | None = None) -> str | None:
    """Return an error string if apply must be refused; None if plan-only or apply is allowed."""
    if not approve_apply:
        return None
    wl_dir = workload_dir or (REPO_ROOT / "workloads" / workload)
    compute = load_compute(wl_dir)
    sync = (compute.get("terraform_sync") or {}).get("status", "enforced")
    if sync == "pending":
        return (
            f"refusing apply: config/compute.yaml terraform_sync.status=pending "
            f"(run tools/ensure_terraform_module.py --workload {workload} or pass --ensure-tf-module)"
        )
    if not terraform_module_declared(workload):
        return (
            f'refusing apply: no Terraform module for "{workload}" '
            f"(run tools/ensure_terraform_module.py --workload {workload})"
        )
    return None


def preflight(workload: str) -> list[str]:
    errors: list[str] = []
    workload_dir = REPO_ROOT / "workloads" / workload
    if not workload_dir.is_dir():
        return [f"workload not found: {workload_dir}"]
    if not (workload_dir / "config" / "compute.yaml").is_file():
        errors.append(f"missing {workload_dir / 'config' / 'compute.yaml'}")
    if not (workload_dir / "config" / "source.yaml").is_file():
        errors.append(f"missing {workload_dir / 'config' / 'source.yaml'}")
    if not (workload_dir / ".discovery_complete").is_file():
        errors.append(f"missing {workload_dir / '.discovery_complete'} (run /onboard-workflow Phase 1)")
    return errors


def _has_codegen_specs(workload: str) -> bool:
    spec_dir = REPO_ROOT / "workloads" / workload / "config" / "codegen"
    return spec_dir.is_dir() and any(spec_dir.glob("*.spec.yaml"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate, sync, and plan/apply a workload deploy.")
    parser.add_argument("--workload", required=True)
    parser.add_argument("--bucket", default=None, help="Data lake bucket (required unless --dry-run)")
    parser.add_argument(
        "--approve-apply",
        action="store_true",
        help="Run terraform apply after plan (requires explicit user approval in chat)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preflight + validators + pytest + codegen drift only (no S3, no Terraform)",
    )
    parser.add_argument(
        "--mcp-catalog",
        action="store_true",
        help="Run MCP catalog ensure-database only (after validators; no Terraform)",
    )
    parser.add_argument(
        "--mcp-infrastructure",
        action="store_true",
        help="Run full MCP infrastructure deploy (catalog, KMS, IAM, LF) — no Terraform",
    )
    parser.add_argument(
        "--tier-b-check",
        action="store_true",
        help="Run local Tier B acceptance (Cedar, DAG, ontology) after validators",
    )
    parser.add_argument(
        "--mwaa-dags-uri",
        default=None,
        help="When orchestrator=mwaa, sync rendered dags/ to this S3 prefix after package_and_sync",
    )
    parser.add_argument(
        "--ensure-tf-module",
        action="store_true",
        help="Generate iac/terraform/workloads_{name}.tf and flip terraform_sync to enforced",
    )
    parser.add_argument(
        "--sync-landing",
        action="store_true",
        help="Generate and upload demo landing CSV after apply (or with --run-e2e)",
    )
    parser.add_argument(
        "--run-e2e",
        action="store_true",
        help="After apply: sync landing (unless --skip-landing-sync), start SFN, poll until terminal",
    )
    parser.add_argument(
        "--skip-landing-sync",
        action="store_true",
        help="With --run-e2e: do not upload landing data first",
    )
    parser.add_argument(
        "--auto-provision",
        action="store_true",
        help="Shorthand: --ensure-tf-module --approve-apply --sync-landing --run-e2e",
    )
    parser.add_argument("--aws-profile", default=None, help="AWS profile for landing sync / SFN E2E")
    args = parser.parse_args(argv)

    if args.auto_provision:
        args.ensure_tf_module = True
        args.approve_apply = True
        args.sync_landing = True
        args.run_e2e = True

    if args.run_e2e and not args.approve_apply:
        print("error: --run-e2e requires --approve-apply (or --auto-provision)", file=sys.stderr)
        return 1
    if args.run_e2e and not args.skip_landing_sync:
        args.sync_landing = True

    workload_dir = REPO_ROOT / "workloads" / args.workload
    errors = preflight(args.workload)
    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        append_trace(args.workload, "deploy", "blocked", agent="deploy", reason="; ".join(errors))
        return 1

    if not args.dry_run and not args.bucket:
        print("error: --bucket is required unless --dry-run", file=sys.stderr)
        return 1

    if args.ensure_tf_module and not args.dry_run:
        print("\n>>> Ensuring Terraform module (workloads_{}.tf)\n".format(args.workload), flush=True)
        ensure_terraform_module(args.workload)

    apply_err = apply_block_reason(args.workload, args.approve_apply, workload_dir)
    if apply_err:
        print(f"error: {apply_err}", file=sys.stderr)
        append_trace(args.workload, "deploy", "blocked", agent="deploy", reason=apply_err)
        return 1

    try:
        _run([sys.executable, "tools/validate_configs.py"])
        _run([sys.executable, "tools/validate_cedar_policies.py"])
        _run([sys.executable, "tools/validate_compute.py", "--workload", args.workload])
        if _has_codegen_specs(args.workload):
            _run(
                [
                    sys.executable,
                    "tools/render_workload.py",
                    "--workload",
                    args.workload,
                    "--all",
                    "--check-drift",
                ]
            )
        _run([sys.executable, "-m", "pytest", f"workloads/{args.workload}/tests/", "-v"])

        if args.tier_b_check or args.dry_run:
            _run(
                [
                    sys.executable,
                    "tools/tier_b_acceptance.py",
                    "--workload",
                    args.workload,
                ]
            )

        if args.dry_run:
            orch = workload_orchestrator(workload_dir)
            print(f"\nOrchestrator: {orch} | artifacts: {sorted(orchestration_artifacts(workload_dir))}")
            print("\nDry-run complete. No S3 sync or Terraform.\n", flush=True)
            append_trace(args.workload, "deploy", "ok", agent="deploy", mode="dry-run")
            return 0

        if args.mcp_catalog:
            if not catalog_owner_mcp(workload_dir):
                print("error: catalog.owner is not mcp in compute.yaml", file=sys.stderr)
                return 1
            _run(
                [
                    sys.executable,
                    "tools/mcp_deploy_catalog.py",
                    "--workload",
                    args.workload,
                    "--ensure-database",
                ]
            )
            append_trace(args.workload, "deploy", "ok", agent="deploy", mode="mcp-catalog")
            return 0

        if args.mcp_infrastructure:
            if not mcp_infrastructure_enabled(workload_dir):
                print("error: no MCP infrastructure owners in compute.yaml", file=sys.stderr)
                return 1
            _run(
                [
                    sys.executable,
                    "tools/mcp_deploy_infrastructure.py",
                    "--workload",
                    args.workload,
                    "--bucket",
                    args.bucket,
                    "--apply",
                ]
            )
            append_trace(args.workload, "deploy", "ok", agent="deploy", mode="mcp-infrastructure")
            return 0

        if mcp_infrastructure_enabled(workload_dir):
            print("\n>>> MCP-first — provision catalog/KMS/IAM/LF before terraform apply\n", flush=True)
            _run(
                [
                    sys.executable,
                    "tools/mcp_deploy_infrastructure.py",
                    "--workload",
                    args.workload,
                    "--bucket",
                    args.bucket,
                    "--apply",
                ]
            )

        sync_cmd = [
            sys.executable,
            "tools/package_and_sync.py",
            "--bucket",
            args.bucket,
            "--workload",
            args.workload,
        ]
        if args.aws_profile:
            sync_cmd.extend(["--profile", args.aws_profile])
        _run(sync_cmd)

        orch_artifacts = orchestration_artifacts(workload_dir)
        if "dag" in orch_artifacts:
            dag_files = list((workload_dir / "dags").glob("*_pipeline.py"))
            if not dag_files:
                print("error: orchestrator emits DAG but dags/*_pipeline.py missing", file=sys.stderr)
                return 1
            if args.mwaa_dags_uri:
                _run(
                    [
                        sys.executable,
                        "tools/sync_mwaa_dags.py",
                        "--workload",
                        args.workload,
                        "--s3-uri",
                        args.mwaa_dags_uri,
                    ]
                )
            else:
                print(
                    "\n>>> MWAA: pass --mwaa-dags-uri s3://<mwaa-bucket>/dags/ to sync DAG after deploy\n",
                    flush=True,
                )

        tf_target = f"module.{args.workload}"
        if "state_machine" in orch_artifacts and terraform_module_declared(args.workload):
            _run(
                ["terraform", "plan", f"-target={tf_target}"],
                cwd=TERRAFORM_DIR,
                env=_terraform_env(args.aws_profile),
            )
        elif "state_machine" in orch_artifacts:
            print(
                f'\n>>> SFN orchestrator but no module "{args.workload}" in main.tf — terraform plan skipped\n',
                flush=True,
            )
        else:
            print("\n>>> MWAA-only orchestrator — Step Functions terraform plan skipped\n", flush=True)

        if args.approve_apply and "state_machine" in orch_artifacts and terraform_module_declared(
            args.workload
        ):
            print("\n>>> Running terraform apply (--approve-apply set)\n", flush=True)
            _run(
                ["terraform", "apply", "-auto-approve", f"-target={tf_target}"],
                cwd=TERRAFORM_DIR,
                env=_terraform_env(args.aws_profile),
            )
            append_trace(args.workload, "deploy", "ok", agent="deploy", mode="apply")

            if args.sync_landing and not args.run_e2e:
                print("\n>>> Syncing landing demo data\n", flush=True)
                sync_landing_data(args.workload, args.bucket, profile=args.aws_profile)

            if args.run_e2e:
                if not args.skip_landing_sync:
                    print("\n>>> Syncing landing demo data (E2E)\n", flush=True)
                    sync_landing_data(args.workload, args.bucket, profile=args.aws_profile)
                print("\n>>> Starting Step Functions E2E\n", flush=True)
                try:
                    result = start_and_wait(
                        args.workload,
                        args.bucket,
                        profile=args.aws_profile,
                    )
                except (LookupError, TimeoutError, RuntimeError) as exc:
                    append_trace(args.workload, "e2e", "failed", agent="deploy", reason=str(exc))
                    print(f"error: {exc}", file=sys.stderr)
                    return 1
                status = result["status"]
                append_trace(
                    args.workload,
                    "e2e",
                    "ok" if status == "SUCCEEDED" else "failed",
                    agent="deploy",
                    execution_arn=result["execution_arn"],
                    execution_status=status,
                )
                print(f"\nE2E {status}: {result['execution_arn']}\n", flush=True)
                if status != "SUCCEEDED":
                    return 1
        elif "state_machine" in orch_artifacts and terraform_module_declared(args.workload):
            print(
                "\nStopped after terraform plan. Re-run with --approve-apply after user approves deploy.\n",
                flush=True,
            )
            append_trace(args.workload, "deploy", "ok", agent="deploy", mode="plan")
        else:
            append_trace(args.workload, "deploy", "ok", agent="deploy", mode="mwaa-or-mcp-only")
    except subprocess.CalledProcessError as exc:
        append_trace(args.workload, "deploy", "failed", agent="deploy", returncode=exc.returncode)
        return exc.returncode or 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
