variable "environment" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "account_id" {
  type = string
}

variable "data_lake_bucket" {
  type        = string
  description = "Data lake bucket (CodeBuild source zip, terraform state, artifacts)."
}

variable "tags" {
  type = map(string)
}

variable "state_machine_name" {
  type    = string
  default = "adop_factory_provision"
}

variable "repo_artifact_key" {
  type        = string
  default     = "factory-artifacts/adop-repo.zip"
  description = "S3 key for CodeBuild source zip (upload via tools/package_factory_artifact.py)."
}

variable "terraform_state_key" {
  type    = string
  default = "terraform-state/adop/root.tfstate"
}

variable "codebuild_timeout_minutes" {
  type    = number
  default = 60
}

variable "allowed_workloads" {
  type        = list(string)
  default     = ["supplier_lead_times", "product_inventory", "advisory_transactions", "web_events"]
  description = "Comma-separated allowlist passed to validate Lambda."
}
