# TOOL_ROUTING.md — Track A Agent Factory

> Read this before pipeline operations. Official ADOP reference:
> `../agentic-projects/ADOP/TOOL_ROUTING.md` (13 MCP servers, MWAA deploy).
> Track A target: **MCP-first create**, **Terraform fallback**, **Step Functions + EventBridge**.

---

## Step 1 — Sub-agent or main conversation?

| Context | Allowed |
|---------|---------|
| **Main agent** (`/onboard-workflow`, deploy phase) | Read/write repo, pytest, validators, MCP (Phase 5), AWS CLI, Terraform **with user approval** |
| **Sub-agent** (Task tool, build phases) | **Generate YAML specs and hand-authored artifacts only** — no AWS, no MCP, no Terraform |
| **Build phases (1–4)** | Config + codegen specs + sql + tests; **not** direct writes to `scripts/` or `*_state_machine.json` |
| **Deploy phase (5)** | Main agent only; explicit user approval required |

**Sub-agents: stop after Step 1. You write specs. The main conversation renders and deploys.**

Prompt files: `prompts/onboarding/01-dedup-agent.md` … `04-deploy-agent.md`.

---

## Step 2 — Phase → tool map (Track A)

| Phase | Intent | Tool |
|-------|--------|------|
| 0 | Verify AWS identity / budget / MCP health | `aws sts get-caller-identity`; `python tools/mcp_health_check.py` |
| 1 | Discovery | Ask user; auto-profile local CSV or S3 sample (main agent) |
| 2 | Dedup | Sub-agent + `Glob`/`Read` on `workloads/*/config/source.yaml` |
| 3 | Profile | Read sample file; optional Athena via MCP (main agent) |
| 4a | Metadata + quality specs | Sub-agent → `config/*.yaml` + `config/codegen/*.spec.yaml` |
| 4b | Transform rules + sql + tests | Sub-agent → `transformations.yaml`, `sql/`, `tests/`, `eventbridge_schedule.json` |
| 4c | Validate | `validate_configs.py`, `validate_compute.py`, `pytest` |
| 4d | Codegen (mandatory) | `python tools/render_workload.py --workload {name} --all --write` then `--check-drift` |
| 4e | Ontology (opt-in) | Sub-agent `05-ontology-agent.md` → `shared.semantic_layer.induce_and_stage()` |
| 5 | Deploy | MCP catalog/LF/verify → TF fallback for compute/orchestration (see Step 3) |
| 5b | MWAA (when `orchestrator: mwaa`) | `tools/sync_mwaa_dags.py --workload {name} --s3-uri s3://…/dags/` |
| 5c | Gateway (Tier B AWS) | `tools/generate_mcp_gateway_config.py` → `mcp_health_check.py --config .mcp.gateway.json` |

---

## Step 3 — Deploy ownership (MCP first, Terraform fallback)

**Policy:** MCP creates any asset the official 13 servers can create. Terraform owns only
what has **no MCP create tool** (or platform infra already in state). **Never both create the
same ARN.**

Full guardrails: `docs/MCP_GUARDRAILS.md`. Server list: `tool-registry/servers.yaml`.

### Ownership table

| AWS asset | Primary owner | Tool |
|---|---|---|
| S3 objects (scripts, landing data) | **MCP** | `core` S3 / `package_and_sync.py` for Glue script sync |
| KMS keys / aliases | **MCP** | `core` KMS |
| IAM roles / inline policies | **MCP** | `iam` MCP |
| Glue **database / table** (catalog) | **MCP** | `glue-athena` `create_database` / `create_table` |
| Glue **crawler** | **MCP** | `glue-athena` |
| Lake Formation tags / grants | **MCP** | `lakeformation` / lambda LF grant tools |
| Athena / Redshift **verify queries** | **MCP** | `glue-athena` / `redshift` |
| CloudTrail audit lookup | **MCP** | `cloudtrail` |
| Glue **job** definition | **Terraform** (until custom MCP tool) | `iac/terraform/modules/workload_pipeline/glue.tf` |
| Lambda **function** | **Terraform** | `lambda.tf` |
| Step Functions state machine | **Terraform** | `main.tf` (no SFN MCP in official 13) |
| EventBridge Scheduler | **Terraform** | `main.tf` |
| SNS alerts | **Terraform** | `main.tf` |
| Redshift Serverless namespace/workgroup | **Terraform** | `modules/redshift_workload/` |
| OpenSearch domain | **Terraform** | `modules/opensearch_workload/` |
| ElastiCache Redis + VPC endpoint | **Terraform** | `modules/redis_workload/` |
| AWS Budgets | **Terraform** | `main.tf` |

