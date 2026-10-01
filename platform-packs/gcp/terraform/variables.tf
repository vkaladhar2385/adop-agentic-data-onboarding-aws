variable "workload" {
  type        = string
  description = "Workload name."
}

variable "project_id" {
  type        = string
  description = "GCP project ID."
  default     = "adop-gcp-demo"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "bucket_name" {
  type        = string
  description = "GCS lake bucket (globally unique)."
  default     = null
}

variable "tags" {
  type    = map(string)
  default = {}
}
