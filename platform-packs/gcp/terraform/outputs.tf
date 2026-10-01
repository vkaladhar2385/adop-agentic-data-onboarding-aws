output "gcs_bucket" {
  value = google_storage_bucket.lake.name
}

output "lake_zone_prefixes" {
  value = { for z in local.zones : z => "gs://${google_storage_bucket.lake.name}/${z}/" }
}

output "dataproc_cluster" {
  value = google_dataproc_cluster.spark.name
}
