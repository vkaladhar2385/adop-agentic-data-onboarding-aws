"""Redshift Spectrum registration for `advisory_transactions` (extension).

Creates (or refreshes) an external schema over the Glue Data Catalog, then
runs SELECT COUNT(*) on gold_spectrum.fact_transactions so a failed Spectrum
link fails the Step Functions state.
"""
from __future__ import annotations

import argparse
import os
import time

WORKLOAD = "advisory_transactions"
EXTERNAL_SCHEMA = "gold_spectrum"


def build_statement(glue_database: str, iam_role_arn: str, aws_region: str) -> str:
    return (
        f"CREATE EXTERNAL SCHEMA IF NOT EXISTS {EXTERNAL_SCHEMA} "
        f"FROM DATA CATALOG DATABASE '{glue_database}' "
        f"IAM_ROLE '{iam_role_arn}' REGION '{aws_region}';"
    )


def run_local() -> None:
    stmt = build_statement(
        glue_database="advisory_transactions_db",
        iam_role_arn="<spectrum_role_arn -- from terraform output spectrum_role_arn>",
        aws_region="us-east-1",
    )
    print("[load] Redshift Spectrum external schema plan:")
    print(f"  {stmt}")
    print(f"[load] Once applied, BI tools query: SELECT * FROM {EXTERNAL_SCHEMA}.fact_transactions;")


def _wait(client, statement_id: str, attempts: int = 40) -> dict:  # pragma: no cover
    """Poll redshift-data until FINISHED/FAILED. Serverless workgroups can
    take a minute to resume from 0 RPU, so this is intentionally generous."""
    for _ in range(attempts):
        desc = client.describe_statement(Id=statement_id)
        status = desc["Status"]
        if status in ("FINISHED", "FAILED", "ABORTED"):
            return desc
        time.sleep(3)
    raise TimeoutError(f"Redshift statement {statement_id} still {desc.get('Status')} after {attempts * 3}s")


def apply_via_data_api(workgroup: str, database: str, statement: str, secret_arn: str) -> dict:  # pragma: no cover
    import boto3
    client = boto3.client("redshift-data")
    resp = client.execute_statement(
        WorkgroupName=workgroup, Database=database, Sql=statement, SecretArn=secret_arn,
    )
    desc = _wait(client, resp["Id"])
    if desc["Status"] != "FINISHED":
        raise RuntimeError(f"Redshift SQL failed: {desc.get('Error')} sql={statement[:120]}")
    return desc


def lambda_handler(event: dict, context) -> dict:  # pragma: no cover - requires AWS
    """Step Functions `RegisterRedshiftSpectrum` target.

    event = {"action": "register"|"verify"}  (default register = schema + COUNT)
    """
    workgroup = os.environ["WORKGROUP_NAME"]
    database = os.environ.get("DATABASE_NAME", "dev")
    glue_database = (event or {}).get("glue_database") or os.environ["GLUE_DATABASE"]
    iam_role_arn = os.environ["IAM_ROLE_ARN"]
    aws_region = os.environ.get("AWS_REGION", "us-east-1")
    secret_arn = os.environ["SECRET_ARN"]
    action = (event or {}).get("action", "register")

    import boto3
    client = boto3.client("redshift-data")

    if action != "verify":
        stmt = build_statement(glue_database, iam_role_arn, aws_region)
        apply_via_data_api(workgroup, database, stmt, secret_arn)

    count_sql = f"SELECT COUNT(*) FROM {EXTERNAL_SCHEMA}.fact_transactions;"
    desc = apply_via_data_api(workgroup, database, count_sql, secret_arn)
    result = client.get_statement_result(Id=desc["Id"])
    count = int(result["Records"][0][0].get("longValue") or result["Records"][0][0].get("stringValue") or 0)
    if count <= 0:
        raise RuntimeError(f"{EXTERNAL_SCHEMA}.fact_transactions returned COUNT={count}")
    return {"workload": WORKLOAD, "schema": EXTERNAL_SCHEMA, "count": count, "status": "ok"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()
    if args.local:
        run_local()
    else:
        raise SystemExit("Redshift registration runs against AWS; use --local for the demo.")
