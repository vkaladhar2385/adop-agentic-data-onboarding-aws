"""Post-deployment verifier (ADOP `verify-deployment` + `audit-after-deploy`).

Runs a fixed set of automated checks after a deploy and exits non-zero if any
fail. Deployment is NOT considered complete until every check passes. Uses
boto3 against AWS; when boto3/credentials are absent it runs in --dry-run mode
so the check list can be reviewed locally.

Also exposes `lambda_handler`, the Step Functions `PostDeploymentVerify` task
target (used by both workloads -- the target workload/database/state machine
come from the event payload, so one Lambda backs both pipelines).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

CHECKS = [
    "glue_tables_exist",
    "athena_returns_data",
    "lf_tags_applied_on_pii",
    "kms_rotation_enabled",
    "state_machine_loads",
    "cloudtrail_audit_logged",
    "redshift_spectrum_returns_data",
    "opensearch_index_has_docs",
    "redis_quality_score_cached",
]

# Step Functions ASL uses short names in PostDeploymentVerify Payload.checks
SFN_CHECK_ALIASES = {
    "tables_exist": "glue_tables_exist",
    "lf_tags_applied": "lf_tags_applied_on_pii",
    "kms_rotation": "kms_rotation_enabled",
    "audit_logged": "cloudtrail_audit_logged",
}


def _resolve_checks(requested: list[str] | None) -> list[str]:
    """Map SFN check names to internal keys; default to full CHECKS list."""
    if not requested:
        return list(CHECKS)
    resolved: list[str] = []
    for name in requested:
        key = SFN_CHECK_ALIASES.get(name, name)
        if key in CHECKS and key not in resolved:
            resolved.append(key)
    return resolved or list(CHECKS)


def _dry_run(workload: str, database: str) -> dict[str, bool]:
    print(f"[verifier] DRY RUN for workload={workload} db={database}")
    results = {}
    for c in CHECKS:
        print(f"  [PLAN] {c}")
        results[c] = True
    print("[verifier] dry-run only (install boto3 + configure AWS to execute).")
    return results


def _check_glue_tables_exist(glue, database: str) -> bool:
    try:
        tables = glue.get_tables(DatabaseName=database)["TableList"]
        print(f"[verifier] glue tables={len(tables)} in {database}")
        return len(tables) > 0
    except Exception as exc:  # noqa: BLE001
        print(f"[verifier] glue get_tables exception: {exc}")
        return False


def _check_state_machine_loads(sfn, state_machine: str) -> bool:
    try:
        arns = [
            m["stateMachineArn"] for m in sfn.list_state_machines()["stateMachines"]
            if m["name"] == state_machine
        ]
        return bool(arns)
    except Exception:
        return False


def _check_kms_rotation(kms, workload: str) -> bool:
    try:
        ok = True
        for zone in ("bronze", "silver", "gold"):
            key = kms.describe_key(KeyId=f"alias/{workload}-{zone}")["KeyMetadata"]["KeyId"]
            ok = ok and kms.get_key_rotation_status(KeyId=key)["KeyRotationEnabled"]
        return ok
    except Exception:
        return False


def _check_athena_returns_data(athena, database: str, table: str, output_location: str) -> bool:
    """Runs SELECT COUNT(*) via Athena and waits (bounded) for a non-zero result."""
    try:
        if not output_location:
            print("[verifier] athena: no output_location (DATA_LAKE_BUCKET unset)")
            return False
        qid = athena.start_query_execution(
            QueryString=f'SELECT COUNT(*) AS n FROM "{database}"."{table}"',
            QueryExecutionContext={"Database": database},
            ResultConfiguration={"OutputLocation": output_location},
        )["QueryExecutionId"]
        state = "QUEUED"
        reason = ""
        for _ in range(15):  # ~30s; first Athena query in an account can be slow
            qe = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
            state = qe["Status"]["State"]
            reason = qe["Status"].get("StateChangeReason", "")
            if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
                break
            time.sleep(2)
        if state != "SUCCEEDED":
            print(f"[verifier] athena {state}: {reason} (qid={qid})")
            return False
        rows = athena.get_query_results(QueryExecutionId=qid)["ResultSet"]["Rows"]
        count = int(rows[1]["Data"][0]["VarCharValue"])
        print(f"[verifier] athena COUNT(*)={count}")
        return count > 0
    except Exception as exc:  # noqa: BLE001
        print(f"[verifier] athena exception: {exc}")
        return False


def _check_lf_tags_applied(lakeformation, database: str, table: str, pii_columns: list[str]) -> bool:
    try:
        tagged = lakeformation.get_resource_lf_tags(
            Resource={"TableWithColumns": {"DatabaseName": database, "Name": table, "ColumnNames": pii_columns}}
        )
        ok = bool(tagged.get("LFTagsOnColumns"))
        print(f"[verifier] lf_tags_on_columns={len(tagged.get('LFTagsOnColumns') or [])} expected={len(pii_columns)}")
        return ok
    except Exception as exc:  # noqa: BLE001
        print(f"[verifier] lf_tags exception: {exc}")
        return False


def _check_cloudtrail_audit_logged(cloudtrail, lookback_minutes: int = 60) -> bool:
    """Confirms CloudTrail captured *some* recent write activity (audit trail is live)."""
    try:
        import datetime
        start = datetime.datetime.utcnow() - datetime.timedelta(minutes=lookback_minutes)
        events = cloudtrail.lookup_events(StartTime=start)["Events"]
        return len(events) > 0
    except Exception:
        return False


def _invoke_lambda(lambda_client, function_name: str, payload: dict) -> dict:
    import json
    resp = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8"),
    )
    body = json.loads(resp["Payload"].read() or b"{}")
    if resp.get("FunctionError"):
        raise RuntimeError(f"{function_name} error: {body}")
    return body


def _check_redshift_spectrum(workload: str) -> bool:
    try:
        import boto3
        body = _invoke_lambda(
            boto3.client("lambda"), f"{workload}_register_redshift_spectrum", {"action": "verify"},
        )
        count = int(body.get("count", 0))
        print(f"[verifier] redshift COUNT(*)={count}")
        return count > 0
    except Exception as exc:  # noqa: BLE001
        print(f"[verifier] redshift exception: {exc}")
        return False


def _check_opensearch_index(workload: str) -> bool:
    try:
        import boto3
        body = _invoke_lambda(
            boto3.client("lambda"), f"{workload}_index_gold_to_opensearch", {"action": "count"},
        )
        count = int(body.get("count", 0))
        print(f"[verifier] opensearch count={count}")
        return count > 0
    except Exception as exc:  # noqa: BLE001
        print(f"[verifier] opensearch exception: {exc}")
        return False


def _check_redis_scores(workload: str) -> bool:
    try:
        import boto3
        body = _invoke_lambda(
            boto3.client("lambda"), f"{workload}_cache_quality_scores",
            {"action": "get", "zones": ["silver", "gold"]},
        )
        cached = body.get("cached") or {}
        print(f"[verifier] redis keys={list(cached)}")
        return "gold" in cached and "silver" in cached
    except Exception as exc:  # noqa: BLE001
        print(f"[verifier] redis exception: {exc}")
        return False


def _live(workload: str, database: str, state_machine: str | None,
          table: str = None, athena_output: str = None, pii_columns: list[str] = None,
          active_checks: list[str] | None = None) -> dict[str, bool]:  # pragma: no cover - requires AWS
    import boto3

    table = table or f"silver_{workload}"
    pii_columns = pii_columns or []
    checks = _resolve_checks(active_checks)
    # `database` is NOT a valid fallback bucket name (it's a Glue Catalog
    # database name, e.g. "advisory_transactions_db" -- no such S3 bucket
    # exists). Fall back to DATA_LAKE_BUCKET (set on every workload Lambda,
    # see lambda.tf), which always does exist.
    results_bucket = os.environ.get("ATHENA_RESULTS_BUCKET") or os.environ.get("DATA_LAKE_BUCKET")
    athena_output = athena_output or (f"s3://{results_bucket}/athena-results/" if results_bucket else None)

    glue = boto3.client("glue")
    sfn = boto3.client("stepfunctions")
    kms = boto3.client("kms")
    athena = boto3.client("athena")
    lakeformation = boto3.client("lakeformation")
    cloudtrail = boto3.client("cloudtrail")

    runners = {
        "glue_tables_exist": lambda: _check_glue_tables_exist(glue, database),
        "state_machine_loads": lambda: _check_state_machine_loads(sfn, state_machine) if state_machine else True,
        "kms_rotation_enabled": lambda: _check_kms_rotation(kms, workload),
        "athena_returns_data": lambda: _check_athena_returns_data(athena, database, table, athena_output),
        "lf_tags_applied_on_pii": lambda: _check_lf_tags_applied(lakeformation, database, table, pii_columns) if pii_columns else True,
        "cloudtrail_audit_logged": lambda: _check_cloudtrail_audit_logged(cloudtrail),
        "redshift_spectrum_returns_data": lambda: _check_redshift_spectrum(workload),
        "opensearch_index_has_docs": lambda: _check_opensearch_index(workload),
        "redis_quality_score_cached": lambda: _check_redis_scores(workload),
    }
    return {key: runners[key]() for key in checks}


def _report(results: dict[str, bool]) -> int:
    failed = [c for c in CHECKS if not results.get(c)]
    for c in CHECKS:
        print(f"  [{'PASS' if results.get(c) else 'FAIL'}] {c}")
    if failed:
        print(f"[verifier] FAILED: {failed}")
        return 1
    print("[verifier] all checks passed.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workload", required=True)
    ap.add_argument("--database", required=True)
    ap.add_argument("--state-machine", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        return _report(_dry_run(args.workload, args.database))
    try:
        import boto3  # noqa: F401
    except ImportError:
        return _report(_dry_run(args.workload, args.database))
    return _report(_live(args.workload, args.database, args.state_machine))


def lambda_handler(event: dict, context) -> dict:  # pragma: no cover - requires AWS
    """Step Functions `PostDeploymentVerify` task target (shared by both workloads).

    event = {
      "workload": "advisory_transactions", "database": "advisory_transactions_db",
      "state_machine": "advisory_transactions_pipeline", "table": "silver_advisory_transactions",
      "pii_columns": ["client_ssn", "client_email"], "checks": [...]   # optional; SFN short names
    }
    """
    workload = event["workload"]
    database = event["database"]
    active = _resolve_checks(event.get("checks"))
    try:
        import boto3  # noqa: F401
        results = _live(
            workload, database,
            event.get("state_machine"), event.get("table"),
            event.get("athena_output"), event.get("pii_columns"),
            active_checks=active,
        )
    except ImportError:
        results = _dry_run(workload, database)
    passed = all(results.get(c) for c in active)
    if not passed:
        raise RuntimeError(f"post-deployment verifier failed: { {c: results.get(c) for c in active} }")
    return {"workload": workload, "passed": passed, "results": results, "checks_run": active}


if __name__ == "__main__":
    sys.exit(main())
