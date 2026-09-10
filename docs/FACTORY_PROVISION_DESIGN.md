# Option B — Factory Provision (no-laptop API path)

**Goal:** Client uses **Harness only** → types **APPROVE** → AWS runs validate + deploy + optional E2E. No Cursor, no local CLI.

**Status:** Step 1 (Harness tool-use + design) — SFN/Terraform module pending Step 3.

---

## Flow

```text
Client / API
  → invoke_agentcore_harness.py  (or future API Gateway)
      → AgentCore Harness (Claude + Gateway tools)
          → factory.trigger_provision(workload, bucket, approve=true)
              → Step Functions: adop_factory_provision
                  → ValidateInput (Lambda)
                  → RunDeploy (CodeBuild sync — deploy_workload equivalent)
                  → StartWorkloadPipeline (Lambda — optional E2E)
              → get_provision_status(execution_arn)
```

---

## Contract

JSON Schema: `contracts/v1/factory_provision_request.schema.json`

| Field | Required | Notes |
|-------|----------|-------|
| `workload` | yes | Pre-onboarded name under `workloads/` |
| `bucket` | yes | Data lake bucket (no `s3://`) |
| `approve` | yes | Must be `true` after human APPROVE in Harness |
| `run_e2e` | no | Default `true` — landing sync + workload SFN |
| `session_id` | no | Harness audit trail |

Validation logic: `shared/deploy/factory_provision.py`

---

## Components

| Piece | Path | Step |
|-------|------|------|
| Request schema | `contracts/v1/factory_provision_request.schema.json` | 1 ✓ |
| Core library | `shared/deploy/factory_provision.py` | 1 ✓ |
| Gateway Lambda | `mcp-servers/gateway-lambdas/factory/` | 2 |
| Gateway target | `config/agentcore/gateway_targets.yaml` → `factory` | 2 |
| SFN ASL (skeleton) | `orchestration/factory_provision_state_machine.json` | 1 ✓ |
| Terraform module | `iac/terraform/modules/factory_provision/` | 3 |
| CodeBuild project | buildspec runs `deploy_workload --auto-provision` from S3 artifact | 3 |
| Harness prompt | `config/agentcore/harness_system_prompt.md` | 4 |

---

## Why CodeBuild (not Lambda-only)

`deploy_workload.py` needs git checkout, `terraform apply`, pytest, and long-running sync. Lambda 15 min cap is tight; **CodeBuild** matches the laptop script with no rewrite.

**v1 buildspec outline:**

```yaml
phases:
  install:
    commands:
      - pip install -r requirements.txt
      - curl -fsSL https://releases.hashicorp.com/terraform/1.9.x/terraform_1.9.x_linux_amd64.zip ...
  build:
    commands:
      - python tools/deploy_workload.py --workload $ADOP_WORKLOAD --bucket $ADOP_BUCKET --auto-provision
```

Repo artifact: zip from CI or `package_and_sync` bootstrap bucket (Step 3).

---

## Harness tool-use (Step 1)

| Model | Tool use | Notes |
|-------|----------|-------|
| `us.anthropic.claude-sonnet-4-6` | ✓ | **Default** after Step 1 fix |
| `us.amazon.nova-pro-v1:0` | ✗ | `modelStreamErrorException` on Gateway ToolUse |

Redeploy after model change:

```powershell
python tools/deploy_agentcore_harness.py --profile aws-agent
python tools/harness_smoke_test.py --live --profile aws-agent
```

---

## Approval gate (v1)

Harness system prompt requires:

1. Agent summarizes workload + bucket + `--run-e2e` flag.
2. User replies **`APPROVE`** (exact word).
3. Agent calls `trigger_provision` with `approve: true`.

`approve: false` → tool returns 400 / validation error (no SFN start).

---

## Test plan

| # | Test | Command |
|---|------|---------|
| 1 | Schema + allowlist | `pytest tests/test_factory_provision.py` |
| 2 | Harness tool-use | `python tools/harness_smoke_test.py --live` |
| 3 | Gateway factory target | After deploy gateway — `trigger_provision` dry path |
| 4 | SFN exists | `aws stepfunctions describe-state-machine --name adop_factory_provision` |
| 5 | End-to-end | Harness: "Provision supplier_lead_times to bucket X — APPROVE" |

---

## Next session (Step 2–3)

1. Add `factory` to Gateway — `python tools/deploy_mcp_gateway.py`
2. Terraform module: SFN + CodeBuild + validate/e2e Lambdas
3. Wire buildspec + S3 repo artifact
4. Extend Harness smoke with `trigger_provision` mock (SFN not deployed → expect clear error)

---

## Teardown

Factory SFN and CodeBuild are tagged `adop-sandbox`; include in `destroy_sandbox.py` when module lands.
