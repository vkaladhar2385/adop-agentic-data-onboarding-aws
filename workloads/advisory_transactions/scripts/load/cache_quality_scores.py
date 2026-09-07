"""Redis caching of quality-gate scores for `advisory_transactions` (extension).

Reads the sidecar JSON the quality Glue jobs write to
s3://<bucket>/quality-scores/advisory_transactions/<zone>.json (because Step
Functions uses ResultPath=null, Glue job output never reaches this Lambda),
SETs it in Redis, then GETs it back so a failed write is visible.

This Lambda is VPC-attached (Redis has no public endpoint). S3 access from
inside the VPC needs the Gateway VPC endpoint in redis_workload/main.tf.
"""
from __future__ import annotations

import argparse
import json
import os
import time

WORKLOAD = "advisory_transactions"
KEY_PREFIX = f"adop:{WORKLOAD}:quality"


def run_local() -> None:
    print("[load] Redis cache plan (dry-run, no VPC access from a laptop):")
    print(f"  SET {KEY_PREFIX}:silver '{{\"score\": 0.94, \"ts\": <epoch>}}'")
    print(f"  SET {KEY_PREFIX}:gold   '{{\"score\": 0.99, \"ts\": <epoch>}}'")
    print("[load] Dashboard reads these keys instead of querying Athena on every page load.")


def _client():
    import redis
    host = os.environ["REDIS_HOST"]
    port = int(os.environ.get("REDIS_PORT", "6379"))
    return redis.Redis(host=host, port=port, socket_timeout=5, decode_responses=True)


def _read_score_from_s3(bucket: str, zone: str) -> dict:
    import boto3
    key = f"quality-scores/{WORKLOAD}/{zone}.json"
    body = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
    return json.loads(body)


def lambda_handler(event: dict, context) -> dict:  # pragma: no cover - requires VPC + Redis
    """Step Functions `CacheQualityScores` / verifier `action=get` target.

    event = {"action": "cache"|"get", "zones": ["silver","gold"]}
    """
    action = (event or {}).get("action", "cache")
    zones = (event or {}).get("zones") or ["silver", "gold"]
    client = _client()

    if action == "get":
        got = {}
        for zone in zones:
            raw = client.get(f"{KEY_PREFIX}:{zone}")
            if not raw:
                raise RuntimeError(f"missing Redis key {KEY_PREFIX}:{zone}")
            got[zone] = json.loads(raw)
        return {"workload": WORKLOAD, "action": "get", "cached": got}

    bucket = os.environ["DATA_LAKE_BUCKET"]
    cached = {}
    for zone in zones:
        sidecar = _read_score_from_s3(bucket, zone)
        payload = json.dumps({
            "score": sidecar["overall_score"],
            "passed": sidecar["passed"],
            "ts": int(time.time()),
        })
        redis_key = f"{KEY_PREFIX}:{zone}"
        client.set(redis_key, payload, ex=86400)
        roundtrip = client.get(redis_key)
        if not roundtrip:
            raise RuntimeError(f"Redis SET/GET failed for {redis_key}")
        cached[zone] = json.loads(roundtrip)
    return {"workload": WORKLOAD, "action": "cache", "cached": cached}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()
    if args.local:
        run_local()
    else:
        raise SystemExit("Redis caching requires VPC access; use --local for the demo.")
