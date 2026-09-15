"""Opt-in sink plugins (P1-3) — no AWS."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import validate_compute as vc  # noqa: E402
from package_and_sync import lambdas_for_workload  # noqa: E402

from shared.deploy.sinks import load_enabled_sinks
from shared.deploy.workload_tf import render_module_hcl, render_sink_modules_hcl


def test_factory_skus_have_sinks_off():
    assert load_enabled_sinks("supplier_lead_times") == []
    assert load_enabled_sinks("advisory_transactions") == []


def test_package_skips_sink_zips_when_disabled():
    names = set(lambdas_for_workload("advisory_transactions"))
    assert "register_catalog" in names
    assert "post_deploy_verifier" in names
    assert "register_redshift_spectrum" not in names
    assert "index_gold_to_opensearch" not in names
    assert "cache_quality_scores" not in names


def test_render_pipeline_has_empty_enabled_sinks():
    hcl = render_module_hcl("product_inventory")
    assert "enabled_sinks" in hcl
    assert 'enabled_sinks    = []' in hcl
    assert 'module "product_inventory_redshift"' not in hcl


def test_render_sink_modules_when_enabled():
    hcl = render_sink_modules_hcl("demo_sku", ["redshift", "redis"])
    assert 'module "demo_sku_redshift"' in hcl
    assert 'module "demo_sku_redis"' in hcl
    assert 'module "demo_sku_opensearch"' not in hcl
    assert "glue_database    = module.demo_sku.glue_database" in hcl


def test_sink_without_tf_module_is_error():
    issues = vc.validate_sinks(
        "demo",
        {"workload": "demo", "sinks": {"redshift": True, "opensearch": False, "redis": False}},
        tf_module_names=set(),
    )
    assert any("sink redshift is enabled" in i.message for i in issues)
