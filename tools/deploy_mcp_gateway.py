#!/usr/bin/env python3
"""Deploy glue-athena MCP Lambda + AgentCore Gateway (Tier B step 13).

Minimum viable Gateway: one Lambda target (glue-athena). Other custom MCP servers
remain local stdio until Lambda handlers are added.

Usage:
  python tools/deploy_mcp_gateway.py --profile aws-agent --region us-east-1
  python tools/deploy_mcp_gateway.py --profile aws-agent --region us-east-1 --project adop
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SRC = (
    REPO_ROOT.parent
    / "agentic-projects"
    / "ADOP"
    / "prompts"
    / "environment-setup-agent"
    / "agentcore"
    / "gateway"
    / "schemas"
    / "glue-athena-tools.json"
)
LAMBDA_SRC = REPO_ROOT / "mcp-servers" / "glue-athena-server" / "lambda_handler.py"
BUILD_ZIP = REPO_ROOT / "build" / "mcp" / "glue-athena.zip"


def _session(profile: str | None, region: str):
    import boto3

    return boto3.Session(profile_name=profile, region_name=region)


def _account_id(session) -> str:
    return session.client("sts").get_caller_identity()["Account"]


def _zip_lambda() -> Path:
    BUILD_ZIP.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(BUILD_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(LAMBDA_SRC, "lambda_handler.py")
    return BUILD_ZIP


def _ensure_lambda_role(iam, project: str, account_id: str, region: str) -> str:
    role_name = f"{project}-mcp-glue-athena-role"
    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
    try:
        role = iam.get_role(RoleName=role_name)["Role"]
    except iam.exceptions.NoSuchEntityException:
        role = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="MCP glue-athena Lambda execution role",
        )["Role"]
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
        )
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "glue:GetDatabase",
                        "glue:GetDatabases",
                        "glue:GetTable",
                        "glue:GetTables",
                        "glue:CreateDatabase",
                        "athena:StartQueryExecution",
                        "athena:GetQueryExecution",
                        "athena:GetQueryResults",
                        "s3:GetObject",
                        "s3:ListBucket",
                        "s3:PutObject",
                    ],
                    "Resource": "*",
                }
            ],
        }
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName="glue-athena-mcp",
            PolicyDocument=json.dumps(policy),
        )
        time.sleep(10)
    return role["Arn"]


def _ensure_lambda(session, project: str, role_arn: str, zip_path: Path) -> str:
    lam = session.client("lambda")
    fn_name = f"{project}-mcp-glue-athena"
    with zip_path.open("rb") as fh:
        zip_bytes = fh.read()
    try:
        lam.get_function(FunctionName=fn_name)
        lam.update_function_code(FunctionName=fn_name, ZipFile=zip_bytes)
        print(f"Updated Lambda {fn_name}")
    except lam.exceptions.ResourceNotFoundException:
        lam.create_function(
            FunctionName=fn_name,
            Runtime="python3.12",
            Role=role_arn,
            Handler="lambda_handler.handler",
            Code={"ZipFile": zip_bytes},
            Timeout=300,
            MemorySize=256,
        )
        print(f"Created Lambda {fn_name}")
    return fn_name


def _ensure_gateway_role(iam, project: str, account_id: str, region: str, lambda_name: str) -> str:
    role_name = f"{project}-agentcore-gateway-role"
    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
    try:
        role = iam.get_role(RoleName=role_name)["Role"]
    except iam.exceptions.NoSuchEntityException:
        role = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="AgentCore Gateway MCP invoke role",
        )["Role"]
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "lambda:InvokeFunction",
                    "Resource": f"arn:aws:lambda:{region}:{account_id}:function:{lambda_name}",
                }
            ],
        }
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName="gateway-lambda-invoke",
            PolicyDocument=json.dumps(policy),
        )
        time.sleep(10)
    return role["Arn"]


def _wait_gateway_ready(client, gateway_id: str, timeout: int = 120) -> None:
    for _ in range(timeout // 5):
        status = client.get_gateway(gatewayIdentifier=gateway_id)["status"]
        if status == "READY":
            return
        time.sleep(5)
    raise TimeoutError(f"Gateway {gateway_id} not READY after {timeout}s")


def _wait_target_ready(client, gateway_id: str, target_id: str, timeout: int = 60) -> None:
    for _ in range(timeout // 5):
        status = client.get_gateway_target(gatewayIdentifier=gateway_id, targetId=target_id)["status"]
        if status == "READY":
            return
        time.sleep(5)
    raise TimeoutError(f"Target {target_id} not READY after {timeout}s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="aws-agent")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--project", default="adop")
    args = ap.parse_args()

    if not LAMBDA_SRC.is_file():
        print(f"error: missing {LAMBDA_SRC}", file=sys.stderr)
        return 1
    if not SCHEMA_SRC.is_file():
        print(f"error: missing schema {SCHEMA_SRC}", file=sys.stderr)
        return 1

    session = _session(args.profile, args.region)
    account_id = _account_id(session)
    iam = session.client("iam")
    gateway_client = session.client("bedrock-agentcore-control")

    zip_path = _zip_lambda()
    lambda_role_arn = _ensure_lambda_role(iam, args.project, account_id, args.region)
    lambda_name = _ensure_lambda(session, args.project, lambda_role_arn, zip_path)
    gateway_role_arn = _ensure_gateway_role(
        iam, args.project, account_id, args.region, lambda_name
    )

    gateway_name = f"{args.project}-mcp-gateway"
    existing = gateway_client.list_gateways().get("items", [])
    gateway_id = next((g["gatewayId"] for g in existing if g.get("name") == gateway_name), None)

    if not gateway_id:
        created = gateway_client.create_gateway(
            name=gateway_name,
            description="MCP Gateway for ADOP Track B",
            protocolType="MCP",
            protocolConfiguration={
                "mcp": {"supportedVersions": ["2025-11-25"], "searchType": "SEMANTIC"}
            },
            authorizerType="AWS_IAM",
            roleArn=gateway_role_arn,
        )
        gateway_id = created["gatewayId"]
        print(f"Created gateway {gateway_id}")
    else:
        print(f"Using existing gateway {gateway_id}")

    _wait_gateway_ready(gateway_client, gateway_id)
    gateway_url = gateway_client.get_gateway(gatewayIdentifier=gateway_id)["gatewayUrl"]
    print(f"Gateway URL: {gateway_url}")

    tools_schema = json.loads(SCHEMA_SRC.read_text(encoding="utf-8"))
    lambda_arn = f"arn:aws:lambda:{args.region}:{account_id}:function:{lambda_name}"
    target_cfg = {
        "mcp": {
            "lambda": {
                "lambdaArn": lambda_arn,
                "toolSchema": {"inlinePayload": tools_schema},
            }
        }
    }

    targets = gateway_client.list_gateway_targets(gatewayIdentifier=gateway_id).get("items", [])
    if not any(t.get("name") == "glue-athena" for t in targets):
        target = gateway_client.create_gateway_target(
            gatewayIdentifier=gateway_id,
            name="glue-athena",
            description="Glue catalog and Athena query operations",
            targetConfiguration=target_cfg,
            credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}],
        )
        _wait_target_ready(gateway_client, gateway_id, target["targetId"])
        print("Registered target glue-athena")
    else:
        print("Target glue-athena already registered")

    out_path = REPO_ROOT / ".mcp.gateway.json"
    payload = {
        "mcpServers": {
            "agentcore-gateway": {
                "url": gateway_url,
                "transport": "sse",
                "auth": {
                    "type": "aws-sigv4",
                    "service": "bedrock-agentcore",
                    "region": args.region,
                },
            }
        }
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")

    meta = REPO_ROOT / "build" / "mcp" / "gateway.json"
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(
        json.dumps(
            {
                "gatewayId": gateway_id,
                "gatewayUrl": gateway_url,
                "lambdaName": lambda_name,
                "accountId": account_id,
                "region": args.region,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Metadata: {meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
