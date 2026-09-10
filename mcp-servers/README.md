# MCP custom servers (self-contained)

Custom MCP server scripts vendored from official ADOP for Track A. PyPI-backed servers
(iam, core, cloudtrail, etc.) are installed via `uvx` at runtime — see
`tool-registry/servers.yaml`.

**Gateway Lambdas:** `gateway-lambdas/` holds thin Lambda handlers for AgentCore Gateway
(PyPI proxies + shared dispatch). Custom servers use `*-server/lambda_handler.py`.
Manifest: `config/agentcore/gateway_targets.yaml` (**14 targets** — 13 registry + `factory`).

**Regenerate Cursor/Claude MCP config after path changes:**

```powershell
python tools/generate_mcp_config.py
python tools/mcp_health_check.py --skip-aws
```

**Deploy Gateway targets:**

```powershell
python tools/deploy_mcp_gateway.py --profile aws-agent --region us-east-1
python tools/switch_mcp_mode.py --mode gateway --aws-profile aws-agent
```

**Provenance:** copied from `aws-samples/sample-Agentic-Ai-Data-Operations` (sibling
`../agentic-projects/ADOP`). Re-sync when upstream custom servers change.
