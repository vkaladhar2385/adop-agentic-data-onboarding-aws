# Lake Formation grants for Glue ETL (Iceberg writes) and zone S3 paths.
# When lakeformation_owner=mcp, grants are created by tools/mcp_deploy_infrastructure.py.

resource "aws_lakeformation_permissions" "glue_database" {
  count       = var.lakeformation_owner == "terraform" ? 1 : 0
  principal   = local.glue_role_arn
  permissions = ["CREATE_TABLE", "ALTER", "DROP", "DESCRIBE"]

  database {
    name = local.glue_database_name
  }
}

resource "aws_lakeformation_permissions" "glue_tables" {
  count       = var.lakeformation_owner == "terraform" ? 1 : 0
  principal   = local.glue_role_arn
  permissions = ["ALL"]

  table {
    database_name = local.glue_database_name
    wildcard      = true
  }
}

resource "aws_lakeformation_permissions" "glue_data_location" {
  count       = var.lakeformation_owner == "terraform" ? 1 : 0
  principal   = local.glue_role_arn
  permissions = ["DATA_LOCATION_ACCESS"]

  data_location {
    arn = "arn:aws:s3:::${var.data_lake_bucket}"
  }
}

resource "aws_lakeformation_permissions" "lambda_catalog" {
  count            = var.lakeformation_owner == "terraform" ? 1 : 0
  principal        = local.lambda_role_arn
  permissions      = ["CREATE_LF_TAG", "ALTER", "DROP"]
  catalog_resource = true
}

resource "aws_lakeformation_permissions" "lambda_database" {
  count       = var.lakeformation_owner == "terraform" ? 1 : 0
  principal   = local.lambda_role_arn
  permissions = ["DESCRIBE", "CREATE_TABLE", "ALTER"]

  database {
    name = local.glue_database_name
  }
}

resource "aws_lakeformation_permissions" "lambda_tables" {
  count       = var.lakeformation_owner == "terraform" ? 1 : 0
  principal   = local.lambda_role_arn
  permissions = ["ALL"]

  table {
    database_name = local.glue_database_name
    wildcard      = true
  }
}

resource "aws_lakeformation_permissions" "lambda_lf_tag_pii_type" {
  count       = var.lakeformation_owner == "terraform" ? 1 : 0
  principal   = local.lambda_role_arn
  permissions = ["ASSOCIATE", "DESCRIBE"]

  lf_tag {
    key    = "PII_Type"
    values = ["SSN", "EMAIL", "NAME"]
  }
}

resource "aws_lakeformation_permissions" "lambda_lf_tag_data_sensitivity" {
  count       = var.lakeformation_owner == "terraform" ? 1 : 0
  principal   = local.lambda_role_arn
  permissions = ["ASSOCIATE", "DESCRIBE"]

  lf_tag {
    key    = "Data_Sensitivity"
    values = ["CRITICAL", "HIGH"]
  }
}
