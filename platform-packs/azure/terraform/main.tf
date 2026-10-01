terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.80"
    }
  }
}

provider "azurerm" {
  features {}
}

locals {
  rg_name   = coalesce(var.resource_group_name, "rg-adop-${var.workload}")
  sa_name   = coalesce(var.storage_account_name, substr(replace("adop${var.workload}", "_", ""), 0, 24))
  base_tags = merge({ project = "adop", workload = var.workload, lake_format = var.lake_format }, var.tags)
  zones     = ["bronze", "silver", "gold"]
}

resource "azurerm_resource_group" "this" {
  name     = local.rg_name
  location = var.location
  tags     = local.base_tags
}

# ADLS Gen2 (hierarchical namespace) for Bronze/Silver/Gold zones.
resource "azurerm_storage_account" "lake" {
  name                     = local.sa_name
  resource_group_name      = azurerm_resource_group.this.name
  location                 = azurerm_resource_group.this.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  is_hns_enabled           = true
  min_tls_version          = "TLS1_2"
  tags                     = local.base_tags
}

resource "azurerm_storage_data_lake_gen2_filesystem" "zone" {
  for_each           = toset(local.zones)
  name               = each.value
  storage_account_id = azurerm_storage_account.lake.id
}

# Synapse workspace + Spark pool for Iceberg transforms.
resource "azurerm_synapse_workspace" "this" {
  name                                 = "syn-adop-${var.workload}"
  resource_group_name                  = azurerm_resource_group.this.name
  location                             = azurerm_resource_group.this.location
  storage_data_lake_gen2_filesystem_id = azurerm_storage_data_lake_gen2_filesystem.zone["silver"].id
  managed_virtual_network_enabled      = true
  identity { type = "SystemAssigned" }
  tags = local.base_tags
}

resource "azurerm_synapse_spark_pool" "this" {
  name                 = "sparkadop"
  synapse_workspace_id = azurerm_synapse_workspace.this.id
  node_size_family     = "MemoryOptimized"
  node_size            = "Small"
  spark_version        = "3.4"
  auto_scale {
    max_node_count = 3
    min_node_count = 3
  }
  auto_pause {
    delay_in_minutes = 15
  }
  tags = local.base_tags
}

# Azure Data Factory to orchestrate the medallion pipeline.
resource "azurerm_data_factory" "this" {
  name                = "adf-adop-${var.workload}"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  identity { type = "SystemAssigned" }
  tags = local.base_tags
}
