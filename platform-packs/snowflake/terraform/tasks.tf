# Mode B (7.5): Snowflake Tasks root skeleton — Gate B validate only.
resource "snowflake_schema" "pipeline" {
  database = snowflake_database.analytics.name
  name     = "PIPELINE"
}

resource "snowflake_task" "ingest_root" {
  database      = snowflake_database.analytics.name
  schema        = snowflake_schema.pipeline.name
  name          = "${var.workload}_ingest_to_bronze"
  warehouse     = var.warehouse
  sql_statement = "SELECT 1 /* Gate B placeholder; live deploy uses rendered Tasks SQL */"
  started       = false

  schedule {
    using_cron = "0 6 * * MON UTC"
  }
}
