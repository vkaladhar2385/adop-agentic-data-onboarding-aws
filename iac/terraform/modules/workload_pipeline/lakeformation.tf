# Lake Formation grants for Glue ETL (Iceberg writes) and zone S3 paths.
# IAM alone is insufficient when LF is enabled on the account catalog.

resource "aws_lakeformation_permissions" "glue_database" {
  principal   = aws_iam_role.glue.arn
  permissions = ["CREATE_TABLE", "ALTER", "DROP", "DESCRIBE"]

  database {
    name = aws_glue_catalog_database.db.name
  }
}

resource "aws_lakeformation_permissions" "glue_tables" {
  principal   = aws_iam_role.glue.arn
  permissions = ["ALL"]

  table {
    database_name = aws_glue_catalog_database.db.name
    wildcard      = true
  }
}

resource "aws_lakeformation_permissions" "glue_data_location" {
  principal   = aws_iam_role.glue.arn
  permissions = ["DATA_LOCATION_ACCESS"]

  data_location {
    arn = "arn:aws:s3:::${var.data_lake_bucket}"
  }
}
