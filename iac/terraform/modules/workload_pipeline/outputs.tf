output "sfn_role_name" {
  value       = local.sfn_role_name
  description = "Step Functions execution role name (root attaches extra invoke perms for extension Lambdas)."
}

output "state_machine_arn" {
  value       = aws_sfn_state_machine.pipeline.arn
  description = "Step Functions pipeline ARN."
}

output "schedule_name" {
  value       = aws_scheduler_schedule.trigger.name
  description = "EventBridge schedule name."
}

output "glue_database" {
  value       = local.glue_database_name
  description = "Glue catalog database for all zones (created by Terraform or MCP per catalog_owner)."
}

output "catalog_owner" {
  value       = var.catalog_owner
  description = "terraform or mcp — who owns Glue database creation."
}

output "kms_key_aliases" {
  value       = local.zone_kms_alias_map
  description = "Zone-scoped KMS aliases (Bronze/Silver/Gold)."
}

output "kms_owner" {
  value       = var.kms_owner
  description = "terraform or mcp — who owns zone KMS keys."
}

output "iam_owner" {
  value       = var.iam_owner
  description = "terraform or mcp — who owns pipeline IAM roles."
}

output "lakeformation_owner" {
  value       = var.lakeformation_owner
  description = "terraform or mcp — who owns Lake Formation grants."
}

output "alerts_topic_arn" {
  value       = aws_sns_topic.alerts.arn
  description = "SNS topic for pipeline/quality alerts."
}

output "glue_job_names" {
  value       = { for k, j in aws_glue_job.job : k => j.name }
  description = "All Glue job names provisioned for this workload."
}

output "lambda_function_arns" {
  value       = { for k, f in aws_lambda_function.fn : k => f.arn }
  description = "All Lambda function ARNs provisioned for this workload."
}
