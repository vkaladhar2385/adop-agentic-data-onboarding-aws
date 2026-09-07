output "sfn_role_name" {
  value       = aws_iam_role.sfn.name
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
  value       = aws_glue_catalog_database.db.name
  description = "Glue catalog database for all zones."
}

output "kms_key_aliases" {
  value       = { for z, a in aws_kms_alias.zone : z => a.name }
  description = "Zone-scoped KMS aliases (Bronze/Silver/Gold)."
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
