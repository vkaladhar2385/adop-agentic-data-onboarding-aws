# Pilot status — what's done, what's left

Last verified live AWS run: Step Functions `tier-b-e2e-fix-v3-20260909-124345` (**SUCCEEDED**).

Previous green run: `framework-e2e-v6-20260908-185515`.

Previous failures (resolved):

| Run | Failed at | Cause |
|-----|-----------|-------|
| v1–v2 | PostDeploymentVerify | Verifier LF permissions; OpenSearch checks |
| v3–v4 | BronzeToSilver | `register_catalog` Parquet DDL corrupted Iceberg catalog |
| v5 | PostDeploymentVerify | Gold Iceberg metadata under `silver/` — Redshift S3 scope was `gold/` only |
| v6 | — | **Green** — per-job warehouse + catalog self-heal in `spark_transforms.py` |

---

## Agent Factory progress

| Milestone | Target | Factory % (weighted) | Status |
|-----------|--------|----------------------|--------|
| **Today** (pre-M1) | One hand-built pilot + partial codegen | **~35–40%** | In progress |
| **M1** | `/onboard-workflow` + sub-agents + workload #2 via factory | **~55–60%** | Row 10 done; row 9 deferred (E2E / LF-IAM) |
| **M2** | Full codegen templates (ingest, silver→gold, quality, SFN JSON) | ~70% | **Done** — both workloads render from shared templates |
| **M3** | `/devops-workflow`, trace logs, deploy wrapper hardened | ~80% | **Done** — command + dry-run/apply gates |
| **M4** | 3rd workload, StructuredLogger, CI drift, docs aligned | ~85% | **Done** — `web_events` factory-aligned |
| **M5** | MCP-first contract + enforced codegen hooks | ~88% | **Done** — `TOOL_ROUTING.md`, `MCP_GUARDRAILS.md`, write guard |
| **M6** | Wire official 13 MCP servers | ~92% | **Done** — `.mcp.json`, health check, `docs/MCP_WIRING.md` |
| **M6b** | MCP-first data plane cutover | ~94% | **Done** — catalog, KMS, IAM, LF → MCP; TF → jobs/Lambdas/SFN/SNS |

**Deferred (cost / optional extensions):** OpenSearch/Redis SFN steps; Prompt Intelligence loop.

**M1–M6b vs official ADOP:** Internal milestones measure Track A scaffolding (~85–94%).
**Tier A** = factory process on disk. **Tier B** = full official parity (Gateway, Cedar,
ontology, dual orchestration). **Target:** complete Tier A then Tier B — not “skip Tier B.”

Reference: `AGENTS.md` (framework roadmap), `docs/TRACK_B.md` (official ADOP comparison).

---

## Tier A — Factory process (steps 1–7)

**Goal:** Repeatable spec → render → test → deploy plant. Same work order in, same SKU out.
**Tier B items are next**, not optional for the full ADOP-shaped factory (see below).

**Acceptance test:** Run `/onboard-workflow` for a **fourth workload** (small CSV, catalog-only).
Sub-agents return validated `AgentOutput` JSON; main agent renders; `pytest` + drift + validators
pass; no hand-edits to `scripts/` or `*_state_machine.json`; MCP health passes with servers
**inside this repo** (no sibling-clone path required).

