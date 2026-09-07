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
    python_version  = each.value.job_type == "pythonshell" ? "3.9" : "3" # "3" (i.e. 3.6) pythonshell runtime is retired
    name            = each.value.job_type == "pythonshell" ? "pythonshell" : "glueetl"
  }

  default_arguments = merge(
    {
      "--enable-continuous-cloudwatch-log" = "true"
      "--enable-metrics"                   = "true"
      "--TempDir"                          = "s3://${var.data_lake_bucket}/glue-temp/${var.workload}/"
      # Python Shell's pre-installed library set doesn't guarantee pyarrow;
      # this pip-installs it at job bootstrap (supported for both job types).
      "--additional-python-modules" = "pyarrow==15.0.2"
      # Standalone Glue scripts don't get a repo checkout. --extra-py-files
      # only supports flat files for Python Shell (no extracted package
      # tree), so tools/package_and_sync.py uploads pii.py/quality.py/s3_io.py/
      # local_runner.py flat and each script falls back to a plain `import
      # local_runner` etc. when the dotted `shared.utils...` import fails.
      "--extra-py-files" = join(",", [
        "s3://${var.data_lake_bucket}/glue-deps/${var.workload}/pii.py",
        "s3://${var.data_lake_bucket}/glue-deps/${var.workload}/quality.py",
        "s3://${var.data_lake_bucket}/glue-deps/${var.workload}/s3_io.py",
        "s3://${var.data_lake_bucket}/glue-deps/${var.workload}/local_runner.py",
      ])
      # local_runner.load_config() falls back to looking next to itself, i.e.
      # in this same flat working directory, when it's not run from a repo checkout.
      "--extra-files" = join(",", [
        "s3://${var.data_lake_bucket}/glue-deps/${var.workload}/transformations.yaml",
        "s3://${var.data_lake_bucket}/glue-deps/${var.workload}/quality_rules.yaml",
      ])
    },
    each.value.default_arguments,
  )

  tags = local.tags
}
