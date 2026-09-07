# Extension module (added after the core pilot): Redshift Serverless as a
# BI-facing query layer over the Gold zone, via Redshift Spectrum against the
# existing Glue Data Catalog (no data copy -- Spectrum reads S3/Iceberg directly).
# See docs/EXTENDING_TO_NEW_SERVICES.md for the design recipe this follows.

variable "workload" {
  type        = string
  description = "Workload whose Gold database gets exposed, e.g. advisory_transactions."
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
  description = "Base data-lake bucket (Lambda deployment package lives under lambda-artifacts/<workload>/)."
}

variable "glue_database" {
  type        = string
  description = "Glue catalog database backing this workload's Gold tables (module.<workload>.glue_database)."
}

variable "gold_kms_key_arn" {
  type        = string
  description = "Gold-zone KMS key ARN, so the Spectrum IAM role can decrypt Gold objects."
}

variable "base_capacity_rpu" {
  type        = number
  default     = 8
  description = "Redshift Serverless base capacity in RPUs (8 = smallest allowed, cheapest sandbox setting)."
}

variable "admin_username" {
  type    = string
  default = "adop_admin"
}

variable "vpc_id" {
  type        = string
  default     = null
  description = "VPC for the workgroup's network interfaces (Redshift Serverless requires one even though the Data API path used here never needs direct network access). Null falls back to the account's default VPC -- pass explicitly if the account has none."
}

variable "tags" {
  type    = map(string)
  default = {}
}
