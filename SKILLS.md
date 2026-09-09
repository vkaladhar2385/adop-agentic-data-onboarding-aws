# SKILLS.md — Track A Agentic Data Onboarding Factory

> Agent + skill catalog for this repo. Adapted from official ADOP
> (`../agentic-projects/ADOP/SKILLS.md`) for **Step Functions + EventBridge** (default),
> **MWAA opt-in**, **spec → renderer codegen**, and **MCP-first deploy**.
>
> **Read with:** `AGENTS.md`, `TOOL_ROUTING.md`, `.cursor/commands/onboard-workflow.md`

---

## System context

This platform onboarded data through a **Bronze → Silver → Gold** medallion architecture using
specialized agents under **human-in-the-loop** control. Agents ask before irreversible actions,
respect security boundaries, and reuse existing configs/scripts when possible.

**Track A differences from official ADOP:**

| Topic | Official ADOP | This repo (Track A) |
|-------|---------------|---------------------|
| Orchestration default | MWAA Airflow DAG | **Step Functions ASL** + EventBridge Scheduler |
| Orchestration opt-in | — | **MWAA** when `config/schedule.yaml` → `orchestrator: mwaa` (Tier B) |
| Executable scripts | Renderer from specs | Same — `tools/render_workload.py` |
| MCP custom servers | In-repo | **Vendored** at `mcp-servers/` |
| Deploy | MCP Phase 5 | MCP-first + `tools/deploy_workload.py` Terraform fallback |

---

## MCP-first rule

**All AWS operations in the main conversation MUST use MCP tools first.** Fall back to AWS CLI
only if MCP is unavailable or errors. See `TOOL_ROUTING.md` and `tool-registry/servers.yaml`.

**Critical constraint:** Sub-agents (Task tool / Agent tool) do **NOT** have MCP access.
Sub-agents emit **specs, configs, SQL, tests, and AgentOutput JSON** only. Deploy runs in the
**main conversation** after human approval.

Phase 0 health check:

```bash
python tools/generate_mcp_config.py
python tools/mcp_health_check.py
```

---

## Agent model: main agent + sub-agents

```
MAIN CONVERSATION (/onboard-workflow)
│
├── Router (inline) — workloads/ exists? new vs extend
│
└── Data Onboarding Agent (orchestrator, human-facing)
    │
    │  Phase 0: MCP health + AWS identity        ← main agent, read-only
    │  Phase 1: Discovery (6 question groups)    ← HITL gate (AGENTS.md STOP)
    │  Phase 2: Dedup                            ← sub-agent: 01-dedup-agent.md
    │  Phase 3: Profile (optional)               ← main agent samples local/S3 data
    │
    │  Phase 4: Build (sub-agents + test gates)
    │  ┌──────────────────────────────────────────────────────────┐
    │  │ Metadata + Quality Agent → config/*.yaml + codegen specs │
    │  │         ▼ TEST GATE: validate_configs, validate_compute  │
    │  │ Build Agent → transformations.yaml, sql/, tests/         │
    │  │         ▼ TEST GATE: pytest workloads/{name}/tests/       │
    │  │ Main agent: render_workload.py --all --write              │
    │  │         ▼ TEST GATE: check_codegen_drift                  │
    │  │ Orchestration (codegen, not sub-agent hand-write):        │
    │  │   default → state_machine.json.j2 → SFN ASL                 │
    │  │   opt-in  → airflow_dag.py.j2 → dags/ (Tier B)              │
    │  └──────────────────────────────────────────────────────────┘
    │
    │  Present artifacts + test results → human approve
    │
    │  Phase 5: Deploy (main only — MCP + Terraform fallback)
    │  `/devops-workflow` or deploy sub-agent prompt 04-deploy-agent.md
    └──────────────────────────────────────────────────────────────
```

**Why sub-agents?**

- Focused context — no crosstalk between stations
- Failures contained — bad transform output does not corrupt main thread
- Parallel potential — metadata specs vs SQL can fan out when safe
- Orchestrator stays lean — validate AgentOutput, write files, run gates

---

## Sub-agent output format (mandatory)

Every sub-agent MUST finish with an **AgentOutput** JSON payload.

- **Schema:** `shared/templates/agent_output_schema.py`
- **Contract doc:** `prompts/onboarding/_agent_output_contract.md`
- **I/O helpers:** `shared/utils/agent_output_io.py`
- **Persistence:** `workloads/{name}/logs/agent_outputs/{agent_type}.json`

The main agent:

1. Parses JSON → `AgentOutput.from_dict`
2. Calls `parse_agent_output_payload` — **stops** if `not can_proceed`
3. Writes artifact files from `file_contents` in payload (or listed paths)
4. Appends `trace_events.jsonl`

**Bedrock / AgentCore Runtime:** use tool `submit_agent_output` with the same schema
(`SUBMIT_OUTPUT_TOOL` in `agent_output_schema.py`).

### Required fields

- `agent_name`, `agent_type`, `workload_name`, `run_id`, `started_at`, `completed_at`, `status`
- `artifacts`: `[{path, type, checksum}]` for every file the main agent should write
- `blocking_issues`: `[]` when none
- `tests`: `{unit: {passed, failed, total}, integration: {...}}`

### Valid `agent_type` values (Track A)

| agent_type | Prompt file |
|------------|-------------|
| `dedup` | `prompts/onboarding/01-dedup-agent.md` |
| `metadata` | `prompts/onboarding/02-metadata-quality-agent.md` |
| `transformation` | `prompts/onboarding/03-build-agent.md` |
| `devops` | `prompts/onboarding/04-deploy-agent.md` |
| `ontology_staging` | `prompts/onboarding/05-ontology-agent.md` (opt-in) |
| `analysis` | Ad-hoc profiling sub-tasks |
| `dag` | Tier B — `config/codegen/dag.spec.yaml` (MWAA) |
| `quality` | Reserved — merged into `metadata` agent in Track A |

### Decisions and memory

Document non-trivial choices in `decisions[]` (audit trail). Flag durable facts in
`memory_hints[]` for future runs.

---

## Determinism requirements (mandatory)

Same discovery answers + same specs → same rendered artifacts.

1. **Input hash** — SHA-256 of inputs; include in spec comments where applicable
2. **Output hash** — SHA-256 per artifact; list in `AgentOutput.artifacts`
3. **Renderer ownership** — `workloads/*/scripts/**` and `orchestration/*_state_machine.json`
   are produced only by `tools/render_workload.py` (PreToolUse hook blocks direct writes)
4. **CI drift** — `python tools/check_codegen_drift.py` must pass before deploy
5. **Stable ordering** — sort YAML keys; stable list ordering in specs
6. **No unseeded randomness** in generated configs

---

## Compute routing (Glue job types)

**Source of truth:** `workloads/{name}/config/compute.yaml`

| Step | Default | Hard rule |
|------|---------|-----------|
| `bronze_to_silver` | `glueetl` | Iceberg Silver ⇒ **always glueetl** |
| `silver_to_gold` | `glueetl` | Iceberg Gold ⇒ **always glueetl** |
| `quality_*` | `pythonshell` | Sidecar scores; no Iceberg commits from Shell |
| `ingest_to_bronze` | `auto` | Volume + format from discovery |

Every `glueetl` job: `--datalake-formats=iceberg`, `--enable-data-lineage=true`.

---

## Orchestration choice

**Default:** `step_functions` when `orchestrator` is omitted (`shared/utils/orchestrator.py`).

Record in `config/schedule.yaml`:

```yaml
orchestrator: step_functions   # default
# orchestrator: mwaa           # explicit opt-in (Tier B — DAG codegen + MWAA deploy)
```

| orchestrator | Codegen output | Deploy owner |
|--------------|----------------|--------------|
| `step_functions` | `orchestration/{name}_state_machine.json` | Terraform SFN + EventBridge |
| `mwaa` | `dags/{name}_pipeline.py` (Tier B) | MWAA sync + Terraform MWAA module |

Ask during discovery Group 6. Do not assume MWAA for cost-sensitive sandboxes.

---

## Skill: Router Agent — INLINE

**Runs in:** main conversation (start of `/onboard-workflow`).

