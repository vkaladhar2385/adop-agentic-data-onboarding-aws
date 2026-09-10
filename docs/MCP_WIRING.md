# MCP wiring — official 13 servers on Track A

Custom MCP server scripts are **vendored in this repo** under `mcp-servers/`. PyPI-backed
servers (iam, core, cloudtrail, etc.) install via `uvx` at runtime.

Fallback: set `ADOP_MCP_ROOT` or `ADOP_OFFICIAL_ROOT` to a sibling ADOP clone if you replace
the vendored tree.

---

## Prerequisites

1. **Vendored tree present** — `mcp-servers/glue-athena-server/server.py` (copied from official ADOP).

2. **Install [uv](https://docs.astral.sh/uv/)** — required for custom + PyPI MCP servers.

3. **AWS credentials** — sandbox profile (default in generated config: `aws-agent`):

   ```powershell
   aws login --profile aws-agent
   aws sts get-caller-identity --profile aws-agent
   ```

4. Override paths or profile:

   ```powershell
   $env:ADOP_OFFICIAL_ROOT = "C:\path\to\official\ADOP"
   $env:AWS_PROFILE = "aws-agent"
   $env:AWS_REGION = "us-east-1"
   ```

---

## One-time setup

From this repo root:

```powershell
python tools/generate_mcp_config.py
python tools/validate_mcp_registry.py
python tools/mcp_health_check.py
```

This writes:

| File | Host |
|---|---|
| `.mcp.json` | Claude Code |
| `.cursor/mcp.json` | Cursor project MCP |

Both list **13 servers** matching `tool-registry/servers.yaml`.

---

## Enable in Cursor

1. Open **Cursor Settings → MCP** (or reload after saving `.cursor/mcp.json`).
2. Confirm all 13 servers show connected (slow starters: `core`, `pii-detection`, `sagemaker-catalog` may take 5–10s).
3. Keep optional `user-aws-mcp` for docs — **Phase 5 deploy uses the official 13**, not the proxy.

---

## Sandbox lifecycle (provision / destroy)

From repo root on your laptop:

```powershell
python tools/provision_sandbox.py --bucket adop-datalake-ACCOUNT-us-east-1
python tools/destroy_sandbox.py --dry-run
python tools/destroy_sandbox.py --yes
```

Full flags and KMS caveats: **`docs/SANDBOX_LIFECYCLE.md`**.

---

## Mode B — AgentCore Gateway (hybrid)

Laptop agent + cloud MCP for deploy-critical tools. Full checklist: **`docs/MODE_B_SETUP.md`**.

**Cursor fix:** Native `url` + `auth.aws-sigv4` often shows **Error** in Settings → MCP.
We use AWS **`mcp-proxy-for-aws-cli`** as a stdio bridge (SigV4 + your `AWS_PROFILE`).

```powershell
python tools/deploy_mcp_gateway.py --profile aws-agent
python tools/switch_mcp_mode.py --mode gateway --aws-profile aws-agent
python tools/verify_gateway_mcp.py --profile aws-agent
# Developer -> Reload Window, then enable agentcore-gateway in Settings -> MCP
```

Modes (see `docs/MODE_B_SETUP.md`):

| Mode | Behavior |
|------|----------|
| `local` | All 13 stdio on laptop |
| `gateway` | Single AgentCore Gateway endpoint (all 13 after deploy) |
| `hybrid` | Gateway for registered targets; local for the rest |
| `hybrid --local-only iam,core` | Mix: force named servers to stay on laptop stdio |

Restart Cursor if servers do not appear after `generate_mcp_config.py`.

---

## Enable in Claude Code

Open this repo in Claude Code. It loads `.mcp.json` automatically. Run Phase 0:

```text
python tools/mcp_health_check.py
```

Before Phase 5 deploy, re-run health check per `docs/MCP_GUARDRAILS.md`.

---

## Server tiers

| Tier | Servers | Phase 5 rule |
|---|---|---|
| **REQUIRED** | `glue-athena`, `lakeformation`, `iam` | Block deploy if any fail |
| **WARN** | `cloudtrail`, `redshift`, `core`, `s3-tables`, `pii-detection` | CLI fallback OK |
| **OPTIONAL** | `sagemaker-catalog`, `lambda`, `cloudwatch`, `cost-explorer`, `dynamodb` | Skip if unavailable |

**Not in registry:** Step Functions, EventBridge — Terraform/CLI only (Track A).

---

## Regenerate after changes

```powershell
python tools/generate_mcp_config.py --profile aws-agent --region us-east-1
python tools/validate_mcp_registry.py
```

Options: `--official-root`, `--python 3.12`, `--relative-scripts` (portable relative paths).

---

## Related

- `docs/MCP_GUARDRAILS.md` — Phase 5 MCP deploy steps
- `TOOL_ROUTING.md` — ownership table (MCP vs Terraform)
- `../agentic-projects/ADOP/MCP_GUARDRAILS.md` — full official guardrails
