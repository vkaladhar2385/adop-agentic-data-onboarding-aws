# ---- IAM role assumed by every Lambda in this workload ----
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# register_catalog needs Lake Formation write; post_deploy_verifier needs
# read-only Glue/Athena/KMS/StepFunctions/CloudTrail. Granting the union to
# both keeps the module simple; tighten per-function in a hardened rollout.
data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    sid = "LakeFormationTagging"
    actions = [
      "lakeformation:CreateLFTag", "lakeformation:UpdateLFTag", "lakeformation:GetLFTag",
      "lakeformation:ListLFTags", "lakeformation:AddLFTagsToResource",
      "lakeformation:GetResourceLFTags", "lakeformation:GetDataAccess",
    ]
    resources = ["*"] # LF-Tags are account-scoped resources; no ARN-level scoping available
  }
  statement {
    sid = "GlueReadWrite"
    actions = [
      "glue:GetTable", "glue:GetTables", "glue:GetDatabase",
      "glue:GetPartition", "glue:GetPartitions",
      "glue:CreateTable", "glue:UpdateTable", # register_catalog registers Silver/Gold tables
    ]
    resources = ["*"]
  }
  statement {
    sid       = "AthenaVerify"
    actions   = ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults"]
    resources = ["*"]
  }
  statement {
    sid       = "KmsVerifyAndDecrypt"
    actions   = ["kms:DescribeKey", "kms:GetKeyRotationStatus", "kms:Decrypt", "kms:GenerateDataKey"]
    resources = [for k in aws_kms_key.zone : k.arn]
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
    sid     = "AthenaResultsAndTableData"
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

resource "aws_iam_role_policy" "lambda" {
  name   = "${local.name}-lambda-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

# ---- One aws_lambda_function per Step Functions Lambda target ----
# Deployment package expects the CI deploy workflow to have already uploaded
# s3://<bucket>/lambda-artifacts/<workload>/<artifact_key>.zip (see deploy.yml
# and docs/ARCHITECTURE.md#packaging for the lean-zip build steps).
resource "aws_lambda_function" "fn" {
  for_each = var.lambda_functions

  function_name = "${var.workload}_${each.key}"
  role          = aws_iam_role.lambda.arn
  runtime       = "python3.12"
  handler       = each.value.handler
  timeout       = each.value.timeout
  memory_size   = each.value.memory_size

  s3_bucket = var.data_lake_bucket
  s3_key    = "lambda-artifacts/${var.workload}/${each.value.artifact_key}.zip"

  environment {
    variables = merge(
      { GLUE_DATABASE = aws_glue_catalog_database.db.name, WORKLOAD = var.workload, DATA_LAKE_BUCKET = var.data_lake_bucket },
      each.value.environment,
    )
  }

  tags = local.tags
}
