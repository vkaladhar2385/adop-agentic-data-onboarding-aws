variable "workload" {
  type = string
}

variable "organization_name" {
  type    = string
  default = "PLACEHOLDER_ORG"
}

variable "account_name" {
  type    = string
  default = "PLACEHOLDER_ACCT"
}

variable "user" {
  type    = string
  default = "TERRAFORM_SVC"
}

variable "password" {
  type      = string
  default   = "placeholder"
  sensitive = true
}

variable "role" {
  type    = string
  default = "ACCOUNTADMIN"
}

variable "database" {
  type    = string
  default = "ADOP_ANALYTICS"
}

variable "schema" {
  type    = string
  default = "GOLD"
}

variable "table" {
  type    = string
  default = ""
}

variable "external_volume" {
  type        = string
  description = "Existing external volume name (created in Gate C)."
  default     = "ADOP_PLACEHOLDER_GOLD_VOL"
}

variable "warehouse" {
  type    = string
  default = "ADOP_WH"
}
