#!/usr/bin/env python3
"""Generate .mcp.json and .cursor/mcp.json from tool-registry + local mcp-servers/."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_MCP = REPO_ROOT / "mcp-servers"
DEFAULT_OFFICIAL = REPO_ROOT.parent / "agentic-projects" / "ADOP"

CUSTOM_SCRIPT_REL = {
    "glue-athena": Path("mcp-servers/glue-athena-server/server.py"),
    "lakeformation": Path("mcp-servers/lakeformation-server/server.py"),
    "sagemaker-catalog": Path("mcp-servers/sagemaker-catalog-server/server.py"),
    "pii-detection": Path("mcp-servers/pii-detection-server/server.py"),
}

CUSTOM_SERVERS = {
    "glue-athena": {
        "args": [
            "run",
            "--no-project",
            "--with",
            "fastmcp",
            "--with",
            "boto3",
            "--python",
            "{python}",
            "{script}",
        ],
    },
    "lakeformation": {
        "args": [
            "run",
            "--no-project",
            "--with",
            "fastmcp",
            "--with",
            "boto3",
            "--python",
            "{python}",
            "{script}",
        ],
    },
    "sagemaker-catalog": {
        "args": [
            "run",
            "--no-project",
            "--with",
            "fastmcp",
            "--with",
            "boto3",
            "--python",
            "{python}",
            "{script}",
        ],
    },
    "pii-detection": {
        "args": [
            "run",
            "--no-project",
            "--with",
            "boto3",
            "--with",
            "mcp",
            "--python",
            "{python}",
            "{script}",
        ],
    },
}

PYPI_SERVERS = {
    "core": ("awslabs-core-mcp-server", "awslabs.core-mcp-server"),
    "iam": ("awslabs-iam-mcp-server", "awslabs.iam-mcp-server"),
    "lambda": ("awslabs-lambda-mcp-server", "awslabs.lambda-mcp-server"),
    "s3-tables": ("awslabs-s3-tables-mcp-server", "awslabs.s3-tables-mcp-server"),
    "cloudtrail": ("awslabs-cloudtrail-mcp-server", "awslabs.cloudtrail-mcp-server"),
    "redshift": ("awslabs-redshift-mcp-server", "awslabs.redshift-mcp-server"),
    "cloudwatch": ("awslabs-cloudwatch-mcp-server", "awslabs.cloudwatch-mcp-server"),
    "cost-explorer": ("awslabs-cost-explorer-mcp-server", "awslabs.cost-explorer-mcp-server"),
    "dynamodb": ("awslabs-dynamodb-mcp-server", "awslabs.dynamodb-mcp-server"),
}


def find_mcp_root(explicit: str | None = None) -> Path:
    """Prefer vendored mcp-servers/ in this repo; fallback to sibling ADOP clone."""
    if explicit:
        root = Path(explicit).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"MCP root not found: {root}")
        return root
    for env_key in ("ADOP_MCP_ROOT", "ADOP_OFFICIAL_ROOT"):
        env = os.environ.get(env_key)
        if env:
            return find_mcp_root(env)
    if (LOCAL_MCP / "glue-athena-server" / "server.py").is_file():
        return REPO_ROOT.resolve()
    if DEFAULT_OFFICIAL.is_dir():
        return DEFAULT_OFFICIAL.resolve()
    raise FileNotFoundError(
        "No MCP servers found. Expected vendored tree at "
        f"{LOCAL_MCP} or sibling clone at {DEFAULT_OFFICIAL}."
    )


def _env_block(region: str, profile: str) -> dict[str, str]:
    block = {
        "AWS_REGION": region,
        "AWS_PROFILE": profile,
    }
    return block


def _pypi_entry(package: str, module: str, region: str, profile: str) -> dict:
    env = _env_block(region, profile)
    env["FASTMCP_LOG_LEVEL"] = "ERROR"
    return {
        "command": "uvx",
        "args": ["--from", package, module],
        "env": env,
    }


def build_mcp_config(
    mcp_root: Path,
    *,
    region: str = "us-east-1",
    profile: str = "aws-agent",
    python_version: str = "3.12",
    use_relative_scripts: bool | None = None,
) -> dict:
    """Build mcpServers dict. Custom scripts resolve under mcp_root."""
    servers: dict[str, dict] = {}
    if use_relative_scripts is None:
        use_relative_scripts = mcp_root.resolve() == REPO_ROOT.resolve()

    for name, spec in CUSTOM_SERVERS.items():
        rel = CUSTOM_SCRIPT_REL[name]
        script_path = mcp_root / rel
        if not script_path.is_file():
            raise FileNotFoundError(f"Missing custom MCP server: {script_path}")

        if use_relative_scripts:
            try:
                script_arg = os.path.relpath(script_path, REPO_ROOT).replace("\\", "/")
            except ValueError:
                script_arg = script_path.as_posix()
        else:
            script_arg = script_path.as_posix()

        args = [a.format(python=python_version, script=script_arg) for a in spec["args"]]
        servers[name] = {
            "command": "uv",
            "args": args,
            "env": _env_block(region, profile),
        }

    for name, (package, module) in PYPI_SERVERS.items():
        servers[name] = _pypi_entry(package, module, region, profile)

    return {"mcpServers": servers}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {path.relative_to(REPO_ROOT)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--mcp-root",
        default=None,
        help="Repo root or ADOP clone containing mcp-servers/ (default: local vendored copy)",
    )
    ap.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    ap.add_argument("--profile", default=os.environ.get("AWS_PROFILE", "aws-agent"))
    ap.add_argument("--python", default="3.12", dest="python_version")
    ap.add_argument(
        "--relative-scripts",
        action="store_true",
        help="Use paths relative to this repo (default: absolute script paths)",
    )
    args = ap.parse_args(argv)

    try:
        mcp_root = find_mcp_root(args.mcp_root)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    payload = build_mcp_config(
        mcp_root,
        region=args.region,
        profile=args.profile,
        python_version=args.python_version,
        use_relative_scripts=True if args.relative_scripts else None,
    )

    write_json(REPO_ROOT / ".mcp.json", payload)
    write_json(REPO_ROOT / ".cursor" / "mcp.json", payload)
    print(f"MCP script root: {mcp_root}")
    print(f"Servers: {len(payload['mcpServers'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
