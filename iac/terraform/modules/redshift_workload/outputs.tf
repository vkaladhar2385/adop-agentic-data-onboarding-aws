output "workgroup_endpoint" {
  value       = aws_redshiftserverless_workgroup.this.endpoint
  description = "Redshift Serverless workgroup endpoint (for BI tool connection strings)."
}

output "namespace_name" {
  value = aws_redshiftserverless_namespace.this.namespace_name
}

output "spectrum_role_arn" {
  value       = aws_iam_role.spectrum.arn
  description = "IAM role Redshift Spectrum assumes to read the Glue Catalog + Gold S3 objects."
}

output "register_spectrum_lambda_arn" {
  value = aws_lambda_function.register_spectrum.arn
}
