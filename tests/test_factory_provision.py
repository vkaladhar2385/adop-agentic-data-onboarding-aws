"""Unit tests for Option B factory provision contract."""

from __future__ import annotations

import pytest

from unittest.mock import MagicMock, patch

from shared.deploy.factory_provision import (
    build_audit_record,
    build_factory_input,
    factory_execution_arn,
    provision_audit_s3_uri,
    validate_request,
    write_provision_audit,
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


def test_provision_audit_s3_uri():
    uri = provision_audit_s3_uri("my-lake", "factory-abc123")
    assert uri == "s3://my-lake/provision-runs/factory-abc123.json"


def test_factory_execution_arn_from_state_machine_arn():
    sm = "arn:aws:states:us-east-1:199064440913:stateMachine:adop_factory_provision"
    arn = factory_execution_arn(sm, "supplier_lead_times-factory-abc")
    assert arn == (
        "arn:aws:states:us-east-1:199064440913:execution:"
        "adop_factory_provision:supplier_lead_times-factory-abc"
    )


def test_build_audit_record_includes_pipeline_and_codebuild():
    record = build_audit_record(
        status="SUCCEEDED",
        workload="supplier_lead_times",
        bucket="my-lake",
        provision_id="factory-deadbeef",
        run_e2e=True,
        factory_execution_arn="arn:aws:states:us-east-1:1:execution:sm:exec",
        codebuild={"Build": {"id": "b1", "buildStatus": "SUCCEEDED", "projectName": "adop-factory-dev"}},
        pipeline_e2e={"status": "SUCCEEDED", "execution_arn": "arn:execution:pipeline:run"},
    )
    assert record["audit_s3_uri"] == "s3://my-lake/provision-runs/factory-deadbeef.json"
    assert record["codebuild"]["status"] == "SUCCEEDED"
    assert record["pipeline_e2e"]["status"] == "SUCCEEDED"


@patch("boto3.Session")
def test_write_provision_audit_puts_json(mock_session):
    s3 = MagicMock()
    mock_session.return_value.client.return_value = s3
    record = build_audit_record(
        status="SUCCEEDED",
        workload="supplier_lead_times",
        bucket="my-lake",
        provision_id="factory-deadbeef",
        run_e2e=True,
    )
    uri = write_provision_audit(record)
    assert uri == "s3://my-lake/provision-runs/factory-deadbeef.json"
    s3.put_object.assert_called_once()
    kwargs = s3.put_object.call_args.kwargs
    assert kwargs["Bucket"] == "my-lake"
    assert kwargs["Key"] == "provision-runs/factory-deadbeef.json"
    assert kwargs["ContentType"] == "application/json"
