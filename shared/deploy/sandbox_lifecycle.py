"""Create and destroy ADOP sandbox AWS assets from one orchestrated entry point."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from shared.deploy.agentcore_gateway import gateway_target_names, load_gateway_manifest
from shared.deploy.agentcore_harness import HARNESS_META, load_harness_config
from shared.deploy.bedrock_logging import disable_invocation_logging
from shared.deploy.infrastructure_config import load_infrastructure_owners
from shared.deploy.mcp_lf import revoke_lf_grants
from shared.deploy.sandbox_tags import (
    list_tagged_lambda_names,
    list_tagged_resource_arns,
    resource_prefix,
    role_name_matches_prefix,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TERRAFORM_DIR = REPO_ROOT / "iac" / "terraform"
GATEWAY_META = REPO_ROOT / "build" / "mcp" / "gateway.json"


@dataclass
class LifecycleReport:
    deleted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)


def terraform_env(aws_profile: str | None) -> dict[str, str]:
    import os

    env = os.environ.copy()
    env["AWS_SDK_LOAD_CONFIG"] = "1"
    if aws_profile == "aws-agent":
        env["AWS_PROFILE"] = "aws-agent-terraform"
    elif aws_profile:
        env["AWS_PROFILE"] = aws_profile
    return env


def _log(msg: str, *, dry_run: bool) -> None:
    prefix = "[dry-run] " if dry_run else ""
    print(f"{prefix}{msg}", flush=True)


def _session(profile: str | None, region: str):
    import boto3

    return boto3.Session(profile_name=profile, region_name=region)


def _load_tfvars() -> dict[str, Any]:
    path = TERRAFORM_DIR / "terraform.tfvars"
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    out: dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw = line.split("=", 1)
        key = key.strip()
        raw = raw.strip().strip('"').strip("'")
        out[key] = raw
    return out


def resolve_bucket(*, profile: str | None, region: str, bucket: str | None) -> str:
    if bucket:
        return bucket
    tfvars = _load_tfvars()
    if tfvars.get("data_lake_bucket"):
        return str(tfvars["data_lake_bucket"])
    import boto3

    account_id = boto3.Session(profile_name=profile, region_name=region).client("sts").get_caller_identity()[
        "Account"
    ]
    return f"adop-datalake-{account_id}-{region}"


def discover_mcp_workloads() -> list[str]:
    workloads: list[str] = []
    for compute_path in sorted((REPO_ROOT / "workloads").glob("*/config/compute.yaml")):
        workload = compute_path.parent.parent.name
        owners = load_infrastructure_owners(workload)
        if any(
            owners[k] == "mcp"
            for k in ("catalog_owner", "kms_owner", "iam_owner", "lakeformation_owner")
        ):
            workloads.append(workload)
    return workloads


def _delete_iam_role(iam: Any, role_name: str, *, dry_run: bool) -> bool:
    try:
        iam.get_role(RoleName=role_name)
    except iam.exceptions.NoSuchEntityException:
        return False
    _log(f"delete IAM role {role_name}", dry_run=dry_run)
    if dry_run:
        return True
    for policy in iam.list_attached_role_policies(RoleName=role_name).get("AttachedPolicies", []):
        iam.detach_role_policy(RoleName=role_name, PolicyArn=policy["PolicyArn"])
    for policy_name in iam.list_role_policies(RoleName=role_name).get("PolicyNames", []):
        iam.delete_role_policy(RoleName=role_name, PolicyName=policy_name)
    iam.delete_role(RoleName=role_name)
    return True


def destroy_harness(
    session: Any,
    *,
    project: str,
    dry_run: bool,
    report: LifecycleReport,
) -> None:
    control = session.client("bedrock-agentcore-control")
    harness_name = load_harness_config().get("name") or "adop_onboarding_agent"
    harness_id: str | None = None

    if HARNESS_META.is_file():
        try:
            harness_id = json.loads(HARNESS_META.read_text(encoding="utf-8")).get("harnessId")
        except json.JSONDecodeError:
            pass

    if not harness_id:
        for page in control.get_paginator("list_harnesses").paginate():
            for item in page.get("harnesses", []):
                if item.get("harnessName") == harness_name:
                    harness_id = item["harnessId"]
                    break
            if harness_id:
                break

    if not harness_id:
        report.skipped.append(f"harness:{harness_name}")
        return

    _log(f"delete harness {harness_name} ({harness_id})", dry_run=dry_run)
    if dry_run:
        report.deleted.append(f"harness:{harness_id}")
        return

    control.delete_harness(harnessId=harness_id)
    for _ in range(60):
        try:
            status = control.get_harness(harnessId=harness_id)["harness"].get("status")
            if status == "DELETED":
                break
        except Exception:
            break
        time.sleep(5)
    report.deleted.append(f"harness:{harness_id}")


def destroy_gateway(
    session: Any,
    *,
    project: str,
    dry_run: bool,
    report: LifecycleReport,
) -> None:
    control = session.client("bedrock-agentcore-control")
    manifest = load_gateway_manifest()
    gateway_name = f"{project}-{(manifest.get('gateway') or {}).get('name_suffix', 'mcp-gateway')}"

    gateway_id: str | None = None
    if GATEWAY_META.is_file():
        try:
            gateway_id = json.loads(GATEWAY_META.read_text(encoding="utf-8")).get("gatewayId")
        except json.JSONDecodeError:
            pass

    if not gateway_id:
        for item in control.list_gateways().get("items", []):
            if item.get("name") == gateway_name:
                gateway_id = item["gatewayId"]
                break

    if not gateway_id:
        report.skipped.append(f"gateway:{gateway_name}")
        return

    targets = control.list_gateway_targets(gatewayIdentifier=gateway_id).get("items", [])
    for target in targets:
        target_id = target.get("targetId")
        name = target.get("name", target_id)
        _log(f"delete gateway target {name}", dry_run=dry_run)
        if not dry_run and target_id:
            control.delete_gateway_target(gatewayIdentifier=gateway_id, targetId=target_id)
        report.deleted.append(f"gateway-target:{name}")

    _log(f"delete gateway {gateway_name} ({gateway_id})", dry_run=dry_run)
    if not dry_run:
        control.delete_gateway(gatewayIdentifier=gateway_id)
    report.deleted.append(f"gateway:{gateway_id}")


def _delete_lambda(lam: Any, fn_name: str, *, dry_run: bool, report: LifecycleReport) -> None:
    try:
        lam.get_function(FunctionName=fn_name)
    except lam.exceptions.ResourceNotFoundException:
        report.skipped.append(f"lambda:{fn_name}")
        return
    _log(f"delete lambda {fn_name}", dry_run=dry_run)
    if not dry_run:
        lam.delete_function(FunctionName=fn_name)
    report.deleted.append(f"lambda:{fn_name}")


def destroy_mcp_lambdas(
    session: Any,
    *,
    project: str,
    dry_run: bool,
    report: LifecycleReport,
) -> None:
    """Delete MCP Lambdas by tag scan first, then manifest name fallback."""
    lam = session.client("lambda")
    names: set[str] = set(list_tagged_lambda_names(session))
    for name in gateway_target_names():
        names.add(f"{project}-mcp-{name.replace('_', '-')}")

    prefix = resource_prefix()
    for page in lam.get_paginator("list_functions").paginate():
        for fn in page.get("Functions", []):
            fn_name = fn["FunctionName"]
            # Factory Lambdas are removed by Terraform (module.factory_provision).
            if fn_name.startswith(f"{prefix}-factory-"):
                continue
            if fn_name.startswith(f"{prefix}-mcp-") or fn_name.startswith(f"{prefix}-"):
                names.add(fn_name)

    for fn_name in sorted(names):
        _delete_lambda(lam, fn_name, dry_run=dry_run, report=report)


def destroy_agentcore_iam_roles(
    session: Any,
    *,
    project: str,
    dry_run: bool,
    report: LifecycleReport,
) -> None:
    iam = session.client("iam")
    role_names = [f"{project}-agentcore-gateway-role", f"{project}-agentcore-harness-role"]
    for name in gateway_target_names():
        role_names.append(f"{project}-mcp-{name.replace('_', '-')}-role")

    for role_name in role_names:
        if _delete_iam_role(iam, role_name, dry_run=dry_run):
            report.deleted.append(f"iam-role:{role_name}")
        else:
            report.skipped.append(f"iam-role:{role_name}")


def destroy_lf_grants(
    session: Any,
    *,
    workloads: list[str],
    bucket: str | None,
    dry_run: bool,
    report: LifecycleReport,
) -> None:
    """Revoke Lake Formation grants before deleting MCP IAM roles."""
    if not bucket:
        report.skipped.append("lf-grants:no-bucket")
        return
    iam = session.client("iam")

    for workload in workloads:
        owners = load_infrastructure_owners(workload)
        if owners["lakeformation_owner"] != "mcp" or owners["iam_owner"] != "mcp":
            continue
        name_prefix = owners["name_prefix"]
        try:
            glue_arn = iam.get_role(RoleName=f"{name_prefix}-glue-role")["Role"]["Arn"]
            lambda_arn = iam.get_role(RoleName=f"{name_prefix}-lambda-role")["Role"]["Arn"]
        except iam.exceptions.NoSuchEntityException:
            report.skipped.append(f"lf-grants:{workload}")
            continue
        _log(f"revoke LF grants for {workload}", dry_run=dry_run)
        revoke_lf_grants(
            database=owners["database"],
            bucket=bucket,
            glue_role_arn=glue_arn,
            lambda_role_arn=lambda_arn,
            dry_run=dry_run,
        )
        report.deleted.append(f"lf-grants:{workload}")


def destroy_mcp_infrastructure(
    session: Any,
    *,
    workloads: list[str],
    dry_run: bool,
    report: LifecycleReport,
) -> None:
    glue = session.client("glue")
    kms = session.client("kms")
    iam = session.client("iam")

    for workload in workloads:
        owners = load_infrastructure_owners(workload)
        database = owners["database"]
        name_prefix = owners["name_prefix"]

        if owners["catalog_owner"] == "mcp":
            try:
                glue.get_database(Name=database)
            except glue.exceptions.EntityNotFoundException:
                report.skipped.append(f"glue-db:{database}")
            else:
                _log(f"delete glue database {database}", dry_run=dry_run)
                if not dry_run:
                    for table in glue.get_tables(DatabaseName=database).get("TableList", []):
                        glue.delete_table(DatabaseName=database, Name=table["Name"])
                    glue.delete_database(Name=database)
                report.deleted.append(f"glue-db:{database}")

        if owners["kms_owner"] == "mcp":
            for zone in owners["zones"]:
                alias = f"alias/{workload}-{zone}"
                try:
                    meta = kms.describe_key(KeyId=alias)["KeyMetadata"]
                except kms.exceptions.NotFoundException:
                    report.skipped.append(f"kms:{alias}")
                    continue
                key_id = meta["KeyId"]
                _log(f"schedule KMS key deletion {alias}", dry_run=dry_run)
                if not dry_run:
                    try:
                        kms.delete_alias(AliasName=alias)
                    except kms.exceptions.NotFoundException:
                        pass
                    kms.schedule_key_deletion(KeyId=key_id, PendingWindowInDays=7)
                report.pending.append(f"kms:{alias} (7-day deletion window)")
                report.deleted.append(f"kms-scheduled:{alias}")

        if owners["iam_owner"] == "mcp":
            for suffix in ("glue-role", "lambda-role", "sfn-role", "scheduler-role"):
                role_name = f"{name_prefix}-{suffix}"
                if _delete_iam_role(iam, role_name, dry_run=dry_run):
                    report.deleted.append(f"iam-role:{role_name}")
                else:
                    report.skipped.append(f"iam-role:{role_name}")


def _terraform_targets(include_extensions: bool) -> list[str]:
    targets = [
        "module.factory_provision",
        "module.advisory_transactions",
        "module.supplier_lead_times",
        "aws_budgets_budget.pilot",
    ]
    if include_extensions:
        targets = [
            "module.advisory_transactions_redshift",
            "module.advisory_transactions_opensearch",
            "module.advisory_transactions_redis",
            "aws_iam_role_policy.sfn_extension_lambdas",
            *targets,
        ]
    return targets


def destroy_terraform(
    *,
    profile: str | None,
    dry_run: bool,
    include_extensions: bool,
    report: LifecycleReport,
) -> None:
    if not (TERRAFORM_DIR / ".terraform").is_dir() and not dry_run:
        report.warnings.append("terraform: no .terraform directory — run terraform init first or skip")
        return

    env = terraform_env(profile)
    if dry_run:
        _log(
            f"terraform destroy (include_extensions={include_extensions})",
            dry_run=True,
        )
        report.deleted.append("terraform:planned")
        return

    try:
        subprocess.run(
            ["terraform", "destroy", "-auto-approve"],
            cwd=TERRAFORM_DIR,
            env=env,
            check=True,
        )
        report.deleted.append("terraform:all")
        return
    except subprocess.CalledProcessError:
        report.warnings.append("terraform destroy failed — retrying targeted destroy")

    for target in _terraform_targets(include_extensions):
        try:
            subprocess.run(
                ["terraform", "destroy", "-auto-approve", f"-target={target}"],
                cwd=TERRAFORM_DIR,
                env=env,
                check=True,
            )
            report.deleted.append(f"terraform:{target}")
        except subprocess.CalledProcessError as exc:
            report.warnings.append(f"terraform target failed: {target} ({exc.returncode})")


def empty_s3_bucket(session: Any, bucket: str, *, dry_run: bool, report: LifecycleReport) -> None:
    s3 = session.client("s3")
    try:
        s3.head_bucket(Bucket=bucket)
    except Exception:
        report.skipped.append(f"s3:{bucket}")
        return

    _log(f"empty S3 bucket {bucket}", dry_run=dry_run)
    if dry_run:
        report.deleted.append(f"s3-empty:{bucket}")
        return

    paginator = s3.get_paginator("list_object_versions")
    for page in paginator.paginate(Bucket=bucket):
        to_delete: list[dict[str, str]] = []
        for version in page.get("Versions", []):
            to_delete.append({"Key": version["Key"], "VersionId": version["VersionId"]})
        for marker in page.get("DeleteMarkers", []):
            to_delete.append({"Key": marker["Key"], "VersionId": marker["VersionId"]})
        if to_delete:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": to_delete, "Quiet": True})

    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        if keys:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": keys, "Quiet": True})

    _log(f"delete S3 bucket {bucket}", dry_run=dry_run)
    s3.delete_bucket(Bucket=bucket)
    report.deleted.append(f"s3:{bucket}")


def destroy_log_groups(session: Any, *, project: str, dry_run: bool, report: LifecycleReport) -> None:
    logs = session.client("logs")
    prefixes = (
        "/aws/bedrock/",
        "/aws/bedrock-agentcore/",
        "/aws/codebuild/adop-factory",
        "/aws/lambda/adop-",
        f"/aws/lambda/{project}-",
    )
    for page in logs.get_paginator("describe_log_groups").paginate():
        for group in page.get("logGroups", []):
            name = group["logGroupName"]
            if not any(name.startswith(p) for p in prefixes):
                continue
            _log(f"delete log group {name}", dry_run=dry_run)
            if not dry_run:
                logs.delete_log_group(logGroupName=name)
            report.deleted.append(f"log-group:{name}")


def _cleanup_local_metadata() -> None:
    for path in (GATEWAY_META, HARNESS_META):
        if path.is_file():
            path.unlink()


def verify_remaining(session: Any, *, project: str, bucket: str | None) -> list[str]:
    remaining: list[str] = []
    iam = session.client("iam")
    control = session.client("bedrock-agentcore-control")

    tagged = list_tagged_resource_arns(session)
    for arn in tagged:
        remaining.append(f"tagged:{arn}")

    for name in list_tagged_lambda_names(session):
        remaining.append(f"lambda:{name}")

    for role_page in iam.get_paginator("list_roles").paginate():
        for role in role_page.get("Roles", []):
            name = role["RoleName"]
            if role_name_matches_prefix(name) or name.startswith(f"{project}-"):
                remaining.append(f"iam-role:{name}")

    for item in control.list_gateways().get("items", []):
        if item.get("name", "").startswith(project):
            remaining.append(f"gateway:{item['gatewayId']}")

    for page in control.get_paginator("list_harnesses").paginate():
        for harness in page.get("harnesses", []):
            if harness.get("harnessName", "").startswith("adop"):
                remaining.append(f"harness:{harness['harnessId']}")

    if bucket:
        try:
            session.client("s3").head_bucket(Bucket=bucket)
            remaining.append(f"s3:{bucket}")
        except Exception:
            pass

    return remaining


def destroy_sandbox(
    *,
    profile: str | None = "aws-agent",
    region: str = "us-east-1",
    project: str = "adop",
    bucket: str | None = None,
    include_data: bool = False,
    include_extensions: bool = True,
    skip_terraform: bool = False,
    skip_agentcore: bool = False,
    revoke_lf: bool = True,
    disable_bedrock_logging: bool = True,
    dry_run: bool = False,
) -> LifecycleReport:
    """Tear down ADOP sandbox resources in safe dependency order."""
    report = LifecycleReport()
    session = _session(profile, region)
    bucket_name = resolve_bucket(profile=profile, region=region, bucket=bucket)
    mcp_workloads = discover_mcp_workloads()

    if not skip_agentcore:
        destroy_harness(session, project=project, dry_run=dry_run, report=report)
        destroy_gateway(session, project=project, dry_run=dry_run, report=report)
        destroy_mcp_lambdas(session, project=project, dry_run=dry_run, report=report)
        destroy_agentcore_iam_roles(session, project=project, dry_run=dry_run, report=report)

    if not skip_terraform:
        destroy_terraform(
            profile=profile,
            dry_run=dry_run,
            include_extensions=include_extensions,
            report=report,
        )

    if revoke_lf:
        destroy_lf_grants(
            session,
            workloads=mcp_workloads,
            bucket=bucket_name,
            dry_run=dry_run,
            report=report,
        )

    destroy_mcp_infrastructure(session, workloads=mcp_workloads, dry_run=dry_run, report=report)

    if include_data:
        empty_s3_bucket(session, bucket_name, dry_run=dry_run, report=report)

    destroy_log_groups(session, project=project, dry_run=dry_run, report=report)

    if disable_bedrock_logging:
        result = disable_invocation_logging(session, dry_run=dry_run)
        if result.get("status") in ("disabled", "planned"):
            report.deleted.append(f"bedrock-logging:{result['status']}")
        elif result.get("status") == "skipped":
            report.skipped.append(f"bedrock-logging:{result.get('reason', 'skipped')}")

    if not dry_run:
        _cleanup_local_metadata()

    remaining = verify_remaining(session, project=project, bucket=bucket_name if include_data else None)
    # Filter out items already reported deleted this run (tag scan sees pre-delete state in dry-run)
    if dry_run:
        remaining = []
    if remaining:
        report.warnings.extend([f"still exists: {item}" for item in remaining[:25]])
        if len(remaining) > 25:
            report.warnings.append(f"... and {len(remaining) - 25} more")

    return report


def provision_sandbox(
    *,
    profile: str | None = "aws-agent",
    region: str = "us-east-1",
    project: str = "adop",
    bucket: str | None = None,
    workloads: list[str] | None = None,
    skip_gateway: bool = False,
    skip_harness: bool = False,
    skip_terraform: bool = False,
    auto_provision_workloads: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Bring up ADOP sandbox: Gateway (+ optional Harness) + workload deploy."""
    bucket_name = resolve_bucket(profile=profile, region=region, bucket=bucket)
    wl = workloads or ["advisory_transactions"]
    plan: list[str] = []

    if not skip_gateway:
        plan.append("deploy_mcp_gateway")
    if not skip_harness:
        plan.append("deploy_agentcore_harness")
    if auto_provision_workloads and not skip_terraform:
        plan.extend([f"deploy_workload:{w}" for w in wl])

    if dry_run:
        return {"dry_run": True, "bucket": bucket_name, "steps": plan}

    import sys

    py = sys.executable
    results: dict[str, Any] = {"bucket": bucket_name, "steps": {}}

    if not skip_gateway:
        subprocess.run(
            [py, "tools/deploy_mcp_gateway.py", "--profile", profile or "aws-agent", "--region", region, "--project", project],
            cwd=REPO_ROOT,
            check=True,
        )
        results["steps"]["gateway"] = "ok"

    if not skip_harness:
        subprocess.run(
            [py, "tools/deploy_agentcore_harness.py", "--profile", profile or "aws-agent", "--region", region, "--project", project],
            cwd=REPO_ROOT,
            check=True,
        )
        results["steps"]["harness"] = "ok"

    if auto_provision_workloads and not skip_terraform:
        for workload in wl:
            subprocess.run(
                [
                    py,
                    "tools/deploy_workload.py",
                    "--workload",
                    workload,
                    "--bucket",
                    bucket_name,
                    "--auto-provision",
                    "--aws-profile",
                    profile or "aws-agent",
                ],
                cwd=REPO_ROOT,
                check=True,
            )
            results["steps"][f"workload:{workload}"] = "ok"

    subprocess.run(
        [py, "tools/switch_mcp_mode.py", "--mode", "hybrid"],
        cwd=REPO_ROOT,
        check=True,
    )
    results["steps"]["mcp_mode"] = "hybrid"
    return results
