# Generated as an extension exercise (see docs/EXTENDING_TO_NEW_SERVICES.md):
# Redshift Serverless namespace/workgroup + Spectrum IAM role + a Lambda that
# runs `CREATE EXTERNAL SCHEMA ... FROM DATA CATALOG` so Redshift can query the
# existing Gold Iceberg tables with zero data duplication.

locals {
  name = "${var.workload}-${var.environment}-redshift"
  tags = merge(var.tags, {
    Project   = "ADOP-Pilot"
    Workload  = var.workload
    Extension = "redshift-spectrum"
    ManagedBy = "Terraform"
  })
}

# ---- IAM role Redshift assumes to read the Glue Catalog + Gold S3 objects ----
data "aws_iam_policy_document" "redshift_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["redshift.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "spectrum" {
  name               = "${local.name}-spectrum-role"
  assume_role_policy = data.aws_iam_policy_document.redshift_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "spectrum_permissions" {
  statement {
    sid       = "GlueCatalogRead"
    actions   = ["glue:GetDatabase", "glue:GetTable", "glue:GetTables", "glue:GetPartitions"]
    resources = ["*"]
  }
  statement {
    sid       = "ReadGoldObjects"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [
      "arn:aws:s3:::${var.data_lake_bucket}",
      "arn:aws:s3:::${var.data_lake_bucket}/gold/${var.workload}/*",
      "arn:aws:s3:::${var.data_lake_bucket}/gold/${var.workload}*",
    ]
  }
  statement {
    sid       = "DecryptGoldKms"
    actions   = ["kms:Decrypt"]
    resources = [var.gold_kms_key_arn]
  }
}

resource "aws_iam_role_policy" "spectrum" {
  name   = "${local.name}-spectrum-policy"
  role   = aws_iam_role.spectrum.id
  policy = data.aws_iam_policy_document.spectrum_permissions.json
}

# ---- Redshift Serverless: namespace + workgroup ----
# manage_admin_password delegates the admin credential to Secrets Manager --
# no plaintext password ever lives in state or this config.
resource "aws_redshiftserverless_namespace" "this" {
  namespace_name        = replace(local.name, "_", "-")
  admin_username        = var.admin_username
  manage_admin_password = true
  iam_roles             = [aws_iam_role.spectrum.arn]
  default_iam_role_arn  = aws_iam_role.spectrum.arn
  db_name               = "dev"
  tags                  = local.tags
}

# Redshift Serverless always provisions ENIs for the workgroup, even though
# this module only ever talks to it via the Data API (no direct network path
# needed) -- so it still requires a VPC/subnets/security group explicitly
# when the account has no default VPC. See docs/EXTENDING_TO_NEW_SERVICES.md.
data "aws_vpc" "default" {
  count   = var.vpc_id == null ? 1 : 0
  default = true
}

locals {
  vpc_id = var.vpc_id != null ? var.vpc_id : data.aws_vpc.default[0].id
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [local.vpc_id]
  }
}

resource "aws_security_group" "workgroup" {
  name        = "${local.name}-workgroup-sg"
  description = "Redshift Serverless workgroup ENIs. No direct network access used -- Lambda talks via the Data API."
  vpc_id      = local.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

resource "aws_redshiftserverless_workgroup" "this" {
  namespace_name      = aws_redshiftserverless_namespace.this.namespace_name
  workgroup_name      = replace(local.name, "_", "-")
  base_capacity       = var.base_capacity_rpu
  publicly_accessible = false
  subnet_ids          = data.aws_subnets.default.ids
  security_group_ids  = [aws_security_group.workgroup.id]
  tags                = local.tags
}

# ---- Lambda: creates the external schema once the workgroup is up ----
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

data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    sid = "RedshiftDataApi"
    actions = [
      "redshift-data:ExecuteStatement", "redshift-data:DescribeStatement", "redshift-data:GetStatementResult",
    ]
    resources = ["*"]
  }
  statement {
    sid       = "RedshiftServerlessAuth"
    actions   = ["redshift-serverless:GetCredentials"]
    resources = ["*"]
  }
  statement {
    sid       = "ReadAdminSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_redshiftserverless_namespace.this.admin_password_secret_arn]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${local.name}-lambda-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

# Deployment package expects s3://<bucket>/lambda-artifacts/<workload>/register_redshift_spectrum.zip
# (see deploy.yml). Lean zip: stdlib + boto3 only, same packaging philosophy as
# the core module's register_catalog Lambda.
resource "aws_lambda_function" "register_spectrum" {
  function_name = "${var.workload}_register_redshift_spectrum"
  role          = aws_iam_role.lambda.arn
  runtime       = "python3.12"
  handler       = "workloads.${var.workload}.scripts.load.register_redshift_spectrum.lambda_handler"
  timeout       = 180
  memory_size   = 256

  s3_bucket = var.data_lake_bucket
  s3_key    = "lambda-artifacts/${var.workload}/register_redshift_spectrum.zip"

  environment {
    variables = {
      WORKGROUP_NAME = aws_redshiftserverless_workgroup.this.workgroup_name
      DATABASE_NAME  = "dev"
      GLUE_DATABASE  = var.glue_database
      IAM_ROLE_ARN   = aws_iam_role.spectrum.arn
      SECRET_ARN     = aws_redshiftserverless_namespace.this.admin_password_secret_arn
    }
  }

  tags = local.tags
}
