# Deploy AgentCore cloud agent (Mode C)

Track A uses **AgentCore Harness first** (C1), not classic Bedrock Agents.

## C1 — Harness + Gateway (recommended)

```powershell
python tools/deploy_mcp_gateway.py --profile aws-agent
python tools/deploy_agentcore_harness.py --profile aws-agent
python tools/invoke_agentcore_harness.py --prompt "List Glue databases"
```

Full runbook: **`docs/MODE_C1_HARNESS.md`**

Official ADOP `03-deploy-agentcore-runtime.md` describes classic `bedrock-agent` APIs — **do not use for new work**. AWS recommends AgentCore Harness or AgentCore Runtime container.

## C2 — Runtime container (later)

Custom ARM64 Docker agent with `/invocations` + `/ping`. Analyze after C1 is stable.
See AWS: [Get started without the AgentCore CLI](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/getting-started-custom.html).
