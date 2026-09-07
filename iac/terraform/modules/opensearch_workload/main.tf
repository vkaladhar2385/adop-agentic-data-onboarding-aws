# Generated as an extension exercise: single-instance OpenSearch domain + a
# Lambda that queries Gold via Athena and bulk-indexes rows for search. The
# domain's access policy is scoped to exactly the indexing Lambda's role --
# no public/anonymous access, unlike a lot of OpenSearch quickstarts.

locals {
  # OpenSearch domain names are capped at 28 chars, so this can't reuse the
  # full "<workload>-<env>-search" pattern every other module uses --
  # abbreviate the workload instead of hashing, to keep it human-readable.
  name = "${substr(var.workload, 0, 8)}-${var.environment}-search"
  tags = merge(var.tags, {
    Project   = "ADOP-Pilot"
    Workload  = var.workload
    Extension = "opensearch"
    ManagedBy = "Terraform"
  })
}

# ---- Lambda role (declared first so the domain access policy can reference it) ----
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

# ---- OpenSearch domain ----
resource "aws_opensearch_domain" "this" {
  domain_name    = replace(local.name, "_", "-")
  engine_version = "OpenSearch_2.11"

  cluster_config {
    instance_type  = var.instance_type
    instance_count = 1
  }

  ebs_options {
    ebs_enabled = true
    volume_type = "gp3"
    volume_size = var.volume_size_gb
  }

  encrypt_at_rest {
    enabled = true
  }

  node_to_node_encryption {
    enabled = true
  }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }

  # Scoped to the indexing Lambda's role only -- no public/anonymous access.
  access_policies = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = aws_iam_role.lambda.arn }
      Action    = "es:ESHttp*"
      Resource  = "arn:aws:es:${var.aws_region}:${var.account_id}:domain/${replace(local.name, "_", "-")}/*"
    }]
  })

  tags = local.tags
}

# ---- Lambda: Athena query on Gold + SigV4-signed bulk index into OpenSearch ----
data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    sid       = "AthenaQueryGold"
    actions   = ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults"]
    resources = ["*"]
  }
  statement {
    sid       = "GlueCatalogRead"
    actions   = ["glue:GetTable", "glue:GetTables", "glue:GetDatabase", "glue:GetPartition", "glue:GetPartitions"]
    resources = ["*"]
  }
  statement {
    sid     = "AthenaResultsAndGoldData"
    actions = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation"]
    resources = [
      "arn:aws:s3:::${var.data_lake_bucket}",
      "arn:aws:s3:::${var.data_lake_bucket}/athena-results/*",
      "arn:aws:s3:::${var.data_lake_bucket}/gold/*",
    ]
  }
  statement {
    sid       = "LakeFormationRead"
    actions   = ["lakeformation:GetDataAccess"]
    resources = ["*"]
  }
  statement {
    sid       = "IndexIntoOpenSearch"
    actions   = ["es:ESHttpPost", "es:ESHttpPut", "es:ESHttpGet"]
    resources = ["${aws_opensearch_domain.this.arn}/*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${local.name}-lambda-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

# Deployment package expects s3://<bucket>/lambda-artifacts/<workload>/index_gold_to_opensearch.zip
# (see deploy.yml). Stays lean: stdlib + boto3/botocore only -- SigV4 signing
# uses botocore.auth directly instead of adding the opensearch-py dependency.
resource "aws_lambda_function" "index_gold" {
  function_name = "${var.workload}_index_gold_to_opensearch"
  role          = aws_iam_role.lambda.arn
  runtime       = "python3.12"
  handler       = "workloads.${var.workload}.scripts.load.index_gold_to_opensearch.lambda_handler"
  timeout       = 120
  memory_size   = 256

  s3_bucket = var.data_lake_bucket
  s3_key    = "lambda-artifacts/${var.workload}/index_gold_to_opensearch.zip"

  environment {
    variables = {
      OPENSEARCH_ENDPOINT    = aws_opensearch_domain.this.endpoint
      GLUE_DATABASE          = var.glue_database
      AWS_REGION_NAME        = var.aws_region
      ATHENA_OUTPUT_LOCATION = "s3://${var.data_lake_bucket}/athena-results/"
    }
  }

  tags = local.tags
}
