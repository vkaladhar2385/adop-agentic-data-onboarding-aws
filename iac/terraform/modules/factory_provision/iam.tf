data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sfn" {
  name               = "${local.name}-sfn-role"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "sfn_permissions" {
  statement {
    sid       = "InvokeValidateAndE2E"
    actions   = ["lambda:InvokeFunction"]
    resources = [
      aws_lambda_function.validate.arn,
      aws_lambda_function.e2e.arn,
      aws_lambda_function.audit.arn,
    ]
  }

  statement {
    sid = "CodeBuildSync"
    actions = [
      "codebuild:StartBuild",
      "codebuild:StopBuild",
      "codebuild:BatchGetBuilds",
      "codebuild:BatchGetBuildBatches",
    ]
    resources = [aws_codebuild_project.factory.arn]
  }

  statement {
    sid = "CodeBuildLogs"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }

  statement {
    sid = "CodeBuildEvents"
    actions = [
      "events:PutRule",
      "events:PutTargets",
      "events:DescribeRule",
      "events:DeleteRule",
      "events:RemoveTargets",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "sfn" {
  name   = "${local.name}-sfn-policy"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sfn_permissions.json
}

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
    sid = "StartWorkloadPipeline"
    actions = [
      "states:StartExecution",
      "states:DescribeExecution",
      "states:ListStateMachines",
    ]
    resources = [
      "arn:aws:states:${var.aws_region}:${var.account_id}:stateMachine:*",
      "arn:aws:states:${var.aws_region}:${var.account_id}:execution:*:*",
    ]
  }

  statement {
    sid = "DataLakeReadWrite"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]
    resources = [
      "arn:aws:s3:::${var.data_lake_bucket}",
      "arn:aws:s3:::${var.data_lake_bucket}/*",
    ]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${local.name}-lambda-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

data "aws_iam_policy_document" "codebuild_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "codebuild" {
  name               = "${local.name}-codebuild-role"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "codebuild_basic" {
  role       = aws_iam_role.codebuild.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
}

data "aws_iam_policy_document" "codebuild_permissions" {
  statement {
    sid = "ReadRepoArtifact"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:ListBucket",
    ]
    resources = [
      "arn:aws:s3:::${var.data_lake_bucket}",
      "arn:aws:s3:::${var.data_lake_bucket}/${var.repo_artifact_key}",
      "arn:aws:s3:::${var.data_lake_bucket}/factory-artifacts/*",
    ]
  }

  statement {
    sid = "TerraformState"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      "arn:aws:s3:::${var.data_lake_bucket}",
      "arn:aws:s3:::${var.data_lake_bucket}/terraform-state/*",
    ]
  }

  statement {
    sid = "DataLakeDeploy"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]
    resources = [
      "arn:aws:s3:::${var.data_lake_bucket}",
      "arn:aws:s3:::${var.data_lake_bucket}/*",
    ]
  }

  statement {
    sid = "GlueJobs"
    actions = [
      "glue:*",
    ]
    resources = ["*"]
  }

  statement {
    sid = "LambdaDeploy"
    actions = [
      "lambda:*",
    ]
    resources = ["*"]
  }

  statement {
    sid = "StepFunctionsDeploy"
    actions = [
      "states:*",
    ]
    resources = ["*"]
  }

  statement {
    sid = "IAMPassRole"
    actions = [
      "iam:GetRole",
      "iam:PassRole",
      "iam:CreateRole",
      "iam:AttachRolePolicy",
      "iam:PutRolePolicy",
      "iam:GetRolePolicy",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:TagRole",
      "iam:CreatePolicy",
      "iam:GetPolicy",
      "iam:CreatePolicyVersion",
    ]
    resources = ["*"]
  }

  statement {
    sid = "SupportingServices"
    actions = [
      "kms:*",
      "sns:*",
      "events:*",
      "scheduler:*",
      "logs:*",
      "cloudwatch:*",
      "lakeformation:*",
      "athena:*",
    ]
    resources = ["*"]
  }

  statement {
    sid = "GlueSyncArtifacts"
    actions = [
      "glue:GetJob",
      "glue:UpdateJob",
      "glue:CreateJob",
      "glue:StartJobRun",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "codebuild" {
  name   = "${local.name}-codebuild-policy"
  role   = aws_iam_role.codebuild.id
  policy = data.aws_iam_policy_document.codebuild_permissions.json
}
