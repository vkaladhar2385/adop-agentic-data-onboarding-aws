output "state_machine_arn" {
  value       = aws_sfn_state_machine.factory.arn
  description = "Factory provision Step Functions ARN (Gateway trigger_provision target)."
}

output "state_machine_name" {
  value = aws_sfn_state_machine.factory.name
}

output "codebuild_project_name" {
  value = aws_codebuild_project.factory.name
}

output "validate_lambda_arn" {
  value = aws_lambda_function.validate.arn
}

output "e2e_lambda_arn" {
  value = aws_lambda_function.e2e.arn
}

output "audit_lambda_arn" {
  value = aws_lambda_function.audit.arn
}

output "repo_artifact_s3_uri" {
  value = "s3://${var.data_lake_bucket}/${var.repo_artifact_key}"
}
