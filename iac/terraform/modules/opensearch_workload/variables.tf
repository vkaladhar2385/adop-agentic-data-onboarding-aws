# Extension module: OpenSearch as a full-text/analytics search layer over Gold
# rows (e.g. client/transaction lookup for a support-desk UI). See
# docs/EXTENDING_TO_NEW_SERVICES.md for the design recipe this follows.

variable "workload" {
  type        = string
  description = "Workload whose Gold rows get indexed, e.g. advisory_transactions."
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "account_id" {
  type        = string
  description = "Target AWS account id (sandbox for the pilot)."
}

variable "data_lake_bucket" {
  type        = string
  description = "Base data-lake bucket (Lambda deployment package + Athena results live under it)."
}

variable "glue_database" {
  type        = string
  description = "Glue catalog database queried (via Athena) to source rows for indexing."
}

variable "instance_type" {
  type    = string
  default = "t3.small.search"
}

variable "volume_size_gb" {
  type    = number
  default = 10
}

variable "tags" {
  type    = map(string)
  default = {}
}
