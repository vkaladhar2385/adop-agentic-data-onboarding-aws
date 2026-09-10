resource "aws_sfn_state_machine" "factory" {
  name     = var.state_machine_name
  role_arn = aws_iam_role.sfn.arn
  definition = templatefile("${path.module}/../../../../orchestration/factory_provision_state_machine.json", {
    factory_validate_lambda_arn = aws_lambda_function.validate.arn
    factory_e2e_lambda_arn      = aws_lambda_function.e2e.arn
    factory_audit_lambda_arn    = aws_lambda_function.audit.arn
    factory_codebuild_project   = aws_codebuild_project.factory.name
  })
  tags = local.tags
}
