output "redis_endpoint" {
  value       = aws_elasticache_cluster.this.cache_nodes[0].address
  description = "Redis primary endpoint address (VPC-internal only)."
}

output "cache_lambda_arn" {
  value = aws_lambda_function.cache_scores.arn
}
