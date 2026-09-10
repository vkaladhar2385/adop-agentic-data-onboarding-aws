"""Deploy AgentCore Gateway targets from config/agentcore/gateway_targets.yaml."""

from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path
from typing import Any

import yaml

from shared.deploy.sandbox_tags import iam_tag_list, tag_iam_role, tag_lambda, tag_map

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGETS_YAML = REPO_ROOT / "config" / "agentcore" / "gateway_targets.yaml"
BUILD_DIR = REPO_ROOT / "build" / "mcp"


def load_gateway_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or TARGETS_YAML
    with manifest_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def gateway_target_names(manifest: dict[str, Any] | None = None) -> list[str]:
    m = manifest or load_gateway_manifest()
    return [t["name"] for t in m.get("targets", []) if isinstance(t, dict) and t.get("name")]


def _zip_lambda(source: Path, out_zip: Path) -> Path:
    """Zip handler at archive root; bundle shared/mcp_lambda for proxy handlers."""
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    shared_root = REPO_ROOT / "shared"
    mcp_lambda = shared_root / "mcp_lambda"
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(source, source.name)
        if not mcp_lambda.is_dir():
            return out_zip
        init_shared = shared_root / "__init__.py"
        init_mcp = mcp_lambda / "__init__.py"
        if init_shared.is_file():
            zf.write(init_shared, "shared/__init__.py")
        if init_mcp.is_file():
            zf.write(init_mcp, "shared/mcp_lambda/__init__.py")
        for fp in mcp_lambda.rglob("*.py"):
            if fp == init_mcp:
                continue
            arc = Path("shared") / "mcp_lambda" / fp.relative_to(mcp_lambda)
            zf.write(fp, str(arc).replace("\\", "/"))
    return out_zip


def _ensure_lambda_role(iam, project: str, target_name: str, policy_doc: dict) -> str:
    role_name = f"{project}-mcp-{target_name.replace('_', '-')}-role"
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
    created = False
    try:
        role = iam.get_role(RoleName=role_name)["Role"]
    except iam.exceptions.NoSuchEntityException:
        role = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description=f"MCP {target_name} Lambda execution role",
            Tags=iam_tag_list(),
        )["Role"]
        created = True
    iam.update_assume_role_policy(RoleName=role_name, PolicyDocument=json.dumps(trust))
    attached = iam.list_attached_role_policies(RoleName=role_name).get("AttachedPolicies", [])
    if not any(p.get("PolicyArn", "").endswith("AWSLambdaBasicExecutionRole") for p in attached):
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
        )
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName=f"{target_name}-mcp",
        PolicyDocument=json.dumps(policy_doc),
    )
    if created:
        time.sleep(8)
    tag_iam_role(iam, role_name)
    return role["Arn"]


def _ensure_lambda(
    lam,
    *,
    fn_name: str,
    role_arn: str,
    handler: str,
    runtime: str,
    timeout: int,
    memory: int,
    zip_path: Path,
) -> str:
    zip_bytes = zip_path.read_bytes()
    try:
        lam.get_function(FunctionName=fn_name)
        lam.update_function_code(FunctionName=fn_name, ZipFile=zip_bytes)
    except lam.exceptions.ResourceNotFoundException:
        lam.create_function(
            FunctionName=fn_name,
            Runtime=runtime,
            Role=role_arn,
            Handler=handler,
            Code={"ZipFile": zip_bytes},
            Timeout=timeout,
            MemorySize=memory,
            Tags=tag_map(),
        )
    tag_lambda(lam, fn_name)
    return fn_name


def _ensure_gateway_role(iam, project: str, lambda_arns: list[str]) -> str:
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
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "lambda:InvokeFunction",
                "Resource": lambda_arns,
            }
        ],
    }
    try:
        role = iam.get_role(RoleName=role_name)["Role"]
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName="gateway-lambda-invoke",
            PolicyDocument=json.dumps(policy),
        )
    except iam.exceptions.NoSuchEntityException:
        role = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="AgentCore Gateway MCP invoke role",
            Tags=iam_tag_list(),
        )["Role"]
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName="gateway-lambda-invoke",
            PolicyDocument=json.dumps(policy),
        )
        time.sleep(8)
    tag_iam_role(iam, role_name)
    return role["Arn"]