**Purpose:** Decide whether the request targets an existing workload or a new factory run.

**Actions:**

1. Glob `workloads/*/config/source.yaml`
2. If user named a workload and folder exists → offer extend vs new version
3. If new → proceed to Phase 1 discovery
4. Never skip `.discovery_complete` gate for greenfield builds

---

## Skill: Data Onboarding Agent — MAIN AGENT

**Runs in:** main conversation.

**Entry:** `.cursor/commands/onboard-workflow.md`

**Purpose:** Human-facing orchestrator for Phases 0–5.

### Phase 1 — Discovery (STOP gate)

Do **not** write `workloads/` artifacts until ALL checklist items in `AGENTS.md` have explicit
human answers. Ask one group at a time (source, schema/keys, transforms, PII, quality, schedule).

### Phase 2 — Dedup

Spawn sub-agent with `prompts/onboarding/01-dedup-agent.md`. Validate AgentOutput before proceed.

### Phase 4 — Build sequence

1. Spawn **Metadata + Quality** (`02-metadata-quality-agent.md`)
2. Validate configs + compute
3. Spawn **Build** (`03-build-agent.md`)
4. **Mandatory codegen:**

   ```bash
   python tools/render_workload.py --workload {name} --all --write
   python tools/render_workload.py --workload {name} --all --check-drift
   ```

5. `pytest workloads/{name}/tests/ -v`

### Phase 5 — Deploy

Only after explicit user approval. Use `tools/deploy_workload.py` and `docs/MCP_GUARDRAILS.md`.
Sub-agents do not apply Terraform.

---

## Skill: Dedup Agent — SUB-AGENT

**Prompt:** `prompts/onboarding/01-dedup-agent.md`

**agent_type:** `dedup`

**Purpose:** Scan existing workloads for overlapping S3 paths, keys, or semantic collision.

**Outputs:** AgentOutput only (no files). `status=failed` + `blocking_issues` on OVERLAP.

**Constraints:** No AWS, no MCP, no file writes.

---

## Skill: Metadata + Quality Agent — SUB-AGENT

**Prompt:** `prompts/onboarding/02-metadata-quality-agent.md`

**agent_type:** `metadata`

**Purpose:** Emit workload config and codegen **specs** (not rendered scripts).

**Outputs (via AgentOutput `file_contents`):**

| File | Notes |
|------|-------|
| `config/source.yaml` | No real account IDs — placeholders |
| `config/semantic.yaml` | PII classifications, LF-Tag hints |
| `config/quality_rules.yaml` | Silver ≥ 0.80, Gold ≥ 0.95 unless user specified |
| `config/schedule.yaml` | Cron, retries, `orchestrator` (default step_functions) |
| `config/compute.yaml` | Per-step `job_type`; Iceberg ⇒ glueetl |
| `config/codegen/*.spec.yaml` | Drives `shared/templates/*.j2` |

**Never return:** `scripts/**/*.py`, `orchestration/*_state_machine.json` bodies.

**Validation (main agent runs):**

```bash
python tools/validate_configs.py
python tools/validate_compute.py --workload {name}
```

---

## Skill: Build Agent (Transformation) — SUB-AGENT

**Prompt:** `prompts/onboarding/03-build-agent.md`

**agent_type:** `transformation`

**Purpose:** Transformation rules, SQL DDL, unit tests, README, remaining codegen specs.

**Outputs:**

| File | Notes |
|------|-------|
| `config/transformations.yaml` | Validates against `contracts/v1/transformations.schema.json` |
| `config/codegen/*.spec.yaml` | Complete any missing specs |
| `sql/bronze|silver|gold/*.sql` | Iceberg DDL where applicable |
| `orchestration/eventbridge_schedule.json` | Hand-authored until template exists |
| `tests/unit/*.py` | pandas fixtures — no AWS |
| `README.md` | Phase 1 decisions + local run instructions |

**Logging:** Production Glue scripts use `StructuredLogger` (`shared/utils/structured_logger.py`)
via rendered templates.

**Constraints:** Renderer-only for executable pipeline code. No Terraform, no MCP.

---

