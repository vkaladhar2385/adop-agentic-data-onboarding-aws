# Generated as an extension exercise: single-node ElastiCache Redis in the
# default VPC + a VPC-attached Lambda that caches quality-gate scores. Because
# this Lambda only ever talks to Redis (no other AWS API calls), it needs no
# NAT gateway/VPC endpoints -- attaching it to the VPC is enough. That trade-off
# is exactly why this is the *only* one of the three new services requiring a
# network decision; see docs/EXTENDING_TO_NEW_SERVICES.md#trade-offs.

locals {
  name = "${var.workload}-${var.environment}-cache"
  tags = merge(var.tags, {
    Project   = "ADOP-Pilot"
    Workload  = var.workload
    Extension = "redis"
    ManagedBy = "Terraform"
  })
}

# Falls back to the account's default VPC only when var.vpc_id is unset. Many
# sandbox/org accounts have no default VPC (ours doesn't) -- pass var.vpc_id
# explicitly in that case. See docs/EXTENDING_TO_NEW_SERVICES.md#trade-offs.
data "aws_vpc" "default" {
  count   = var.vpc_id == null ? 1 : 0
  default = true
}

locals {
  vpc_id = var.vpc_id != null ? var.vpc_id : data.aws_vpc.default[0].id
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [local.vpc_id]
  }
}

# ---- Security groups: Lambda -> Redis on 6379 only, nothing else ----
resource "aws_security_group" "lambda" {
  name        = "${local.name}-lambda-sg"
  description = "Cache Lambda: egress-only, no inbound needed."
  vpc_id      = local.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

resource "aws_security_group" "redis" {
  name        = "${local.name}-redis-sg"
  description = "Redis: inbound 6379 from the cache Lambda security group only."
  vpc_id      = local.vpc_id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

resource "aws_elasticache_subnet_group" "this" {
  name       = "${replace(local.name, "_", "-")}-subnet-group" # ElastiCache identifiers reject underscores
  subnet_ids = data.aws_subnets.default.ids
}

# Single-node cache.t3.micro keeps this a ~$12/mo sandbox line item; production
# would use a replication group with automatic failover across AZs.
resource "aws_elasticache_cluster" "this" {
  cluster_id         = replace(local.name, "_", "-")
  engine             = "redis"
  engine_version     = "7.1"
  node_type          = var.node_type
  num_cache_nodes    = 1
  port               = 6379
  subnet_group_name  = aws_elasticache_subnet_group.this.name
  security_group_ids = [aws_security_group.redis.id]
  tags               = local.tags
}

# ---- Lambda: writes {score, timestamp} into Redis, VPC-attached ----
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

# VPC-attached Lambdas need ENI management permissions in addition to basic logging.
resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_region" "current" {}

data "aws_route_tables" "vpc" {
  vpc_id = local.vpc_id
}

# Gateway endpoint so the VPC-attached cache Lambda can GetObject the quality
# score sidecar without a NAT gateway.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = local.vpc_id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = data.aws_route_tables.vpc.ids
  tags              = local.tags
}

data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    sid       = "ReadQualityScoreSidecar"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${var.data_lake_bucket}/quality-scores/${var.workload}/*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${local.name}-lambda-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

# Deployment package expects s3://<bucket>/lambda-artifacts/<workload>/cache_quality_scores.zip
# This is the one Lambda in the whole repo that bundles a real dependency
# (redis-py) instead of staying stdlib+boto3 -- there's no AWS-signed HTTP API
# for Redis, so a wire-protocol client is unavoidable. Documented explicitly in
# docs/EXTENDING_TO_NEW_SERVICES.md as the lean-vs-bundled trade-off.
resource "aws_lambda_function" "cache_scores" {
  function_name = "${var.workload}_cache_quality_scores"
  role          = aws_iam_role.lambda.arn
  runtime       = "python3.12"
  handler       = "workloads.${var.workload}.scripts.load.cache_quality_scores.lambda_handler"
  timeout       = 30
  memory_size   = 256

  s3_bucket = var.data_lake_bucket
  s3_key    = "lambda-artifacts/${var.workload}/cache_quality_scores.zip"

  vpc_config {
    subnet_ids         = data.aws_subnets.default.ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      REDIS_HOST       = aws_elasticache_cluster.this.cache_nodes[0].address
      REDIS_PORT       = "6379"
      DATA_LAKE_BUCKET = var.data_lake_bucket
    }
  }

  tags = local.tags
}
