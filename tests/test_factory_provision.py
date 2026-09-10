"""Unit tests for Option B factory provision contract."""

from __future__ import annotations

import pytest

from shared.deploy.factory_provision import (
    build_factory_input,
    validate_request,
)


def test_validate_rejects_missing_approve():
    errors = validate_request(
        {"workload": "supplier_lead_times", "bucket": "my-lake-bucket", "approve": False}
    )
    assert errors  # jsonschema const:true or custom gate


def test_validate_rejects_unknown_workload():
    errors = validate_request(
        {"workload": "not_a_real_workload", "bucket": "my-lake-bucket", "approve": True}
    )
    assert errors


def test_validate_accepts_supplier_lead_times():
    errors = validate_request(
        {
            "workload": "supplier_lead_times",
            "bucket": "adop-datalake-199064440913-us-east-1",
            "approve": True,
        }
    )
    assert errors == []


def test_build_factory_input_includes_provision_id():
    body = build_factory_input(
        {"workload": "supplier_lead_times", "bucket": "my-lake", "approve": True}
    )
    assert body["workload"] == "supplier_lead_times"
    assert body["provision_id"].startswith("factory-")
    assert body["run_e2e"] is True