### Phase 5 order (after human approval)

1. `python tools/check_codegen_drift.py` — must pass
2. `python tools/deploy_workload.py --workload {name} --dry-run`
3. **Terraform fallback:** `package_and_sync` + `terraform plan` (+ `apply` with `--approve-apply`)
4. **MCP:** catalog registration, LF-Tags/grants, Athena/Redshift verify, CloudTrail audit
5. **CLI:** `aws stepfunctions start-execution` (SFN has no MCP server)
6. Post-deploy verifier (Lambda in SFN and/or MCP query checks)

**Orchestrator default:** `step_functions` when `config/schedule.yaml` omits `orchestrator`
(see `shared/utils/orchestrator.py`). User may opt into **MWAA** at discovery (Tier B DAG codegen).
Compute: read
`config/compute.yaml` — Iceberg Silver/Gold writes require `glueetl`.

---

## Step 4 — Enforced schema codegen

Scripts under `workloads/*/scripts/` and `orchestration/*_state_machine.json` MUST be produced
by `tools/render_workload.py` (which sets `ADOP_RENDERER_TOKEN` while writing).

| Guard | Location |
|---|---|
| Cursor hook | `.cursor/hooks.json` → `preToolUse` on `Write\|StrReplace` |
| Claude Code hook | `.claude/settings.json` → `PreToolUse` |
| Shared logic | `shared/codegen/write_guard.py` |
| CI drift | `tools/check_codegen_drift.py` in `.github/workflows/ci.yml` |

**Agents edit specs** (`config/codegen/*.spec.yaml`, `shared/templates/*.j2`), then render.
Do not hand-edit generated files except legacy workloads marked below.

**Legacy exception:** `web_events` ingest + bronze→silver remain hand-authored (JSONL, no
Spark spec yet). All other workloads use codegen for scripts + SFN when specs exist.

---

## Step 5 — MCP servers (Track A target)

Wire the official 13 from the sibling clone (`docs/MCP_WIRING.md`). Sub-agents must **not** use MCP.

Setup (once):

```bash
python tools/generate_mcp_config.py
python tools/mcp_health_check.py
```

| Tier | Servers |
|---|---|
| **REQUIRED** | `glue-athena`, `lakeformation`, `iam` |
| **WARN** | `cloudtrail`, `redshift`, `core`, `s3-tables`, `pii-detection` |
| **OPTIONAL** | `sagemaker-catalog`, `lambda`, `cloudwatch`, `cost-explorer`, `dynamodb` |

Cursor `user-aws-mcp` is optional for docs/reads; do not mix with the official 13 registry.

---

## Step 6 — Deferred

| Item | Status |
|------|--------|
| OpenSearch / Redis SFN steps | Off live advisory SFN; enable via `state_machine.spec.yaml` flags |
| MWAA live sync | `tools/sync_mwaa_dags.py` after sandbox MWAA bucket exists |
| AgentCore Gateway cutover | `prompts/environment-setup/09-deploy-agentcore-gateway.md` |
| MCP `create_job` / `CreateStateMachine` | Backlog to shrink Terraform further |
| Full Phase 7 multi-cloud abstractions | After Track B |

---

## Step 7 — Never

- Sub-agent calling `terraform apply`, MCP deploy, or `aws glue start-job-run`
- MCP-create a resource still declared in Terraform (same ARN)
- Direct Write/Edit to `workloads/*/scripts/` or `*_state_machine.json` (hook blocks)
- Hardcoding account IDs, bucket names, or secrets in scripts
- Deploy without pytest + validator + codegen drift pass
- Python Shell writing Iceberg Silver/Gold tables
