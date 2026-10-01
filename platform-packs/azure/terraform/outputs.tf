output "resource_group" {
  value = azurerm_resource_group.this.name
}

output "storage_account" {
  value = azurerm_storage_account.lake.name
}

output "lake_zone_urls" {
  description = "abfss:// roots per zone."
  value = {
    for z in local.zones :
    z => "abfss://${z}@${azurerm_storage_account.lake.name}.dfs.core.windows.net/"
  }
}

output "synapse_workspace" {
  value = azurerm_synapse_workspace.this.name
}

output "spark_pool" {
  value = azurerm_synapse_spark_pool.this.name
}

output "data_factory" {
  value = azurerm_data_factory.this.name
}