## Skill: Orchestration Agent — CODEGEN (not free-form LLM scripts)

**Default path:** Step Functions ASL from `config/codegen/state_machine.spec.yaml` +
`shared/templates/state_machine.json.j2`.

**Opt-in path (Tier B):** MWAA DAG from `config/codegen/dag.spec.yaml` (future) +
`shared/templates/airflow_dag.py.j2` (to be ported from official ADOP).

Extension flags in SFN spec: `redshift`, `opensearch`, `redis` — OpenSearch/Redis **deferred**
in live SFN for sandbox cost unless user explicitly opts in later.

**Main agent runs render** — sub-agents emit specs only.

---

## Skill: Deploy / DevOps Agent — SUB-AGENT or MAIN (Phase 5)

**Prompts:**

- `prompts/onboarding/04-deploy-agent.md` — Phase 5 onboard deploy
- `prompts/devops/01-iac-agent.md` — `/devops-workflow` Terraform snippet
- `.cursor/commands/devops-workflow.md` — health check → plan

**agent_type:** `devops`

**Purpose:** Validate, sync, plan — **apply only with `--approve-apply` and user consent**.

**Preconditions:**

```bash
python tools/check_codegen_drift.py
python tools/deploy_workload.py --workload {name} --dry-run
pytest workloads/{name}/tests/ -v
```

**Ownership:** MCP for catalog/LF/KMS/IAM verify; Terraform for Glue jobs, Lambda, SFN, SNS.

---

## Skill: Ontology Staging Agent — SUB-AGENT (Tier B, opt-in)

**Status:** Not wired in Track A MVP. Planned for Tier B.

**Purpose (official ADOP):** Emit `ontology.ttl`, `mappings.ttl`, `ontology_manifest.json` from
`semantic.yaml` + Gold schema for AWS Semantic Layer.

**When added:** `prompts/onboarding/05-ontology-agent.md`, `shared/semantic_layer/`.

Skip unless user opts in during discovery.

---

## Security rules (all agents)

1. No hardcoded secrets — Secrets Manager / env / Terraform vars only
2. No account IDs, VPC IDs, or bucket names in committed scripts
3. Bronze immutable — never mutate after ingest
4. Quality gates block promotion — no bypass
5. PII: classify in `semantic.yaml`; mask in Silver/Gold transforms
6. Sub-agents never call AWS

---

## Test gates (orchestrator must enforce)

| After station | Command |
|---------------|---------|
| Metadata + Quality specs | `validate_configs.py`, `validate_compute.py` |
| Build artifacts | `pytest workloads/{name}/tests/ -v` |
| Codegen | `render_workload.py --all --write`, `check_codegen_drift.py` |
| Pre-deploy | `deploy_workload.py --dry-run` |
| Post-deploy | Step Functions E2E + `post_deployment_verifier` |

Do not advance to the next station if AgentOutput `can_proceed` is false or tests fail.

---

## Reference workloads

| Workload | Use for |
|----------|---------|
| `advisory_transactions` | SOX, Redshift SFN, mixed compute, full codegen |
| `product_inventory` | Factory proof #2, catalog-only |
| `supplier_lead_times` | **Tier A workload #4** — weekly procurement CSV, catalog-only |
| `web_events` | GDPR rollups; full pipeline codegen (jsonl ingest + web_events b2s template) |

Official ADOP study clone: `../agentic-projects/ADOP/` (`docs/TRACK_B.md`).

---

## Quick command reference

```bash
# Onboard build (main agent)
python tools/validate_configs.py
python tools/validate_compute.py --workload {name}
python tools/render_workload.py --workload {name} --all --write
python tools/check_codegen_drift.py
pytest workloads/{name}/tests/ -v

# Deploy (approved only)
python tools/deploy_workload.py --workload {name} --bucket {lake_bucket}
python tools/deploy_workload.py --workload {name} --bucket {lake_bucket} --approve-apply
```

---

## Version

- **Track A SKILLS.md** — adapted for Agent Factory M1–M6 + Tier A (AgentOutput, self-contained MCP)
- **Upstream:** official ADOP `SKILLS.md` (Agent + skill catalog pattern)
