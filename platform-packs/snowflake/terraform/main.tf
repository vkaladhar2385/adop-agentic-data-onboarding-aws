terraform {
  required_version = ">= 1.5"
  required_providers {
    snowflake = {
      source  = "snowflakedb/snowflake"
      version = ">= 2.0"
    }
  }
}

provider "snowflake" {
  organization_name = var.organization_name
  account_name      = var.account_name
  user              = var.user
  password          = var.password
  role              = var.role
}

locals {
  table_name = var.table != "" ? var.table : "GOLD_${upper(replace(var.workload, "-", "_"))}"
}

resource "snowflake_database" "analytics" {
  name = var.database
}

resource "snowflake_schema" "gold" {
  database = snowflake_database.analytics.name
  name     = var.schema
}

# Gate B skeleton — live Gate C adds external volume + full Iceberg DDL (see rendered SQL).
resource "snowflake_iceberg_table" "gold" {
  database        = snowflake_database.analytics.name
  schema          = snowflake_schema.gold.name
  name            = local.table_name
  catalog         = "SNOWFLAKE"
  external_volume = var.external_volume
  comment         = "ADOP Mode A Gold sink for ${var.workload}"

  column {
    name = "SUPPLIER_ID"
    type = "VARCHAR"
  }
  column {
    name = "PRODUCT_CATEGORY"
    type = "VARCHAR"
  }
  column {
    name = "LEAD_TIME_DAYS"
    type = "NUMBER"
  }
}
