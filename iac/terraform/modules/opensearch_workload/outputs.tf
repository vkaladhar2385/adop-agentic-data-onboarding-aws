output "domain_endpoint" {
  value       = aws_opensearch_domain.this.endpoint
  description = "HTTPS endpoint for the OpenSearch domain."
}

output "domain_arn" {
  value = aws_opensearch_domain.this.arn
}

output "index_lambda_arn" {
  value = aws_lambda_function.index_gold.arn
}
