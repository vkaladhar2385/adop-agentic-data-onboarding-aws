"""Per-function Lambda IAM (P1-12) — no AWS."""

from shared.deploy.mcp_iam import (
    _lambda_role_names,
    register_catalog_permissions_policy,
    verifier_permissions_policy,
)


def test_role_names_are_split():
    names = _lambda_role_names("advisory_transactions-dev")
    assert names["catalog"] == "advisory_transactions-dev-register-catalog-role"
    assert names["verifier"] == "advisory_transactions-dev-verifier-role"
    assert names["catalog"] != names["verifier"]


def test_verifier_cannot_create_glue_tables():
    policy = verifier_permissions_policy(
        bucket="lake",
        workload="demo",
        region="us-east-1",
        account_id="123",
        kms_arns=["arn:aws:kms:us-east-1:123:key/abc"],
    )
    actions = {a for stmt in policy["Statement"] for a in stmt["Action"]}
    assert "glue:CreateTable" not in actions
    assert "lakeformation:CreateLFTag" not in actions
    assert "lakeformation:AddLFTagsToResource" not in actions
    assert "glue:GetTable" in actions
    assert "athena:StartQueryExecution" in actions


def test_catalog_can_register_and_tag():
    policy = register_catalog_permissions_policy(
        bucket="lake",
        kms_arns=["arn:aws:kms:us-east-1:123:key/abc"],
    )
    actions = {a for stmt in policy["Statement"] for a in stmt["Action"]}
    assert "glue:CreateTable" in actions
    assert "lakeformation:AddLFTagsToResource" in actions
    assert "athena:StartQueryExecution" not in actions
    assert "cloudtrail:LookupEvents" not in actions


def test_lambda_tf_uses_per_function_roles():
    text = open("iac/terraform/modules/workload_pipeline/lambda.tf", encoding="utf-8").read()
    assert "aws_iam_role" in text and "lambda_fn" in text
    assert "register-catalog" in text
    assert "post_deploy_verifier" in text
    assert 'name               = "${local.name}-lambda-role"' not in text