| # | Deliverable | Location / action | Done |
|---|-------------|-------------------|------|
| **A1** | HITL discovery gate (6 groups) | `AGENTS.md`, `.cursor/commands/onboard-workflow.md` | ☑ |
| **A2** | Dedup + build sub-agent prompts | `prompts/onboarding/01–04-*.md` | ☑ |
| **A3** | Build vs deploy separation | `TOOL_ROUTING.md`, `.cursor/rules/agent-factory-build-deploy.mdc` | ☑ |
| **A4** | Deploy wrapper (no apply without flag) | `tools/deploy_workload.py` | ☑ |
| **A5** | Trace helper | `shared/utils/agent_trace.py` | ☑ |
| **A6** | **`AgentOutput` schema + parser** | `shared/templates/agent_output_schema.py`, `shared/utils/agent_output_io.py` | ☑ |
| **A7** | **Sub-agents must finish via structured output** | `prompts/onboarding/_agent_output_contract.md`, `01–04` prompts, onboard command | ☑ |
| **A8** | **`SKILLS.md` catalog** (main + sub-agent skills) | `SKILLS.md` — Track A adapt (SFN default, MWAA opt-in, AgentOutput) | ☑ |
| **A9** | **Hard-fail write guard** | `.cursor/hooks.json` → `failClosed: true` | ☑ |
| **A10** | Core codegen templates (5) | `shared/templates/*.j2` | ☑ |
| **A11** | **Full codegen coverage — all 3 workloads** | All pipeline specs render; drift clean on 3 workloads | ☑ |
| **A12** | CI drift + schema validators | `tools/check_codegen_drift.py`, `tools/validate_configs.py`, `.github/workflows/ci.yml` | ☑ |
| **A13** | **Expand JSON Schema contracts** (spec types) | `contracts/v1/codegen_*.spec.schema.json` (5) + `validate_configs.py` | ☑ |
| **A14** | **Self-contained MCP servers** | `mcp-servers/` vendored; `generate_mcp_config.py` + `mcp_health_check.py` prefer local tree | ☑ |
| **A15** | MCP registry + health (13 servers) | `tool-registry/servers.yaml`, `tools/mcp_health_check.py` | ☑ (paths external today) |
| **A16** | Factory proof workload #2 | `workloads/product_inventory/` | ☑ |
| **A17** | **Factory proof workload #4** (end-to-end Tier A test) | `workloads/supplier_lead_times/` — 8 pytest, drift clean, AgentOutput logs | ☑ |
| **A18** | Orchestration choice at discovery | `config/schedule.yaml` → `orchestrator: step_functions \| mwaa`; **default `step_functions` if omitted** | ☑ |

**Tier A complete:** ☑ (2026-09-09) — all A6–A18 checked; workload #4 `supplier_lead_times` acceptance passed.

### Codegen coverage (A11)

| Workload | Codegen-rendered | Still hand-authored (documented) |
|----------|------------------|----------------------------------|
| `advisory_transactions` | ingest, b2s, s2g, quality, SFN | `spark_transforms.py`, `register_catalog.py`, Redshift loader |
| `product_inventory` | ingest, b2s, s2g, quality, SFN | `spark_transforms.py`, `register_catalog.py` |
| `web_events` | ingest (jsonl), b2s, s2g, quality, SFN | `register_catalog.py` (no spark_transforms yet) |

Re-render all: `foreach ($w in @("advisory_transactions","product_inventory","web_events")) { python tools/render_workload.py --workload $w --all --write }`

### Tier A execution order (recommended)

| Step | Action | Verify |
|------|--------|--------|
| **1** | ~~Port `agent_output_schema.py`~~ | **Done** — `pytest tests/test_agent_output.py -v` |
| **2** | ~~AgentOutput prompts + I/O~~ | **Done** — `_agent_output_contract.md`, onboard command |
| **3** | ~~Adapt `SKILLS.md`~~ | **Done** — `SKILLS.md` + `AGENTS.md` key files |
| **4** | ~~Hard write guard~~ | **Done** — `.cursor/hooks.json` `failClosed: true` |
| **5** | ~~Codegen gaps (web_events + product_inventory)~~ | **Done** — 4 new specs, `web_events_bronze_to_silver` template, jsonl ingest |
| **6** | ~~Expand codegen JSON Schema contracts~~ | **Done** — 20 specs validated |
| **7** | Self-contained MCP (done — `mcp-servers/`); regenerate config | `python tools/generate_mcp_config.py` + `mcp_health_check.py --skip-aws` |
| **8** | ~~Workload #4 acceptance~~ | **Done** — `supplier_lead_times` |

---

## Tier B — Full ADOP parity (after Tier A; **not skipped**)

**Goal:** Match official ADOP AgentOps shape: hosted MCP, enforced sub-agent boundaries,
ontology station, and **human-chosen orchestration** (Step Functions **or** MWAA — not SFN-only).

**Acceptance test:** Workload #5 onboarded with user selecting `orchestrator: mwaa` **or**
`step_functions`; Gateway health passes; Cedar blocks a simulated sub-agent MCP call;
ontology artifacts staged when user opts in; deploy uses MCP-first path on Gateway.

| # | Deliverable | Location / action | Done |
|---|-------------|-------------------|------|
| **B1** | **AgentCore Gateway** (13 MCP servers cloud-hosted) | Port runbook → `prompts/environment-setup/09-deploy-agentcore-gateway.md`; `.mcp.gateway.json` | ☑ Gateway live (glue-athena target); `tools/deploy_mcp_gateway.py` |
| **B2** | AgentCore Runtime (production API agent) | `prompts/environment-setup/10-deploy-agentcore-runtime.md` — optional until API needed | ☑ stub doc |
| **B3** | **Cedar / AVP** sub-agent policy enforcement | Port `shared/policies/` from official ADOP; `sub-agent-no-mcp.cedar`; pre-commit validator | ☑ policies + `tools/validate_cedar_policies.py` + `shared/utils/cedar_policy.py` |
| **B4** | **Ontology Staging Agent** (opt-in at discovery) | `prompts/onboarding/05-ontology-agent.md`; `shared/semantic_layer/`; emit `ontology.ttl`, `mappings.ttl` | ☑ local staging |
| **B5** | **MWAA DAG codegen** | Port `shared/templates/airflow_dag.py.j2` + `contracts/v1/dag_spec.schema.json`; `workloads/{name}/dags/` | ☑ |
| **B6** | **Dual orchestration render** | `render_workload.py`: if `schedule.yaml` → `orchestrator: mwaa` render DAG; if `step_functions` render SFN JSON (existing) | ☑ |
| **B7** | Discovery Group 6 — orchestrator choice | Ask SFN vs MWAA; **default `step_functions`** if user skips; set `mwaa` only when explicit | ☑ onboard Group 6 + `orchestrator.py` |
| **B8** | MWAA deploy path | Terraform MWAA module or `package_and_sync` → MWAA DAG bucket; document in `TOOL_ROUTING.md` | ☑ `tools/sync_mwaa_dags.py` + TOOL_ROUTING |
| **B9** | Prompt Intelligence (feedback loop) | Tool/script reading `workloads/*/logs/trace_events.jsonl` → prompt diff suggestions | ☑ `tools/prompt_intelligence.py` |
| **B10** | Factory proof workload #5 (Tier B) | Full path with Gateway + chosen orchestrator + optional ontology | ☑ `customer_orders` on disk; AWS E2E `tier-b-e2e-fix-v3-20260909-124345` green (catalog-only SFN) |

**Tier B complete when:** B1, B3–B8, B10 checked (B2/B9 optional for first B milestone).

### Why Tier B was listed as “skip” earlier

Tier A was defined as the **minimum** bar to claim “factory process” without standing up
cloud AgentOps (~$ + setup). That was a **scope shortcut for a first milestone**, not a
recommendation to omit Gateway, Cedar, or ontology permanently. Your target is **Tier A + Tier B**.

### Tier B execution order (after Tier A step 8)

| Step | Action | Verify |
|------|--------|--------|
| **9** | Add discovery question + `schedule.yaml` orchestrator field (B7, A18) | **Done** — onboard Group 6 + resolver |
| **10** | Port MWAA DAG template + `dag_spec.schema.json`; extend renderer (B5–B6) | **Done** — `customer_orders` renders `dags/` |
| **11** | Port Cedar policies + validator (B3) | **Done** — pytest denies sub-agent MCP |
| **12** | Port ontology agent + semantic_layer (B4) | **Done** — `customer_orders` TTL + manifest |
| **13** | Deploy AgentCore Gateway; switch to `.mcp.gateway.json` (B1) | **Done** — `adop-mcp-gateway-ztpftsljts` + glue-athena target; `.mcp.gateway.json` |
| **14** | MWAA sync (**optional demo only**, not default) | **Skipped** (per user — demo later via `--mwaa-demo`) |
| **15** | Tier B E2E (B10) | **Done** — SFN `tier-b-e2e-fix-v3-20260909-124345` through PostDeploymentVerify (fixes: `silver_read_suffix=/quality_export`, SFN catalog-only, Glue `glue.id` + LF `GetDataAccess`) |

### Orchestration rule (human decides)

| User choice at discovery | Factory emits | Deploy owns |
|--------------------------|---------------|-------------|
| `orchestrator: step_functions` | `orchestration/{name}_state_machine.json` (codegen) | Terraform SFN + EventBridge (current) |
| `orchestrator: mwaa` | `dags/{name}_pipeline.py` (codegen from `airflow_dag.py.j2`) | MWAA sync + `config/dag.yaml` |
| User says “both” | Emit **both** artifacts; deploy **one** primary (user confirms at deploy gate) | Document secondary as export-only |

**Default:** omit `orchestrator` or leave unset → **`step_functions`** (`shared/utils/orchestrator.py`).
Ask MWAA explicitly during discovery; record `orchestrator: mwaa` in `config/schedule.yaml` when chosen.

---

## M1 checklist — Agent Factory MVP

**Acceptance test:** Run `/onboard-workflow` for a **second workload** (small CSV, catalog-only
or Redshift if needed). Land artifacts under `workloads/{name}/`, pass
`pytest workloads/{name}/ -v` and `python tools/validate_configs.py`, **without**
`terraform apply` unless the user explicitly approves deploy.

| # | Deliverable | Location | Done |
|---|-------------|----------|------|
| 1 | Onboarding command (Phase 1 gate → build → pytest) | `.cursor/commands/onboard-workflow.md` | ☑ |
| 2 | Dedup sub-agent prompt | `prompts/onboarding/01-dedup-agent.md` | ☑ |
| 3 | Metadata + quality sub-agent prompt | `prompts/onboarding/02-metadata-quality-agent.md` | ☑ |
| 4 | Build sub-agent prompt (transform + orchestration + tests) | `prompts/onboarding/03-build-agent.md` | ☑ |
| 5 | Deploy sub-agent prompt (validate + sync + plan only) | `prompts/onboarding/04-deploy-agent.md` | ☑ |
| 6 | Tool routing (main vs sub-agent, Track A deploy path) | `TOOL_ROUTING.md` | ☑ |
| 7 | Build vs deploy separation rule | `.cursor/rules/agent-factory-build-deploy.mdc` | ☑ |
| 8 | Deploy wrapper (no apply without `--approve-apply`) | `tools/deploy_workload.py` | ☑ |
| 9 | Redshift-only E2E proof on sandbox | SFN `framework-e2e-v6-20260908-185515` | ☑ |
| 10 | **Factory proof:** workload #2 onboarded via workflow | `workloads/product_inventory/` + 12 pytest passed | ☑ |

**M1 complete when:** rows 9–10 are checked and the user confirms workload #2 artifacts
need no more than minor hand edits. Row 9 is **not blocking M2**.

---

## M2 checklist — Codegen templates

| # | Deliverable | Location | Done |
|---|-------------|----------|------|
| 1 | Ingest template | `shared/templates/ingest_to_bronze.py.j2` | ☑ |
| 2 | Silver→Gold template | `shared/templates/silver_to_gold.py.j2` | ☑ |
| 3 | Quality gate template | `shared/templates/quality_checks.py.j2` | ☑ |
| 4 | SFN JSON template (optional Redshift / OpenSearch / Redis) | `shared/templates/state_machine.json.j2` | ☑ |
| 5 | Render + drift on `product_inventory` | `tools/render_workload.py --all` | ☑ |
| 6 | Wire advisory SFN + remaining scripts to the same templates | `workloads/advisory_transactions/config/codegen/` | ☑ |

---

## M3 checklist — DevOps + deploy harden

| # | Deliverable | Location | Done |
|---|-------------|----------|------|
| 1 | DevOps command (health check → IaC snippet → plan) | `.cursor/commands/devops-workflow.md` | ☑ |
| 2 | IaC sub-agent prompt | `prompts/devops/01-iac-agent.md` | ☑ |
| 3 | Deploy wrapper: `--dry-run`, refuse apply if no TF module / `pending` | `tools/deploy_workload.py` | ☑ |
| 4 | Trace helper | `shared/utils/agent_trace.py` | ☑ |
| 5 | Unit tests (no AWS) | `tests/test_deploy_workload.py`, `tests/test_agent_trace.py` | ☑ |

---

## M4 checklist — Logger, CI drift, third workload

