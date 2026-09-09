# MCP custom servers (self-contained)

Custom MCP server scripts vendored from official ADOP for Track A. PyPI-backed servers
(iam, core, cloudtrail, etc.) are installed via `uvx` at runtime — see
`tool-registry/servers.yaml`.

**Regenerate Cursor/Claude MCP config after path changes:**

```powershell
python tools/generate_mcp_config.py
python tools/mcp_health_check.py --skip-aws
```

**Provenance:** copied from `aws-samples/sample-Agentic-Ai-Data-Operations` (sibling
`../agentic-projects/ADOP`). Re-sync when upstream custom servers change.
