variable "workload" {
  type = string
}

variable "workspace_url" {
  type        = string
  description = "Databricks workspace URL (Gate C)."
  default     = "https://dbc-placeholder.cloud.databricks.com"
}

variable "lake_format" {
  type    = string
  default = "delta"
}