| # | Deliverable | Location | Done |
|---|-------------|----------|------|
| 1 | StructuredLogger | `shared/utils/structured_logger.py` | ☑ |
| 2 | CI codegen drift for every workload with specs | `tools/check_codegen_drift.py`, `.github/workflows/ci.yml` | ☑ |
| 3 | pytest import isolation (`importlib`) | `pytest.ini` | ☑ |
| 4 | Factory-align `web_events` (compute + quality/SFN codegen) | `workloads/web_events/` | ☑ |
| 5 | Docs: three-workload map | `docs/ARCHITECTURE.md`, `AGENTS.md` | ☑ |

---

## M5 checklist — MCP-first policy + enforced codegen

| # | Deliverable | Location | Done |
|---|-------------|----------|------|
| 1 | MCP-first / TF-fallback ownership table | `TOOL_ROUTING.md` | ☑ |
| 2 | Phase 5 MCP guardrails (catalog/LF/verify) | `docs/MCP_GUARDRAILS.md` | ☑ |
| 3 | Write guard (Cursor + Claude Code) | `.cursor/hooks.json`, `shared/codegen/write_guard.py` | ☑ |
| 4 | Renderer-only onboard prompts | `.cursor/commands/onboard-workflow.md`, `prompts/onboarding/` | ☑ |
| 5 | Unit tests for write guard | `tests/test_write_guard.py` | ☑ |

---

## M6 checklist — MCP wiring

| # | Deliverable | Location | Done |
|---|-------------|----------|------|
| 1 | Server registry (13 servers) | `tool-registry/servers.yaml` | ☑ |
| 2 | Generate Claude + Cursor MCP config | `tools/generate_mcp_config.py` → `.mcp.json`, `.cursor/mcp.json` | ☑ |
| 3 | Phase 0 health check | `tools/mcp_health_check.py` | ☑ |
| 4 | Registry ↔ JSON validator | `tools/validate_mcp_registry.py` | ☑ |
| 5 | Setup doc | `docs/MCP_WIRING.md` | ☑ |

---

## Phase checklist (Track A sandbox)

| Phase | Track A (this repo on AWS) | Status |
|---|---|---|
| 0 | Credentials, region `us-east-1`, Terraform CLI, budget | **Done** |
| 1a | Data-lake bucket `adop-datalake-199064440913-us-east-1` | **Done** |
| 1b | `tools/package_and_sync.py` — scripts, flat Glue deps, Lambda zips | **Done** |
| 2 | `terraform apply` (core pipeline + Redshift + OpenSearch + Redis + budget) | **Done** |
| 3 | Step Functions E2E (medallion + extensions) | **Done** (`phase3-extensions-3`) |
| 3b | PySpark + Iceberg E2E (Redshift-only SFN) | **Done** (`framework-e2e-v6-20260908-185515`) |
| 4 | Lake Formation LF-Tags via `register_catalog` | **Done** |
| 5 | Live `post_deployment_verifier` | **Done** (6 checks on Redshift-only path) |
| 6 | Same-day teardown (`terraform destroy`) | **Done** (2026-09-09) — state empty; KMS keys in 7-day deletion window |
| 7 | Cloud-native multi-provider framework design | **Not done** — after Track B |

---

## What the pipeline runs now (Redshift-only)

OpenSearch and Redis steps are **off the live advisory SFN** (hourly cost). The M2
`state_machine.json.j2` template can turn them back on per workload. Infra may still exist.

```
IngestToBronze → BronzeToSilver → SilverQualityGate → SilverToGold
  → GoldQualityGate → RegisterCatalog
  → RegisterRedshiftSpectrum → PostDeploymentVerify → Succeed
```

`web_events` is **PILOT-DISABLED** in `iac/terraform/main.tf`. Local pytest still runs.

---

## Next decisions

**Primary track — Tier A then Tier B (full ADOP-shaped factory):**

1. **Steps 1–8** — Tier A (AgentOutput, guard, SKILLS, codegen, MCP self-contained, workload #4).
2. **Steps 9–15** — Tier B (dual orchestration, Cedar, ontology, Gateway, workload #5).
3. **Redeploy sandbox** when ready for Gateway/MWAA/SFN E2E (`docs/DEMO_RUNBOOK.md`).

Sandbox is destroyed; steps 1–8 are files-only. Tier B step 13+ needs AWS for Gateway.
