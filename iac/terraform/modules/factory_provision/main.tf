terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

locals {
  name     = "adop-factory-${var.environment}"
  repo_root = abspath("${path.module}/../../../..")
  tags = merge(var.tags, {
    Component = "factory-provision"
    ManagedBy = "Terraform"
  })
}
