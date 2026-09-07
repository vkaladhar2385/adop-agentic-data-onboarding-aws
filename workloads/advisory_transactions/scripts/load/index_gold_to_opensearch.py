"""OpenSearch indexing for `advisory_transactions` Gold rows (extension).

Queries the Gold fact table via Athena, then bulk-indexes the results into an
OpenSearch domain so a support-desk UI can full-text search transactions
(the star schema is great for BI rollups but bad for "find this client's
transaction by free-text search" -- that's exactly the gap OpenSearch fills).

Uses SigV4-signed HTTPS requests via `botocore.auth` + `urllib` instead of the
`opensearch-py`/`requests` packages, so the Lambda stays stdlib + boto3/botocore
only (same lean-packaging rule as every other Lambda in this repo -- see
docs/ARCHITECTURE.md#packaging and docs/EXTENDING_TO_NEW_SERVICES.md).
"""
from __future__ import annotations

import argparse
import json
import os
import time

WORKLOAD = "advisory_transactions"
INDEX_NAME = "advisory_transactions_gold"
GOLD_QUERY = 'SELECT * FROM "{database}"."fact_transactions" LIMIT 500'


def run_local() -> None:
    print("[load] OpenSearch indexing plan:")
    print(f"  1. Athena: {GOLD_QUERY.format(database='advisory_transactions_db')}")
    print(f"  2. Bulk-index each row into OpenSearch index '{INDEX_NAME}'")
    print("  3. Support-desk UI queries: GET /advisory_transactions_gold/_search?q=client_name:Smith")


def _run_athena_query(athena, database: str, output_location: str) -> list[dict]:  # pragma: no cover - requires AWS
    qid = athena.start_query_execution(
        QueryString=GOLD_QUERY.format(database=database),
        QueryExecutionContext={"Database": database},
        ResultConfiguration={"OutputLocation": output_location},
    )["QueryExecutionId"]
    for _ in range(15):
        state = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(2)
    if state != "SUCCEEDED":
        raise RuntimeError(f"Athena query did not succeed: {state}")

    paginator = athena.get_paginator("get_query_results")
    rows: list[dict] = []
    columns: list[str] | None = None
    for page in paginator.paginate(QueryExecutionId=qid):
        for row in page["ResultSet"]["Rows"]:
            values = [d.get("VarCharValue") for d in row["Data"]]
            if columns is None:
                columns = values  # header row
                continue
            rows.append(dict(zip(columns, values)))
    return rows


def _sigv4_request(endpoint: str, region: str, method: str, path: str, body: bytes | None = None,
                   content_type: str = "application/json") -> dict:  # pragma: no cover
    import boto3
    import urllib.request
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest

    url = f"https://{endpoint}{path}"
    headers = {"Content-Type": content_type} if body is not None else {}
    request = AWSRequest(method=method, url=url, data=body, headers=headers)
    SigV4Auth(boto3.Session().get_credentials(), "es", region).add_auth(request)
    req = urllib.request.Request(url, data=body, headers=dict(request.headers), method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read() or b"{}")


def _sigv4_bulk_index(endpoint: str, region: str, index: str, rows: list[dict]) -> dict:  # pragma: no cover
    lines = []
    for i, row in enumerate(rows):
        lines.append(json.dumps({"index": {"_index": index, "_id": row.get("transaction_id", str(i))}}))
        lines.append(json.dumps(row))
    body = ("\n".join(lines) + "\n").encode("utf-8")
    return _sigv4_request(endpoint, region, "POST", "/_bulk", body, "application/x-ndjson")


def lambda_handler(event: dict, context) -> dict:  # pragma: no cover - requires AWS
    """Step Functions `IndexGoldToOpenSearch` / verifier `action=count` target."""
    database = (event or {}).get("database") or os.environ["GLUE_DATABASE"]
    endpoint = os.environ["OPENSEARCH_ENDPOINT"]
    region = os.environ.get("AWS_REGION_NAME", "us-east-1")
    output_location = os.environ["ATHENA_OUTPUT_LOCATION"]
    action = (event or {}).get("action", "index")

    if action == "count":
        result = _sigv4_request(endpoint, region, "GET", f"/{INDEX_NAME}/_count")
        count = int(result.get("count", 0))
        if count <= 0:
            raise RuntimeError(f"OpenSearch index {INDEX_NAME} is empty")
        return {"workload": WORKLOAD, "index": INDEX_NAME, "count": count}

    import boto3
    athena = boto3.client("athena")
    rows = _run_athena_query(athena, database, output_location)
    if not rows:
        raise RuntimeError("Athena returned 0 Gold rows to index")
    result = _sigv4_bulk_index(endpoint, region, INDEX_NAME, rows)
    errors = sum(1 for item in result.get("items", []) if "error" in item.get("index", {}))
    indexed = len(rows) - errors
    if indexed <= 0:
        raise RuntimeError(f"OpenSearch bulk index failed: {errors} errors / {len(rows)} rows")
    return {"workload": WORKLOAD, "indexed": indexed, "failed": errors}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()
    if args.local:
        run_local()
    else:
        raise SystemExit("OpenSearch indexing runs against AWS; use --local for the demo.")
