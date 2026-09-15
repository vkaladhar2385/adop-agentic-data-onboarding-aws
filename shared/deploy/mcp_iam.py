"""MCP-equivalent IAM roles for workload_pipeline (boto3 fallback)."""

from __future__ import annotations

import json
from typing import Any

from shared.deploy.sandbox_tags import iam_tag_list, tag_iam_role


def _ensure_role(iam: Any, name: str, assume_policy: dict, *, dry_run: bool, tags: list[dict] | None = None) -> str:
    if dry_run:
        print(f"[dry-run] iam create_role name={name}")
        return f"arn:aws:iam::000000000000:role/{name}"

    try:
        resp = iam.get_role(RoleName=name)
        if not dry_run:
            tag_iam_role(iam, name)
        return resp["Role"]["Arn"]
    except iam.exceptions.NoSuchEntityException:
        pass

    kwargs: dict[str, Any] = {
        "RoleName": name,
        "AssumeRolePolicyDocument": json.dumps(assume_policy),
        "Description": f"ADOP MCP-owned role {name}",
    }
    if tags:
        kwargs["Tags"] = tags
    resp = iam.create_role(**kwargs)
    print(f"Created IAM role: {name}")
    tag_iam_role(iam, name, cfg=None)
    return resp["Role"]["Arn"]


def _put_inline_policy(iam: Any, role_name: str, policy_name: str, policy: dict, *, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] iam put_role_policy role={role_name} policy={policy_name}")
        return
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName=policy_name,
        PolicyDocument=json.dumps(policy),
    )
    print(f"Updated inline policy {policy_name} on {role_name}")


def _attach_managed(iam: Any, role_name: str, policy_arn: str, *, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] iam attach_role_policy role={role_name} arn={policy_arn}")
        return
    iam.attach_role_policy(RoleName=role_name, PolicyArn=policy_arn)


def glue_assume_policy() -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "glue.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }


def glue_permissions_policy(*, bucket: str, workload: str, kms_arns: list[str]) -> dict:
    zone_paths = [
        f"arn:aws:s3:::{bucket}/{zone}/{workload}/*"
        for zone in ["bronze", "silver", "gold", "quarantine", "glue-temp"]
    ]
    zone_prefixes = [
        f"arn:aws:s3:::{bucket}/{zone}/{workload}*"
        for zone in ["bronze", "silver", "gold", "quarantine"]
    ]
    extra = [
        f"arn:aws:s3:::{bucket}/workloads/{workload}/*",
        f"arn:aws:s3:::{bucket}/landing/{workload}/*",
        f"arn:aws:s3:::{bucket}/glue-deps/{workload}/*",
        f"arn:aws:s3:::{bucket}/quality-scores/{workload}/*",
    ]
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "ReadWriteWorkloadData",
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                "Resource": zone_paths + zone_prefixes + extra,
            },
            {
                "Sid": "ListBucket",
                "Effect": "Allow",
                "Action": ["s3:ListBucket"],
                "Resource": [f"arn:aws:s3:::{bucket}"],
            },
            {
                "Sid": "UseZoneKmsKeys",
                "Effect": "Allow",
                "Action": ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey*", "kms:DescribeKey"],
                "Resource": kms_arns,
            },
            {
                "Sid": "GlueCatalogDb",
                "Effect": "Allow",
                "Action": [
                    "glue:GetDatabase",
                    "glue:GetTable",
                    "glue:GetTables",
                    "glue:CreateTable",
                    "glue:UpdateTable",
                    "glue:DeleteTable",
                ],
                "Resource": ["*"],
            },
            {
                "Sid": "LakeFormationDataAccess",
                "Effect": "Allow",
                "Action": ["lakeformation:GetDataAccess"],
                "Resource": ["*"],
            },
        ],
    }


def lambda_assume_policy() -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }


def register_catalog_permissions_policy(*, bucket: str, kms_arns: list[str]) -> dict:
    """Write path: register_catalog Lambda (LF-Tags + Glue tables)."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "LakeFormationTagging",
                "Effect": "Allow",
                "Action": [
                    "lakeformation:CreateLFTag",
                    "lakeformation:UpdateLFTag",
                    "lakeformation:GetLFTag",
                    "lakeformation:ListLFTags",
                    "lakeformation:AddLFTagsToResource",
                    "lakeformation:GetResourceLFTags",
                    "lakeformation:GetDataAccess",
                ],
                "Resource": ["*"],
            },
            {
                "Sid": "GlueRegisterTables",
                "Effect": "Allow",
                "Action": [
                    "glue:GetTable",
                    "glue:GetTables",
                    "glue:GetDatabase",
                    "glue:GetPartition",
                    "glue:GetPartitions",
                    "glue:CreateTable",
                    "glue:UpdateTable",
                ],
                "Resource": ["*"],
            },
            {
                "Sid": "KmsTableData",
                "Effect": "Allow",
                "Action": ["kms:DescribeKey", "kms:Decrypt", "kms:GenerateDataKey"],
                "Resource": kms_arns,
            },
            {
                "Sid": "SilverGoldObjects",
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation"],
                "Resource": [
                    f"arn:aws:s3:::{bucket}",
                    f"arn:aws:s3:::{bucket}/silver/*",
                    f"arn:aws:s3:::{bucket}/gold/*",
                ],
            },
        ],
    }


def verifier_permissions_policy(*, bucket: str, workload: str, region: str, account_id: str, kms_arns: list[str]) -> dict:
    """Read path: post_deploy_verifier Lambda (no Glue CreateTable / LF write)."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "GlueRead",
                "Effect": "Allow",
                "Action": [
                    "glue:GetTable",
                    "glue:GetTables",
                    "glue:GetDatabase",
                    "glue:GetPartition",
                    "glue:GetPartitions",
                ],
                "Resource": ["*"],
            },
            {
                "Sid": "LakeFormationRead",
                "Effect": "Allow",
                "Action": ["lakeformation:GetLFTag", "lakeformation:ListLFTags", "lakeformation:GetResourceLFTags"],
                "Resource": ["*"],
            },
            {
                "Sid": "AthenaVerify",
                "Effect": "Allow",
                "Action": ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults"],
                "Resource": ["*"],
            },
            {
                "Sid": "KmsVerifyAndDecrypt",
                "Effect": "Allow",
                "Action": ["kms:DescribeKey", "kms:GetKeyRotationStatus", "kms:Decrypt", "kms:GenerateDataKey"],
                "Resource": kms_arns,
            },
            {
                "Sid": "StateMachineVerify",
                "Effect": "Allow",
                "Action": ["states:ListStateMachines", "states:DescribeStateMachine"],
                "Resource": ["*"],
            },
            {
                "Sid": "CloudTrailVerify",
                "Effect": "Allow",
                "Action": ["cloudtrail:LookupEvents"],
                "Resource": ["*"],
            },
            {
                "Sid": "AthenaResultsAndReadTableData",
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation"],
                "Resource": [
                    f"arn:aws:s3:::{bucket}",
                    f"arn:aws:s3:::{bucket}/athena-results/*",
                    f"arn:aws:s3:::{bucket}/silver/*",
                    f"arn:aws:s3:::{bucket}/gold/*",
                    f"arn:aws:s3:::{bucket}/quality-scores/*",
                ],
            },
            {
                "Sid": "InvokeExtensionVerifiers",
                "Effect": "Allow",
                "Action": ["lambda:InvokeFunction"],
                "Resource": [
                    f"arn:aws:lambda:{region}:{account_id}:function:{workload}_index_gold_to_opensearch",
                    f"arn:aws:lambda:{region}:{account_id}:function:{workload}_cache_quality_scores",
                    f"arn:aws:lambda:{region}:{account_id}:function:{workload}_register_redshift_spectrum",
                ],
            },
            {
                "Sid": "RedshiftSpectrumVerify",
                "Effect": "Allow",
                "Action": [
                    "redshift-data:ExecuteStatement",
                    "redshift-data:DescribeStatement",
                    "redshift-data:GetStatementResult",
                    "redshift-serverless:GetCredentials",
                ],
                "Resource": ["*"],
            },
        ],
    }


def sfn_assume_policy() -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "states.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }


def sfn_permissions_policy(*, workload: str, region: str, account_id: str) -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "RunGlueJobs",
                "Effect": "Allow",
                "Action": ["glue:StartJobRun", "glue:GetJobRun", "glue:GetJobRuns", "glue:BatchStopJobRun"],
                "Resource": [f"arn:aws:glue:{region}:{account_id}:job/{workload}_*"],
            },
            {
                "Sid": "InvokeLambdas",
                "Effect": "Allow",
                "Action": ["lambda:InvokeFunction"],
                "Resource": [f"arn:aws:lambda:{region}:{account_id}:function:{workload}_*"],
            },
            {
                "Sid": "PublishAlerts",
                "Effect": "Allow",
                "Action": ["sns:Publish"],
                "Resource": [f"arn:aws:sns:{region}:{account_id}:{workload}-alerts"],
            },
        ],
    }


def scheduler_assume_policy() -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "scheduler.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }


def scheduler_permissions_policy(*, workload: str, region: str, account_id: str) -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["states:StartExecution"],
                "Resource": [f"arn:aws:states:{region}:{account_id}:stateMachine:{workload}_pipeline"],
            }
        ],
    }


def _resolve_kms_arns(workload: str, zones: list[str], *, dry_run: bool) -> list[str]:
    if dry_run:
        return [f"arn:aws:kms:us-east-1:000000000000:key/dry-run-{z}" for z in zones]

    import boto3

    kms = boto3.client("kms")
    arns: list[str] = []
    for zone in zones:
        alias = f"alias/{workload}-{zone}"
        meta = kms.describe_key(KeyId=alias)["KeyMetadata"]
        arns.append(meta["Arn"])
    return arns


def _lambda_role_names(name_prefix: str) -> dict[str, str]:
    return {
        "catalog": f"{name_prefix}-register-catalog-role",
        "verifier": f"{name_prefix}-verifier-role",
    }


def _ensure_lambda_execution_role(
    iam: Any,
    *,
    role_name: str,
    policy_name: str,
    policy: dict,
    role_tags: list[dict] | None,
    dry_run: bool,
) -> str:
    arn = _ensure_role(iam, role_name, lambda_assume_policy(), dry_run=dry_run, tags=role_tags)
    _attach_managed(iam, role_name, "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole", dry_run=dry_run)
    _put_inline_policy(iam, role_name, policy_name, policy, dry_run=dry_run)
    return arn


def ensure_pipeline_roles(
    *,
    name_prefix: str,
    workload: str,
    bucket: str,
    zones: list[str],
    dry_run: bool,
) -> dict[str, str]:
    """Create Glue, per-function Lambda, SFN, and Scheduler roles when iam.owner=mcp."""
    glue_role = f"{name_prefix}-glue-role"
    lambda_names = _lambda_role_names(name_prefix)
    sfn_role = f"{name_prefix}-sfn-role"
    scheduler_role = f"{name_prefix}-scheduler-role"

    kms_arns = _resolve_kms_arns(workload, zones, dry_run=dry_run)

    if dry_run:
        region = "us-east-1"
        account_id = "000000000000"
        iam = None
        role_tags = None
    else:
        import boto3

        sts = boto3.client("sts")
        ident = sts.get_caller_identity()
        account_id = ident["Account"]
        region = boto3.session.Session().region_name or "us-east-1"
        iam = boto3.client("iam")
        role_tags = iam_tag_list()

    catalog_policy = register_catalog_permissions_policy(bucket=bucket, kms_arns=kms_arns)
    verifier_policy = verifier_permissions_policy(
        bucket=bucket, workload=workload, region=region, account_id=account_id, kms_arns=kms_arns
    )

    glue_arn = _ensure_role(iam, glue_role, glue_assume_policy(), dry_run=dry_run, tags=role_tags)
    _attach_managed(iam, glue_role, "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole", dry_run=dry_run)
    _put_inline_policy(
        iam,
        glue_role,
        f"{name_prefix}-glue-policy",
        glue_permissions_policy(bucket=bucket, workload=workload, kms_arns=kms_arns),
        dry_run=dry_run,
    )

    catalog_arn = _ensure_lambda_execution_role(
        iam,
        role_name=lambda_names["catalog"],
        policy_name=f"{name_prefix}-register-catalog-policy",
        policy=catalog_policy,
        role_tags=role_tags,
        dry_run=dry_run,
    )
    verifier_arn = _ensure_lambda_execution_role(
        iam,
        role_name=lambda_names["verifier"],
        policy_name=f"{name_prefix}-verifier-policy",
        policy=verifier_policy,
        role_tags=role_tags,
        dry_run=dry_run,
    )

    sfn_arn = _ensure_role(iam, sfn_role, sfn_assume_policy(), dry_run=dry_run, tags=role_tags)
    _put_inline_policy(
        iam,
        sfn_role,
        f"{name_prefix}-sfn-policy",
        sfn_permissions_policy(workload=workload, region=region, account_id=account_id),
        dry_run=dry_run,
    )
    scheduler_arn = _ensure_role(iam, scheduler_role, scheduler_assume_policy(), dry_run=dry_run, tags=role_tags)
    _put_inline_policy(
        iam,
        scheduler_role,
        f"{name_prefix}-scheduler-policy",
        scheduler_permissions_policy(workload=workload, region=region, account_id=account_id),
        dry_run=dry_run,
    )

    return {
        "glue": glue_arn,
        "lambda": catalog_arn,  # LF grants use the catalog Lambda role
        "lambda_catalog": catalog_arn,
        "lambda_verifier": verifier_arn,
        "sfn": sfn_arn,
        "scheduler": scheduler_arn,
    }
