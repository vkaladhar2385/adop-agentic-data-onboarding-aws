# ---- Per-function IAM (P1-12): catalog write vs verifier read ----
# register_catalog may tag Glue tables. post_deploy_verifier only reads
# Glue/Athena/KMS/SFN/CloudTrail. Do not share one union role.

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

locals {
  lambda_role_suffix = {
    register_catalog     = "register-catalog"
    post_deploy_verifier = "verifier"
  }
}

resource "aws_iam_role" "lambda_fn" {
  for_each           = var.iam_owner == "terraform" ? var.lambda_functions : {}
  name               = "${local.name}-${lookup(local.lambda_role_suffix, each.key, each.key)}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = local.tags
}

data "aws_iam_role" "lambda_fn" {
  for_each = var.iam_owner == "mcp" ? var.lambda_functions : {}
  name     = "${local.name}-${lookup(local.lambda_role_suffix, each.key, each.key)}-role"
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  for_each   = var.iam_owner == "terraform" ? var.lambda_functions : {}
  role       = aws_iam_role.lambda_fn[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "register_catalog" {
  statement {
    sid = "LakeFormationTagging"
    actions = [
      "lakeformation:CreateLFTag", "lakeformation:UpdateLFTag", "lakeformation:GetLFTag",
      "lakeformation:ListLFTags", "lakeformation:AddLFTagsToResource",
      "lakeformation:GetResourceLFTags", "lakeformation:GetDataAccess",
    ]
    resources = ["*"] # LF-Tags are account-scoped; no ARN-level scoping
  }
  statement {
    sid = "GlueRegisterTables"
    actions = [
      "glue:GetTable", "glue:GetTables", "glue:GetDatabase",
      "glue:GetPartition", "glue:GetPartitions",
      "glue:CreateTable", "glue:UpdateTable",
    ]
    resources = ["*"]
  }
  statement {
    sid     = "KmsTableData"
    actions = ["kms:DescribeKey", "kms:Decrypt", "kms:GenerateDataKey"]
    resources = local.zone_kms_arns
  }
  statement {
    sid     = "SilverGoldObjects"
    actions = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation"]
    resources = [
      "arn:aws:s3:::${var.data_lake_bucket}",
      "arn:aws:s3:::${var.data_lake_bucket}/silver/*",
      "arn:aws:s3:::${var.data_lake_bucket}/gold/*",
    ]
  }
}

data "aws_iam_policy_document" "verifier" {
  statement {
    sid       = "GlueRead"
    actions   = ["glue:GetTable", "glue:GetTables", "glue:GetDatabase", "glue:GetPartition", "glue:GetPartitions"]
    resources = ["*"]
  }
  statement {
    sid       = "LakeFormationRead"
    actions   = ["lakeformation:GetLFTag", "lakeformation:ListLFTags", "lakeformation:GetResourceLFTags"]
    resources = ["*"]
  }
  statement {
    sid       = "AthenaVerify"
    actions   = ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults"]
    resources = ["*"]
  }
  statement {
    sid     = "KmsVerifyAndDecrypt"
    actions = ["kms:DescribeKey", "kms:GetKeyRotationStatus", "kms:Decrypt", "kms:GenerateDataKey"]
    resources = local.zone_kms_arns
  }
  statement {
    sid       = "StateMachineVerify"
    actions   = ["states:ListStateMachines", "states:DescribeStateMachine"]
    resources = ["*"]
  }
  statement {
    sid       = "CloudTrailVerify"
    actions   = ["cloudtrail:LookupEvents"]
    resources = ["*"]
  }
  statement {
    sid     = "AthenaResultsAndReadTableData"
    actions = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation"]
    resources = [
      "arn:aws:s3:::${var.data_lake_bucket}",
      "arn:aws:s3:::${var.data_lake_bucket}/athena-results/*",
      "arn:aws:s3:::${var.data_lake_bucket}/silver/*",
      "arn:aws:s3:::${var.data_lake_bucket}/gold/*",
      "arn:aws:s3:::${var.data_lake_bucket}/quality-scores/*",
    ]
  }
  statement {
    sid     = "InvokeExtensionVerifiers"
    actions = ["lambda:InvokeFunction"]
    resources = [
      "arn:aws:lambda:${var.aws_region}:${var.account_id}:function:${var.workload}_index_gold_to_opensearch",
      "arn:aws:lambda:${var.aws_region}:${var.account_id}:function:${var.workload}_cache_quality_scores",
      "arn:aws:lambda:${var.aws_region}:${var.account_id}:function:${var.workload}_register_redshift_spectrum",
    ]
  }
  statement {
    sid       = "RedshiftSpectrumVerify"
    actions   = ["redshift-data:ExecuteStatement", "redshift-data:DescribeStatement", "redshift-data:GetStatementResult", "redshift-serverless:GetCredentials"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda_fn" {
  for_each = var.iam_owner == "terraform" ? var.lambda_functions : {}
  name     = "${local.name}-${lookup(local.lambda_role_suffix, each.key, each.key)}-policy"
  role     = aws_iam_role.lambda_fn[each.key].id
  policy   = each.key == "register_catalog" ? data.aws_iam_policy_document.register_catalog.json : data.aws_iam_policy_document.verifier.json
}

# ---- One aws_lambda_function per Step Functions Lambda target ----
# Deployment package expects the CI deploy workflow to have already uploaded
# s3://<bucket>/lambda-artifacts/<workload>/<artifact_key>.zip (see deploy.yml
# and docs/ARCHITECTURE.md#packaging for the lean-zip build steps).
resource "aws_lambda_function" "fn" {
  for_each = var.lambda_functions

  function_name = "${var.workload}_${each.key}"
  role          = local.lambda_role_arn_by_key[each.key]
  runtime       = "python3.12"
  handler       = each.value.handler
  timeout       = each.value.timeout
  memory_size   = each.value.memory_size

  s3_bucket = var.data_lake_bucket
  s3_key    = "lambda-artifacts/${var.workload}/${each.value.artifact_key}.zip"

  environment {
    variables = merge(
      { GLUE_DATABASE = local.glue_database_name, WORKLOAD = var.workload, DATA_LAKE_BUCKET = var.data_lake_bucket },
      each.value.environment,
    )
  }

  tags = local.tags
}
