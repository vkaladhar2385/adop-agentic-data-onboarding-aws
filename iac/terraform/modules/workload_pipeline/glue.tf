# ---- IAM role assumed by every Glue job in this workload ----
data "aws_iam_policy_document" "glue_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue" {
  name               = "${local.name}-glue-role"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

# Scoped to this workload's S3 prefixes (scripts + zones) and its own KMS keys.
data "aws_iam_policy_document" "glue_permissions" {
  statement {
    sid     = "ReadWriteWorkloadData"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [
      "arn:aws:s3:::${var.data_lake_bucket}/*/${var.workload}/*",
      "arn:aws:s3:::${var.data_lake_bucket}/workloads/${var.workload}/*",
      "arn:aws:s3:::${var.data_lake_bucket}/landing/${var.workload}/*",
    ]
  }
  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.data_lake_bucket}"]
  }
  statement {
    sid       = "UseZoneKmsKeys"
    actions   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey*", "kms:DescribeKey"]
    resources = [for k in aws_kms_key.zone : k.arn]
  }
  statement {
    sid       = "GlueCatalogDb"
    actions   = ["glue:GetDatabase", "glue:GetTable", "glue:GetTables", "glue:CreateTable", "glue:UpdateTable"]
    resources = ["*"] # Glue catalog resource-level perms are coarse; scope via Lake Formation instead
  }
}

resource "aws_iam_role_policy" "glue" {
  name   = "${local.name}-glue-policy"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue_permissions.json
}

locals {
  glue_deps_py_files = [
    "s3://${var.data_lake_bucket}/glue-deps/${var.workload}/pii.py",
    "s3://${var.data_lake_bucket}/glue-deps/${var.workload}/quality.py",
    "s3://${var.data_lake_bucket}/glue-deps/${var.workload}/s3_io.py",
    "s3://${var.data_lake_bucket}/glue-deps/${var.workload}/local_runner.py",
    "s3://${var.data_lake_bucket}/glue-deps/${var.workload}/spark_transforms.py",
  ]
  glue_deps_config_files = [
    "s3://${var.data_lake_bucket}/glue-deps/${var.workload}/transformations.yaml",
    "s3://${var.data_lake_bucket}/glue-deps/${var.workload}/quality_rules.yaml",
  ]
}

# ---- One aws_glue_job per pipeline step ----
# script_location expects the CI deploy workflow to have already run
# `aws s3 sync workloads/<workload>/ s3://<bucket>/workloads/<workload>/`.
resource "aws_glue_job" "job" {
  for_each = var.glue_jobs

  name              = "${var.workload}_${each.key}"
  role_arn          = aws_iam_role.glue.arn
  glue_version      = each.value.job_type == "pythonshell" ? "3.0" : "4.0"
  max_retries       = 1
  timeout           = each.value.job_type == "pythonshell" ? 15 : 60
  number_of_workers = each.value.job_type == "pythonshell" ? null : 2
  worker_type       = each.value.job_type == "pythonshell" ? null : "G.1X"
  max_capacity      = each.value.job_type == "pythonshell" ? 0.0625 : null

  command {
    script_location = "s3://${var.data_lake_bucket}/workloads/${var.workload}/${each.value.script_path}"
    python_version  = each.value.job_type == "pythonshell" ? "3.9" : "3"
    name            = each.value.job_type == "pythonshell" ? "pythonshell" : "glueetl"
  }

  default_arguments = merge(
    {
      "--enable-continuous-cloudwatch-log" = "true"
      "--enable-metrics"                   = "true"
      "--TempDir"                          = "s3://${var.data_lake_bucket}/glue-temp/${var.workload}/"
      "--extra-py-files"                   = join(",", local.glue_deps_py_files)
      "--extra-files"                      = join(",", local.glue_deps_config_files)
    },
    each.value.job_type == "glueetl" ? {
      "--job-language"        = "python"
      "--datalake-formats"    = "iceberg"
      "--enable-data-lineage" = "true"
    } : {
      # Python Shell: pyarrow for pandas parquet I/O at demo scale.
      "--additional-python-modules" = "pyarrow==15.0.2"
    },
    each.value.default_arguments,
  )

  tags = local.tags
}
