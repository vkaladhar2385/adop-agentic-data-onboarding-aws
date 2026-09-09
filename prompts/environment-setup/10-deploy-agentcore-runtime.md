# Deploy AgentCore Runtime (optional — Tier B2)

Use when exposing a **production API agent** (chat/onboard endpoint) on Bedrock AgentCore Runtime,
separate from the Gateway MCP path.

## Status

**Optional** for first Tier B milestone. Track A onboarding runs in Cursor with local MCP/Gateway.

## When needed

- External users invoke onboarding via HTTPS API
- Centralized agent session store + runtime observability required

## Reference

See official ADOP `prompts/environment-setup-agent/` runtime prompts in sibling repo
(`../agentic-projects/ADOP/`). Port when API agent is in scope.
