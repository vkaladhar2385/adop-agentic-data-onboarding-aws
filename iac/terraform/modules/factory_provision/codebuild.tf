resource "aws_cloudwatch_log_group" "codebuild" {
  name              = "/aws/codebuild/${local.name}"
  retention_in_days = 14
  tags              = local.tags
}

resource "aws_codebuild_project" "factory" {
  name          = local.name
  description   = "Option B factory provision — runs deploy_workload (no laptop)"
  service_role  = aws_iam_role.codebuild.arn
  build_timeout = var.codebuild_timeout_minutes

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/amazonlinux2-x86_64-standard:5.0"
    type                        = "LINUX_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"
    privileged_mode             = false

    environment_variable {
      name  = "ADOP_DATA_LAKE_BUCKET"
      value = var.data_lake_bucket
    }
    environment_variable {
      name  = "TF_STATE_BUCKET"
      value = var.data_lake_bucket
    }
    environment_variable {
      name  = "TF_STATE_KEY"
      value = var.terraform_state_key
    }
    environment_variable {
      name  = "TF_STATE_REGION"
      value = var.aws_region
    }
  }

  source {
    type      = "S3"
    location  = "${var.data_lake_bucket}/${var.repo_artifact_key}"
    buildspec = file("${path.module}/buildspec.yml")
  }

  logs_config {
    cloudwatch_logs {
      group_name = aws_cloudwatch_log_group.codebuild.name
    }
  }

  tags = local.tags
}
