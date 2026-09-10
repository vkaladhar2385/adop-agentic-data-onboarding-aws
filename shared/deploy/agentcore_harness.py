"""Deploy and invoke AgentCore Harness (Mode C1) wired to ADOP Gateway."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

from shared.deploy.sandbox_tags import iam_tag_list, tag_iam_role, tag_map

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_YAML = REPO_ROOT / "config" / "agentcore" / "harness.yaml"
GATEWAY_META = REPO_ROOT / "build" / "mcp" / "gateway.json"
HARNESS_META = REPO_ROOT / "build" / "agentcore" / "harness.json"


def _merge_tags(*maps: dict[str, str]) -> dict[str, str]:
    """Merge tag dicts; later values win; keys deduped case-insensitively."""
    merged: dict[str, str] = {}
    lower_to_key: dict[str, str] = {}
    for m in maps:
        for k, v in (m or {}).items():
            lk = str(k).lower()
            if lk in lower_to_key:
                merged[lower_to_key[lk]] = str(v)
            else:
                lower_to_key[lk] = str(k)
                merged[str(k)] = str(v)
    return merged


def load_harness_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or HARNESS_YAML
    with cfg_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("harness") or {}


def load_gateway_meta(path: Path | None = None) -> dict[str, Any]:
    meta_path = path or GATEWAY_META
    if not meta_path.is_file():
        raise FileNotFoundError(
            f"Missing {meta_path} — run tools/deploy_mcp_gateway.py first"
        )
    return json.loads(meta_path.read_text(encoding="utf-8"))


def gateway_arn(meta: dict[str, Any]) -> str:
    region = meta["region"]
    account = meta["accountId"]
    gateway_id = meta["gatewayId"]
    return f"arn:aws:bedrock-agentcore:{region}:{account}:gateway/{gateway_id}"


def build_system_prompt(harness_cfg: dict[str, Any], *, repo_root: Path | None = None) -> list[dict[str, str]]:
    root = repo_root or REPO_ROOT
    parts: list[str] = []
    max_chars = int(harness_cfg.get("system_prompt_max_chars") or 120_000)
    for rel in harness_cfg.get("system_prompt_files") or []:
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").strip()
        parts.append(f"## Source: {rel}\n\n{text}")
    combined = "\n\n---\n\n".join(parts) if parts else "You are the ADOP data onboarding agent."
    if len(combined) > max_chars:
        combined = combined[: max_chars - 80] + "\n\n[... truncated for Harness systemPrompt limit ...]"
    return [{"text": combined}]


def build_create_harness_request(
    harness_cfg: dict[str, Any],
    *,
    execution_role_arn: str,
    gateway_meta: dict[str, Any],
    repo_root: Path | None = None,
) -> dict[str, Any]:
    model_cfg = harness_cfg.get("model") or {}
    limits = harness_cfg.get("limits") or {}
    gw_arn = gateway_arn(gateway_meta)

    req: dict[str, Any] = {
        "harnessName": harness_cfg["name"],
        "executionRoleArn": execution_role_arn,
        "systemPrompt": build_system_prompt(harness_cfg, repo_root=repo_root),
        "model": {
            "bedrockModelConfig": {
                "modelId": model_cfg.get("model_id", "anthropic.claude-sonnet-4-20250514-v1:0"),
                "maxTokens": int(model_cfg.get("max_tokens", 8192)),
                "temperature": float(model_cfg.get("temperature", 0.2)),
                "apiFormat": model_cfg.get("api_format", "converse_stream"),
            }
        },
        "tools": [
            {
                "type": "agentcore_gateway",
                "name": "adop_gateway",
                "config": {"agentCoreGateway": {"gatewayArn": gw_arn}},
            }
        ],
        "maxIterations": int(limits.get("max_iterations", 25)),
        "maxTokens": int(limits.get("max_tokens", 8192)),
        "timeoutSeconds": int(limits.get("timeout_seconds", 900)),
        "tags": _merge_tags(tag_map(), harness_cfg.get("tags") or {}),
    }

    memory = harness_cfg.get("memory") or {}
    if memory.get("mode") == "disabled":
        req["memory"] = {"disabled": {}}

    return req


def _ensure_execution_role(
    iam,
    *,
    project: str,
    account_id: str,
    region: str,
    gateway_meta: dict[str, Any],
    model_id: str,
) -> str:
    role_name = f"{project}-agentcore-harness-role"
    gw_arn = gateway_arn(gateway_meta)
    # Runtime trust policy — SourceArn must be account-wide * (not harness/* only) for create-time validation.
    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AssumeRolePolicy",
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": account_id},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{region}:{account_id}:*"
                    },
                },
            }
        ],
    }
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "BedrockInvoke",
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:Converse",
                    "bedrock:ConverseStream",
                ],
                "Resource": [
                    "arn:aws:bedrock:*::foundation-model/*",
                    f"arn:aws:bedrock:*:{account_id}:inference-profile/*",
                    f"arn:aws:bedrock:*:{account_id}:*",
                ],
            },
            {
                "Sid": "BedrockMarketplace",
                "Effect": "Allow",
                "Action": [
                    "aws-marketplace:ViewSubscriptions",
                    "aws-marketplace:Subscribe",
                ],
                "Resource": "*",
            },
            {
                "Sid": "AgentCoreGateway",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:InvokeGateway",
                    "bedrock-agentcore:ListGatewayTargets",
                    "bedrock-agentcore:GetGateway",
                ],
                "Resource": [gw_arn, f"{gw_arn}/*"],
            },
            {
                "Sid": "EcrPublicPull",
                "Effect": "Allow",
                "Action": ["ecr-public:GetAuthorizationToken", "sts:GetServiceBearerToken"],
                "Resource": "*",
            },
            {
                "Sid": "CloudWatchLogs",
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams",
                    "logs:PutResourcePolicy",
                ],
                "Resource": [
                    f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/*",
                    f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/*:log-stream:*",
                    f"arn:aws:logs:{region}:{account_id}:log-group:*",
                ],
            },
            {
                "Sid": "XRay",
                "Effect": "Allow",
                "Action": [
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "xray:GetSamplingRules",
                    "xray:GetSamplingTargets",
                ],
                "Resource": "*",
            },
        ],
    }
    try:
        role = iam.get_role(RoleName=role_name)["Role"]
        iam.update_assume_role_policy(RoleName=role_name, PolicyDocument=json.dumps(trust))
    except iam.exceptions.NoSuchEntityException:
        role = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="AgentCore Harness execution role for ADOP onboarding agent",
            Tags=iam_tag_list(),
        )["Role"]
        time.sleep(8)
    tag_iam_role(iam, role_name)
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName="adop-harness-execution",
        PolicyDocument=json.dumps(policy),
    )
    return role["Arn"]


def _find_harness_by_name(client, name: str) -> dict[str, Any] | None:
    for page in client.get_paginator("list_harnesses").paginate():
        for item in page.get("harnesses", []):
            if item.get("harnessName") == name:
                return item
    return None


def _wait_harness_ready(client, harness_id: str, timeout: int = 600) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        harness = client.get_harness(harnessId=harness_id)["harness"]
        status = harness.get("status")
        print(f"  harness status={status}", flush=True)
        if status == "READY":
            return harness
        if status in ("CREATE_FAILED", "UPDATE_FAILED", "DELETE_FAILED"):
            reason = harness.get("failureReason", "unknown")
            raise RuntimeError(f"Harness {harness_id} failed: {status} — {reason}")
        time.sleep(10)
    raise TimeoutError(f"Harness {harness_id} not READY within {timeout}s")


def deploy_harness(
    *,
    profile: str | None = "aws-agent",
    region: str = "us-east-1",
    project: str = "adop",
    harness_cfg: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    import boto3

    cfg = harness_cfg or load_harness_config()
    gateway_meta = load_gateway_meta()
    if gateway_meta.get("region") != region:
        region = gateway_meta.get("region", region)

    req = build_create_harness_request(
        cfg,
        execution_role_arn="arn:aws:iam::PLACEHOLDER:role/placeholder",
        gateway_meta=gateway_meta,
    )

    if dry_run:
        return {"dry_run": True, "request": req, "gateway_arn": gateway_arn(gateway_meta)}

    session = boto3.Session(profile_name=profile, region_name=region)
    account_id = session.client("sts").get_caller_identity()["Account"]
    iam = session.client("iam")
    control = session.client("bedrock-agentcore-control")

    model_id = (cfg.get("model") or {}).get("model_id", "anthropic.claude-sonnet-4-20250514-v1:0")
    role_arn = _ensure_execution_role(
        iam,
        project=project,
        account_id=account_id,
        region=region,
        gateway_meta=gateway_meta,
        model_id=model_id,
    )
    req = build_create_harness_request(cfg, execution_role_arn=role_arn, gateway_meta=gateway_meta)

    existing = _find_harness_by_name(control, cfg["name"])
    if existing and existing.get("status") in ("CREATE_FAILED", "UPDATE_FAILED", "DELETE_FAILED"):
        failed_id = existing["harnessId"]
        print(f"Deleting failed harness {failed_id} ({existing.get('status')})")
        control.delete_harness(harnessId=failed_id)
        for _ in range(30):
            try:
                st = control.get_harness(harnessId=failed_id)["harness"].get("status")
                if st == "DELETED":
                    break
            except Exception:
                break
            time.sleep(5)
        existing = None

    if existing:
        harness_id = existing["harnessId"]
        print(f"Updating harness {cfg['name']} ({harness_id})")
        skip = {"harnessName", "tags", "memory"}
        update_req = {k: v for k, v in req.items() if k not in skip}
        control.update_harness(harnessId=harness_id, **update_req)
        harness = _wait_harness_ready(control, harness_id)
    else:
        print(f"Creating harness {cfg['name']}")
        resp = control.create_harness(**req)
        harness_id = resp["harness"]["harnessId"]
        harness = _wait_harness_ready(control, harness_id)

    meta = {
        "harnessId": harness["harnessId"],
        "harnessName": harness["harnessName"],
        "harnessArn": harness["arn"],
        "status": harness["status"],
        "gatewayArn": gateway_arn(gateway_meta),
        "region": region,
        "accountId": account_id,
    }
    HARNESS_META.parent.mkdir(parents=True, exist_ok=True)
    HARNESS_META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"Harness READY: {meta['harnessArn']}")
    print(f"Metadata: {HARNESS_META}")
    return meta


def invoke_harness(
    prompt: str,
    *,
    profile: str | None = "aws-agent",
    region: str | None = None,
    session_id: str | None = None,
    harness_meta: dict[str, Any] | None = None,
) -> str:
    import boto3

    meta = harness_meta or json.loads(HARNESS_META.read_text(encoding="utf-8"))
    region = region or meta["region"]
    session = boto3.Session(profile_name=profile, region_name=region)
    client = session.client("bedrock-agentcore")

    runtime_session_id = session_id or f"adop-session-{uuid.uuid4()}"
    if len(runtime_session_id) < 33:
        runtime_session_id = runtime_session_id + "-padding-to-33-chars"

    response = client.invoke_harness(
        harnessArn=meta["harnessArn"],
        runtimeSessionId=runtime_session_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
    )

    chunks: list[str] = []
    for event in response.get("stream", []):
        if "contentBlockDelta" in event:
            delta = event["contentBlockDelta"].get("delta", {})
            if "text" in delta:
                chunks.append(delta["text"])
        if "validationException" in event:
            raise RuntimeError(event["validationException"].get("message", str(event)))
        if "internalServerException" in event:
            raise RuntimeError(event["internalServerException"].get("message", str(event)))
    return "".join(chunks)
