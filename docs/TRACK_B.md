# Track B — Mastering the Official ADOP Framework

**Purpose:** Study how [aws-samples/sample-Agentic-Ai-Data-Operations](https://github.com/aws-samples/sample-Agentic-Ai-Data-Operations) actually works, phase by phase, and compare it to **Track A** (this repo's hand-built deploy). Track B is the prerequisite for **Phase 7** (your own cloud-native, multi-provider framework). Do not design Phase 7 until you can explain Track B from memory.

**Official repo (local clone for study):**
```text
# Canonical local path (sibling under Data-Engineering — not inside this repo):
C:\Vis\MyLearning\Data-Engineering\agentic-projects\ADOP

# Relative from this repo:
../agentic-projects/ADOP

# Fresh clone if needed:
git clone https://github.com/aws-samples/sample-Agentic-Ai-Data-Operations ^
  C:\Vis\MyLearning\Data-Engineering\agentic-projects\ADOP
```
Do not copy the reference tree into this repo. Styled docs: [aws-samples.github.io/sample-Agentic-Ai-Data-Operations](https://aws-samples.github.io/sample-Agentic-Ai-Data-Operations/).

---

## 1. Two tracks, one pilot

| | **Track A** (this repo) | **Track B** (official ADOP) |
|---|---|---|
| **Question it answers** | "Can we deploy and prove the pattern on real AWS?" | "How does AWS's reference agent framework generate and deploy pipelines?" |
| **How artifacts were made** | Human + Cursor guided; files hand-authored to close gaps | Claude Code agents + MCP + template codegen |
| **Orchestration default** | Step Functions + EventBridge (cost guardrail) | **Airflow on MWAA** (DAG in `workloads/*/dags/`) |
| **Glue runtime** | **Python Shell + pandas** (demo scale) | **PySpark + Iceberg** on Glue ETL (`glueetl`) |
| **Deploy path** | `terraform apply` + `tools/package_and_sync.py` | Phase 5: main agent deploys via **MCP** (Glue, LF, S3, catalog) |
| **AWS spend** | Yes — sandbox apply/destroy | **Zero** for study; optional if you run agents live |
| **Status** | Phases 0–5 done; Phase 6 (destroy) in progress | **This document + mastery checklist** |

Track A proved the **pattern** (medallion, gates, LF-Tags, verifier, IaC). Track B teaches the **machinery** (agents, MCP routing, codegen, human gates) that Phase 7 must generalize.

---

## 2. The ADOP mental model (what you must internalize)

Official ADOP is not "ChatGPT writes PySpark." It is a **governed multi-agent factory**:

```text
Human (rules, approvals)
    │
    ▼
Data Onboarding Agent (main conversation — has MCP)
    │
    ├── Phase 0: Health check + auto-detect AWS resources
    ├── Phase 1: Discovery questions (MANDATORY human gate)
    ├── Phase 2: Dedup — scan workloads/ for overlapping sources
    ├── Phase 3: Profile — Glue Crawler / Athena TABLESAMPLE
    ├── Phase 4: Build — spawn sub-agents (NO MCP; artifacts only)
    │       Metadata → Transformation → Quality → Orchestration (DAG)
    │       TEST GATE after each sub-agent
    ├── Human approves all artifacts
    └── Phase 5: Deploy — main agent uses MCP (Glue, LF, S3, KMS, catalog)

Separate command: /devops-workflow → DevOps Agent → Terraform/CDK + monitoring + runbook
```

**Three non-negotiable rules from official ADOP:**

1. **Sub-agents write files; main agent deploys.** Sub-agents never call AWS. See `TOOL_ROUTING.md` Step 1.
2. **Human-in-the-loop before codegen.** Phase 1 must have explicit answers for PK, dedup, PII, quality thresholds, schedule. See `CLAUDE.md` STOP gate.
3. **Deterministic codegen.** Scripts under `workloads/*/scripts/` and `dags/` are rendered from JSON-schema specs via `shared.codegen.renderer` — not free-form LLM edits. A PreToolUse hook blocks direct writes.

---

## 3. Official agent phases vs Track A phases

### Phase 0 — Environment / prerequisites

| Official ADOP (Track B) | Track A (this repo) |
|---|---|
| `MCP_GUARDRAILS.md` Phase 0: scan account for Glue role, S3 lake, KMS, LF-Tags, **MWAA** | Manual: `aws sts get-caller-identity`, budget alert, Terraform CLI |
| 13 MCP servers; 3 **REQUIRED**: `glue-athena`, `lakeformation`, `iam` | Cursor `aws-mcp` proxy + `aws-agent` profile (different stack) |
| Optional: Environment Setup Agent provisions base infra | We created `adop-datalake-199064440913-us-east-1` by hand / Terraform |
| Cedar / AVP policy store check | Not implemented in Track A |

**Study:** `MCP_GUARDRAILS.md` (Phase 0), `tool-registry/servers.yaml`, `prompts/environment-setup-agent/01-setup-aws-infrastructure.md`

---

### Phase 1 — Discovery (human gate)

| Official ADOP | Track A |
|---|---|
| Six question groups in `/onboard-workflow`: source, schema/keys, transforms, PII/compliance, quality, schedule | Same *information* captured in `config/*.yaml`, but authored directly (simulating Metadata Agent output) |
| Auto-profile first, then ask what profiling could not answer | `demo/data_generators/` + local CSV; no Glue Crawler in Track A |
| Regulation prefix: `/onboard-workflow SOX` routes Opus for compliance-critical build | SOX/GDPR baked into workload configs |

**Study:** `CLAUDE.md` (STOP gate), `.claude/commands/onboard-workflow.md` (Groups 1–6), `.claude/rules/00-zone-questions.md`

**Mastery check:** Can you list all six discovery groups without looking? Can you explain why "use defaults" is rejected unless the user explicitly says "use defaults" for each group?

---

### Phase 2 — Dedup + source validation

| Official ADOP | Track A |
|---|---|
| Scan `workloads/*/config/source.yaml` for overlapping S3 paths / PKs | Two workloads (`advisory_transactions`, `web_events`) designed not to overlap |
| `iam` MCP: `simulate_principal_policy` before touching source | Assumed sandbox admin SSO |

**Study:** `TOOL_ROUTING.md` → `local-file-scan`, `iam-simulate`

---

### Phase 3 — Profiling

| Official ADOP | Track A |
|---|---|
| Glue Crawler or Athena `TABLESAMPLE BERNOULLI(5)` via MCP | Local pandas read of synthetic CSV/JSONL |
| PII detection MCP (`pii-detection`) or `shared/utils/pii_detection_and_tagging.py` | `shared/utils/pii.py` + explicit columns in `semantic.yaml` |
| Present profile box to human before build | N/A (config pre-written) |

**Study:** `TOOL_ROUTING.md` → `glue-crawler`, `athena-tablesample`, `lake-formation-grant`

---

### Phase 4 — Build (sub-agents + test gates)

| Sub-agent | Official output | Track A equivalent |
|---|---|---|
| **Metadata Agent** | `config/source.yaml`, `semantic.yaml`, zone specs (`bronze.yaml`, `silver.yaml`, `gold.yaml`) | `workloads/<w>/config/{source,semantic}.yaml` |
| **Transformation Agent** | PySpark scripts from Jinja templates + SQL DDL | Python Shell scripts + `transformations.yaml` + `sql/**` (hand-maintained) |
| **Quality Agent** | `quality.yaml`, Glue DQDL / check scripts | `quality_rules.yaml`, `shared/utils/quality.py` |
| **Orchestration Agent** | **Airflow DAG** `dags/<workload>_pipeline.py` | **Step Functions ASL** `orchestration/*_state_machine.json` |
| **Ontology Agent** (opt-in) | `ontology.ttl`, `mappings.ttl` | Not built in Track A |
| **Test gate** | pytest after each sub-agent; orchestrator blocks on failure | `pytest workloads/ -v` (17+ tests) |

**Codegen contract (official only):**
- Specs validate against `contracts/v1/*.schema.json`
- Renderer: `shared.codegen.renderer.render()`
- Hook: `.claude/hooks/enforce_template_codegen.py`
- Every generated file has a 5-line header (spec_hash, template_id, …)

**Study:** `SKILLS.md` (sub-agent output format), `workloads/claims_v2/README.md`, `shared/codegen/` (renderer + templates)

**Mastery check:** Why must sub-agents call `submit_agent_output` instead of returning markdown?

---

### Phase 5 — Deploy (main conversation + MCP)

| Official ADOP | Track A |
|---|---|
| Main agent uploads scripts to S3, registers Glue jobs, applies LF-Tags via MCP | `tools/package_and_sync.py` + `terraform apply` |
| `--enable-data-lineage true` on every Glue ETL job | Lineage not wired in Track A Python Shell jobs |
| Post-deploy: Athena/Redshift query + CloudTrail lookup | `post_deployment_verifier` Lambda (9 checks) inside Step Functions |
| MWAA: `aws s3 sync workloads/{name}/dags/` to MWAA bucket | EventBridge Scheduler → Step Functions |

**Study:** `MCP_GUARDRAILS.md` Phase 5, `SKILLS.md` deploy box

---

### Phase 4b (official) — `/devops-workflow` (DevOps Agent)

Runs **after** onboard completes. Parallel sub-agents generate:

| Output | Official | Track A |
|---|---|---|
| IaC | Terraform / CDK / CloudFormation (user choice) | `iac/terraform/modules/workload_pipeline/` + extension modules |
| Monitoring | CloudWatch dashboards, SNS/Slack alerts | SNS topic + budget alarm in Terraform |
| Runbook | Operational doc from discovery answers | `docs/DEMO_RUNBOOK.md`, `docs/PILOT_FAILURES_AND_FIXES.md` |

**Study:** `.claude/commands/devops-workflow.md`, `prompts/devops-agent/iac-generator.md`

---

### Phase 6 — Teardown

| Official ADOP | Track A |
|---|---|
| Same-session destroy; verify no MWAA/Glue left running | `terraform destroy` + Cost Explorer next morning |
| Pilot plan warns: MWAA ~$350/mo if forgotten | OpenSearch/Redis/Redshift are the hourly risks — see `DEMO_RUNBOOK.md` |

---

## 4. Structural differences (the "adaptation" map)

These are the deliberate divergences between official ADOP and this repo. Each is a **design decision** Phase 7 must treat as a configurable capability, not an accident.

| Dimension | Official ADOP default | Track A choice | Implication for Phase 7 |
|---|---|---|---|
| **Orchestrator** | Airflow (MWAA) | Step Functions | `orchestrator` capability interface: `airflow` \| `step_functions` \| `eventbridge` |
| **Glue job type** | `glueetl` PySpark 4.x + Iceberg | `pythonshell` 3.9 + pandas + parquet | `compute` capability: `spark` \| `python_shell` \| `lambda` by data volume |
| **Silver/Gold format** | Iceberg on S3 Tables | Parquet paths + Glue tables | `storage` capability: `iceberg` \| `parquet` \| `delta` |
| **Code production** | Schema → Jinja renderer | Hand-authored + local runner | Codegen pipeline is core to ADOP; Track A skipped the factory |
| **Agent runtime** | Claude Code + 13 MCP servers | Cursor + aws-mcp + human edits | Phase 7: agent host + tool registry are pluggable |
| **Governance** | LF-Tags + Cedar/AVP + lineage flags | LF-Tags + quality gates + verifier | `governance` capability bundle |
| **Extensions** | Via MCP + Build templates | Hand modules: Redshift, OpenSearch, Redis | Same 6-step recipe in `EXTENDING_TO_NEW_SERVICES.md` |
| **Logging / audit** | `AgentTracer`, `trace_events.jsonl`, `decisions[]` | pytest + SFN execution history | Agent audit trail is first-class in official ADOP |

---

## 5. File layout comparison

### Official ADOP (`workloads/{name}/`)

```text
workloads/claims_v2/
├── config/
│   source.yaml, bronze.yaml, silver.yaml, gold.yaml, quality.yaml, dag.yaml
│   semantic.yaml, ontology.ttl, mappings.ttl
├── scripts/extract/, transform/, quality/, load/
├── dags/claims_v2_pipeline.py          ← Airflow
├── sql/bronze/, silver/, gold/
├── tests/unit/, integration/
├── logs/                               ← AgentTracer output (mandatory)
└── README.md
```

### Track A (`workloads/{name}/`)

```text
workloads/advisory_transactions/
├── config/
│   source.yaml, semantic.yaml, transformations.yaml, quality_rules.yaml, schedule.yaml
├── scripts/extract/, transform/, quality/, load/
├── orchestration/
│   advisory_transactions_state_machine.json   ← Step Functions
│   eventbridge_schedule.json
├── sql/bronze/, silver/, gold/
├── tests/unit/, integration/
├── memory/MEMORY.md                    ← ad-hoc agent memory (not official pattern)
└── README.md
```

**Key gap:** Track A has no `dags/`, no `logs/`, no zone-split YAML (`bronze.yaml` / `silver.yaml` / `gold.yaml`), no ontology TTL files.

---

## 6. MCP and tools (official)

Official ADOP wires **13 MCP servers** (see `tool-registry/servers.yaml`):

| Tier | Servers |
|---|---|
| **REQUIRED** | `glue-athena`, `lakeformation`, `iam` |
| **WARN** (CLI fallback) | `cloudtrail`, `redshift`, `core`, `s3-tables`, `pii-detection` |
| **OPTIONAL** | `sagemaker-catalog`, `lambda`, `cloudwatch`, `cost-explorer`, `dynamodb` |

No MCP for Step Functions, EventBridge, SNS — official ADOP falls back to AWS CLI for those. Track A uses Terraform for orchestration instead of agent-driven CLI.

**Cursor in this repo:** `~/.cursor/mcp.json` → `aws-mcp` proxy (different from official's 13-server local/gateway setup). Study official `.mcp.json` side by side.

---

## 7. Example workloads to study (official repo)

| Workload | Regulation | Gold shape | Why read it |
|---|---|---|---|
| `financial_portfolios` | SOX | Star schema | Closest to `advisory_transactions` |
| `healthcare_patients` | HIPAA | — | PHI masking patterns |
| `claims_v2` | HIPAA | Flat Iceberg | **Template codegen end-to-end** (best Track B lab) |
| `customer_master` | — | Star + ontology | Semantic layer + OWL |

Run locally (no AWS):
```bash
cd sample-Agentic-Ai-Data-Operations
pip install -r requirements.txt   # or uv sync per pyproject.toml
pytest workloads/ -v
```

---

## 8. What Track A added that official ADOP does not ship

These are **your** extensions — valuable for Phase 7 as optional capability modules:

| Addition | Location | Notes |
|---|---|---|
| Redshift Spectrum external schema | `modules/redshift_workload/` | Gold queryable from warehouse |
| OpenSearch bulk index | `modules/opensearch_workload/` | SigV4 via urllib, no `opensearch-py` |
| Redis quality-score cache | `modules/redis_workload/` | VPC + S3 gateway endpoint pattern |
| Live post-deploy verifier in SFN | `shared/utils/post_deployment_verifier.py` | Fails the state machine if checks fail |
| `package_and_sync.py` | `tools/` | Flat Glue deps, Lambda zips before apply |
| Step Functions + EventBridge | `orchestration/*.json` | Zero always-on orchestration cost |

Documented in `docs/EXTENDING_TO_NEW_SERVICES.md` and `docs/PILOT_FAILURES_AND_FIXES.md`.

---

## 9. Track B mastery checklist (do in order)

Use this as your study plan. Check boxes as you complete each item.

### Read-only (no AWS spend)

- [ ] Read official `README.md` (prompt examples, `/onboard-workflow`, `/devops-workflow`)
- [ ] Read `CLAUDE.md` — memorize the Phase 1 STOP gate and NEVER list
- [ ] Read `SKILLS.md` — draw the main agent + sub-agent diagram from memory
- [ ] Read `TOOL_ROUTING.md` — explain Step 1 (sub-agent vs main) without notes
- [ ] Skim `MCP_GUARDRAILS.md` Phase 0–5 headers
- [ ] Compare `workloads/claims_v2/` to `workloads/advisory_transactions/` in this repo (table in §5)
- [ ] Run `pytest workloads/ -v` in official clone — all pass
- [ ] Read `.claude/commands/onboard-workflow.md` — list the six discovery groups
- [ ] Read `.claude/commands/devops-workflow.md` — list DevOps outputs
- [ ] Inspect `shared/codegen/renderer.py` + one Jinja template — trace spec → script
- [ ] Read `contracts/v1/` — pick one schema and match it to a `config/*.yaml`

### Compare to Track A deploy lessons

- [ ] Read `docs/PILOT_FAILURES_AND_FIXES.md` — categorize which failures official ADOP would also hit vs Track A-only (Python Shell, SFN `ResultPath`, VPC)
- [ ] Read `docs/ADAPTATION_GAP.md` — separate "enterprise wiring" from "framework design"
- [ ] Read `docs/EXTENDING_TO_NEW_SERVICES.md` § "Generalizing beyond AWS"

### Optional hands-on (sandbox, ~$0 if generate-only)

- [ ] Clone official repo; open in Claude Code (not Cursor) with MCP configured per their README
- [ ] Run `/onboard-workflow SOX` with a **tiny synthetic CSV** — stop before Phase 5 Deploy
- [ ] Inspect generated `workloads/<new>/` — compare artifact shape to Track A
- [ ] Run `/devops-workflow <workload> terraform` — compare generated `.tf` to `iac/terraform/modules/workload_pipeline/`
- [ ] **Do not apply** unless you intend same-session destroy

### Exit criteria (ready for Phase 7)

You are done with Track B when you can explain, without notes:

1. The seven official phases (0–5 + devops) and what each produces
2. Why sub-agents cannot use MCP
3. How codegen + contracts enforce determinism
4. Three biggest differences between official ADOP and Track A (orchestration, Glue runtime, deploy path)
5. The smallest set of **capability interfaces** a multi-cloud framework would need (seed: object store, compute, orchestrator, catalog, governance, warehouse, search, cache — from `EXTENDING_TO_NEW_SERVICES.md`)

---

## 10. Bridge to Phase 7

Phase 7 asks: *"What's the smallest cloud-neutral framework that preserves ADOP's pattern?"*

Track B gives you the **reference implementation** to abstract from:

| ADOP concept | Phase 7 abstraction candidate |
|---|---|
| `config/source.yaml` + zone YAMLs | **Workload spec** (declarative, schema-validated) |
| Metadata / Transform / Quality / DAG sub-agents | **Build pipeline stages** (each emits spec slices) |
| `shared.codegen.renderer` | **Artifact factory** (provider-specific templates) |
| 13 MCP servers | **Tool registry** (capability → MCP/CLI/SDK adapter) |
| Phase 1 human gate | **Policy + discovery workflow** (unchanged) |
| Phase 5 MCP deploy | **Deploy adapter** (Terraform, CDK, or direct API) |
| `workloads/*/dags/` vs Track A ASL | **Orchestrator plugin** |
| Redshift / OpenSearch / Redis modules | **Sink plugins** over the same Gold contract |

Track A proves the **artifacts work on AWS**. Track B proves **how agents produce them**. Phase 7 combines both into your own design.

---

## 11. Quick reference links

| Resource | URL / path |
|---|---|
| Official repo | https://github.com/aws-samples/sample-Agentic-Ai-Data-Operations |
| Styled docs site | https://aws-samples.github.io/sample-Agentic-Ai-Data-Operations/ |
| Track A architecture | `docs/ARCHITECTURE.md` |
| Track A failures (paid lessons) | `docs/PILOT_FAILURES_AND_FIXES.md` |
| Enterprise adaptation (consulting SOW) | `docs/ADAPTATION_GAP.md` |
| Extension recipe | `docs/EXTENDING_TO_NEW_SERVICES.md` |
| Pilot phase checklist | `docs/STATUS.md` |
| Original pilot plan | `ADOP_Pilot_Plan.md` |

---

*Last updated: 2026-09-07. Track B doc created after Track A Phase 3–5 sandbox success (`phase3-extensions-3`).*
