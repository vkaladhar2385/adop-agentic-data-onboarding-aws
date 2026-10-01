terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  bucket = coalesce(var.bucket_name, "adop-${var.workload}-${var.project_id}")
  zones  = ["bronze", "silver", "gold"]
  tags   = merge({ project = "adop", workload = var.workload }, var.tags)
}

resource "google_storage_bucket" "lake" {
  name                        = local.bucket
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
  labels                      = local.tags
}

resource "google_storage_bucket_object" "zone_placeholder" {
  for_each = toset(local.zones)
  name     = "${each.value}/.keep"
  bucket   = google_storage_bucket.lake.name
  content  = "adop zone marker"
}

resource "google_dataproc_cluster" "spark" {
  name   = "adop-${var.workload}"
  region = var.region

  cluster_config {
    software_config {
      image_version = "2.2"
    }
    master_config {
      num_instances = 1
      machine_type  = "n2-standard-2"
    }
    worker_config {
      num_instances = 2
      machine_type  = "n2-standard-2"
    }
  }
}
