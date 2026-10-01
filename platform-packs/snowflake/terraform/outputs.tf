output "snowflake_database" {
  value = snowflake_database.analytics.name
}

output "snowflake_iceberg_table" {
  value = "${snowflake_database.analytics.name}.${snowflake_schema.gold.name}.${snowflake_iceberg_table.gold.name}"
}
