# Redshift Spectrum reads Gold Iceberg tables via the Glue Data Catalog.
# The spectrum IAM role needs LF SELECT/DESCRIBE in addition to glue:* IAM.

resource "aws_lakeformation_permissions" "spectrum_database" {
  principal   = aws_iam_role.spectrum.arn
  permissions = ["DESCRIBE"]

  database {
    name = var.glue_database
  }
}

resource "aws_lakeformation_permissions" "spectrum_tables" {
  principal   = aws_iam_role.spectrum.arn
  permissions = ["SELECT", "DESCRIBE"]

  table {
    database_name = var.glue_database
    wildcard      = true
  }
}

resource "aws_lakeformation_permissions" "spectrum_gold_location" {
  principal   = aws_iam_role.spectrum.arn
  permissions = ["DATA_LOCATION_ACCESS"]

  data_location {
    arn = "arn:aws:s3:::${var.data_lake_bucket}/gold/${var.workload}/"
  }
}
