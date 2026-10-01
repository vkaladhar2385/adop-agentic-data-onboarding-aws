variable "workload" {
  description = "Workload name (lowercase, underscores)."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
  default     = "eastus"
}

variable "resource_group_name" {
  description = "Resource group for the workload's data plane."
  type        = string
  default     = null
}

variable "storage_account_name" {
  description = "ADLS Gen2 storage account name (3-24 lowercase alphanumeric). Defaults to a derived name."
  type        = string
  default     = null
}

variable "lake_format" {
  description = "Table format for Silver/Gold (iceberg | delta)."
  type        = string
  default     = "iceberg"
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
