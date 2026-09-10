data "archive_file" "validate_lambda" {
  type        = "zip"
  output_path = "${path.module}/build/validate.zip"

  source {
    content  = file("${path.module}/lambdas/validate/handler.py")
    filename = "handler.py"
  }
  source {
    content  = file("${local.repo_root}/shared/__init__.py")
    filename = "shared/__init__.py"
  }
  source {
    content  = file("${local.repo_root}/shared/deploy/__init__.py")
    filename = "shared/deploy/__init__.py"
  }
  source {
    content  = file("${local.repo_root}/shared/deploy/factory_provision.py")
    filename = "shared/deploy/factory_provision.py"
  }
}

data "archive_file" "e2e_lambda" {
  type        = "zip"
  output_path = "${path.module}/build/e2e.zip"

  source {
    content  = file("${path.module}/lambdas/e2e/handler.py")
    filename = "handler.py"
  }
  source {
    content  = file("${local.repo_root}/shared/__init__.py")
    filename = "shared/__init__.py"
  }
  source {
    content  = file("${local.repo_root}/shared/deploy/__init__.py")
    filename = "shared/deploy/__init__.py"
  }
  source {
    content  = file("${local.repo_root}/shared/deploy/sfn_e2e.py")
    filename = "shared/deploy/sfn_e2e.py"
  }
}

resource "aws_lambda_function" "validate" {
  function_name = "${local.name}-validate"
  role          = aws_iam_role.lambda.arn
  runtime       = "python3.12"
  handler       = "handler.handler"
  timeout       = 30
  memory_size   = 256

  filename         = data.archive_file.validate_lambda.output_path
  source_code_hash = data.archive_file.validate_lambda.output_base64sha256

  environment {
    variables = {
      ADOP_FACTORY_ALLOWED_WORKLOADS = join(",", var.allowed_workloads)
    }
  }

  tags = local.tags
}

resource "aws_lambda_function" "e2e" {
  function_name = "${local.name}-e2e"
  role          = aws_iam_role.lambda.arn
  runtime       = "python3.12"
  handler       = "handler.handler"
  timeout       = 900
  memory_size   = 512

  filename         = data.archive_file.e2e_lambda.output_path
  source_code_hash = data.archive_file.e2e_lambda.output_base64sha256

  tags = local.tags
}

resource "aws_lambda_permission" "sfn_validate" {
  statement_id  = "AllowFactorySfnInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.validate.function_name
  principal     = "states.amazonaws.com"
  source_arn    = aws_sfn_state_machine.factory.arn
}

resource "aws_lambda_permission" "sfn_e2e" {
  statement_id  = "AllowFactorySfnInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.e2e.function_name
  principal     = "states.amazonaws.com"
  source_arn    = aws_sfn_state_machine.factory.arn
}