def _wait_gateway_ready(client, gateway_id: str, timeout: int = 120) -> None:
    for _ in range(timeout // 5):
        if client.get_gateway(gatewayIdentifier=gateway_id)["status"] == "READY":
            return
        time.sleep(5)
    raise TimeoutError(f"Gateway {gateway_id} not READY")


def _wait_target_ready(client, gateway_id: str, target_id: str, timeout: int = 90) -> None:
    for _ in range(timeout // 5):
        if client.get_gateway_target(gatewayIdentifier=gateway_id, targetId=target_id)["status"] == "READY":
            return
        time.sleep(5)
    raise TimeoutError(f"Target {target_id} not READY")


def deploy_gateway(
    *,
    profile: str | None = "aws-agent",
    region: str = "us-east-1",
    project: str = "adop",
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Deploy or update Gateway + all manifest targets. Returns metadata dict."""
    import boto3

    manifest = load_gateway_manifest(manifest_path)
    targets = manifest.get("targets") or []
    if not targets:
        raise ValueError("No targets in gateway manifest")

    session = boto3.Session(profile_name=profile, region_name=region)
    account_id = session.client("sts").get_caller_identity()["Account"]
    iam = session.client("iam")
    lam = session.client("lambda")
    gateway_client = session.client("bedrock-agentcore-control")

    lambda_arns: list[str] = []
    deployed: list[str] = []

    for target in targets:
        name = target["name"]
        lambda_cfg = target["lambda"]
        source = REPO_ROOT / lambda_cfg["source"]
        schema_path = REPO_ROOT / target["schema"]
        policy_path = REPO_ROOT / target["iam_policy"]
        if not source.is_file() or not schema_path.is_file() or not policy_path.is_file():
            raise FileNotFoundError(f"Missing files for target {name}")

        policy_doc = json.loads(policy_path.read_text(encoding="utf-8"))
        role_arn = _ensure_lambda_role(iam, project, name, policy_doc)
        zip_path = _zip_lambda(source, BUILD_DIR / f"{name}.zip")
        fn_name = f"{project}-mcp-{name.replace('_', '-')}"
        _ensure_lambda(
            lam,
            fn_name=fn_name,
            role_arn=role_arn,
            handler=lambda_cfg.get("handler", "lambda_handler.handler"),
            runtime=lambda_cfg.get("runtime", "python3.12"),
            timeout=int(lambda_cfg.get("timeout", 300)),
            memory=int(lambda_cfg.get("memory", 256)),
            zip_path=zip_path,
        )
        lambda_arns.append(f"arn:aws:lambda:{region}:{account_id}:function:{fn_name}")
        deployed.append(name)
        print(f"Lambda ready: {fn_name}")

    gateway_cfg = manifest.get("gateway") or {}
    gateway_name = f"{project}-{gateway_cfg.get('name_suffix', 'mcp-gateway')}"
    gateway_role_arn = _ensure_gateway_role(iam, project, lambda_arns)
    # IAM policy updates need a short propagation window before new Lambda ARNs are invokable.
    time.sleep(15)

    existing = gateway_client.list_gateways().get("items", [])
    gateway_id = next((g["gatewayId"] for g in existing if g.get("name") == gateway_name), None)
    if not gateway_id:
        created = gateway_client.create_gateway(
            name=gateway_name,
            description=gateway_cfg.get("description", "ADOP MCP Gateway"),
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
        print(f"Using gateway {gateway_id}")

    _wait_gateway_ready(gateway_client, gateway_id)
    gateway_url = gateway_client.get_gateway(gatewayIdentifier=gateway_id)["gatewayUrl"]
    print(f"Gateway URL: {gateway_url}")

    registered = {
        t.get("name") for t in gateway_client.list_gateway_targets(gatewayIdentifier=gateway_id).get("items", [])
    }

    for target in targets:
        name = target["name"]
        schema_path = REPO_ROOT / target["schema"]
        tools_schema = json.loads(schema_path.read_text(encoding="utf-8"))
        fn_name = f"{project}-mcp-{name.replace('_', '-')}"
        lambda_arn = f"arn:aws:lambda:{region}:{account_id}:function:{fn_name}"
        target_cfg = {
            "mcp": {
                "lambda": {
                    "lambdaArn": lambda_arn,
                    "toolSchema": {"inlinePayload": tools_schema},
                }
            }
        }
        if name in registered:
            print(f"Target already registered: {name}")
            continue
        last_err: Exception | None = None
        for attempt in range(4):
            try:
                created_target = gateway_client.create_gateway_target(
                    gatewayIdentifier=gateway_id,
                    name=name,
                    description=target.get("description", name),
                    targetConfiguration=target_cfg,
                    credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}],
                )
                _wait_target_ready(gateway_client, gateway_id, created_target["targetId"])
                print(f"Registered target: {name}")
                last_err = None
                break
            except Exception as exc:
                last_err = exc
                if "lacks permission to invoke Lambda" in str(exc) and attempt < 3:
                    print(f"  IAM propagation wait (attempt {attempt + 1}/4) for {name}...")
                    iam.put_role_policy(
                        RoleName=f"{project}-agentcore-gateway-role",
                        PolicyName="gateway-lambda-invoke",
                        PolicyDocument=json.dumps(
                            {
                                "Version": "2012-10-17",
                                "Statement": [
                                    {
                                        "Effect": "Allow",
                                        "Action": "lambda:InvokeFunction",
                                        "Resource": lambda_arns,
                                    }
                                ],
                            }
                        ),
                    )
                    time.sleep(15 * (attempt + 1))
                    continue
                raise
        if last_err:
            raise last_err

    meta = {
        "gatewayId": gateway_id,
        "gatewayUrl": gateway_url,
        "gatewayTargets": gateway_target_names(manifest),
        "accountId": account_id,
        "region": region,
        "project": project,
    }
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    (BUILD_DIR / "gateway.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta
