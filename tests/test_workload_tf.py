"""Unit tests for auto Terraform module generation (no AWS)."""

from pathlib import Path

from shared.deploy.sync_landing import resolve_landing_s3_uri
from shared.deploy.sfn_e2e import build_state_machine_input, state_machine_name
from shared.deploy.workload_tf import render_module_hcl, terraform_module_declared


def test_render_product_inventory_module_contains_glue_jobs():
    hcl = render_module_hcl("product_inventory")
    assert 'module "product_inventory"' in hcl
    assert "ingest_to_bronze" in hcl
    assert "bronze_to_silver" in hcl
    assert "product_inventory_db" in hcl
    assert "silver_product_inventory" in hcl
    assert "catalog_owner" in hcl


def test_advisory_module_declared_in_main_tf():
    assert terraform_module_declared("advisory_transactions")


def test_product_inventory_not_declared_until_generated():
    assert not terraform_module_declared("product_inventory")


def test_resolve_landing_uri_replaces_bucket_and_date():
    uri, name = resolve_landing_s3_uri(
        "product_inventory",
        "my-lake-bucket",
        repo_root=Path("."),
    )
    assert uri.startswith("s3://my-lake-bucket/landing/product_inventory/")
    assert "ingestion_date=" in uri
    assert name == "product_inventory.csv"


def test_state_machine_name_from_schedule():
    assert state_machine_name("product_inventory", repo_root=Path(".")) == "product_inventory_pipeline"


def test_sfn_input_paths():
    payload = build_state_machine_input("product_inventory", "lake-123")
    assert payload["source_path"] == "s3://lake-123/landing/product_inventory/"
