---
project: adop-client-demo
stack: Python (Glue PySpark 4.x, Apache Iceberg), Step Functions, SQL, Terraform, AWS
status: track-a-deployed, agent-contract-layer-in-progress, pyspark-iceberg-migration-pending
agent_host: Cursor (primary), Claude Code (optional, Track B study)
---

# AGENTS.md — ADOP Agent Contract

Bronze → Silver → Gold data pipeline orchestration for this repo. This file is the
**source of truth for agent behavior** when working in Cursor (or any agent host
that loads project instructions).

**Relationship to official ADOP:** The AWS sample at
`C:\Vis\MyLearning\Data-Engineering\agentic-projects\ADOP` (Track B study clone,
sibling repo — see `docs/TRACK_B.md`) is the reference *agent factory*. This repo
adapts official ADOP guardrails with **our** orchestration and deploy choices: **Step Functions +
EventBridge** (not MWAA), **Terraform + package_and_sync** (not MCP Phase 5).
**Compute and storage:** Silver and Gold use **Apache Iceberg**. **Glue job type
per pipeline step** is declared in `config/compute.yaml` — agents may mix
**Glue ETL (PySpark)** and **Glue Python Shell** on the same workload when the
rules say so. See **Compute routing** below.

---

## STOP — Human-in-the-Loop Gate (Phase 1 Discovery)

**DO NOT GENERATE ANY PIPELINE CODE, SCRIPTS, CONFIGS, OR ORCHESTRATION JSON
UNTIL YOU HAVE EXPLICIT HUMAN ANSWERS FOR ALL ITEMS BELOW.**

The human provides the rules. The agent does NOT guess or infer them.

### Required questions (ask ALL before proceeding)

**Identify the zone first**, then ask zone-targeted questions:

- **Bronze** → source path, credentials, ingestion pattern, retention
- **Silver** → primary key, dedup strategy, null handling, business logic, transformations
- **Gold** → business outcome, KPIs, aggregation grain, schema choice (star vs rollup), BI tool

**Always ask regardless of zone:**

1. **PII / compliance** → which columns are PII? SOX / GDPR / HIPAA / PCI?
2. **Quality** → thresholds per zone (defaults: Silver ≥ 0.80, Gold ≥ 0.95), critical vs warning rules
3. **Scheduling** → cron expression, dependencies, failure handling (SNS alert vs retry)

**Auto-discover first** (local CSV/JSONL sample, Athena `TABLESAMPLE`, or Glue Crawler when AWS is wired) — then ask only what profiling could not answer. Present findings before questions.

### Completion checklist — ALL must have human-provided answers

```
[ ] Zone identified (Bronze, Silver, Gold, or full medallion)
[ ] Zone-specific questions answered
[ ] Transformation rules confirmed (derived columns, calculations, quarantine logic — NEVER skip even if "none needed")
[ ] PII columns and compliance framework confirmed by user
[ ] Quality thresholds explicitly stated (or user says "use defaults" for each zone)
[ ] Schedule explicitly stated by user
[ ] Orchestrator choice confirmed (default: Step Functions + EventBridge for this repo)
[ ] Extension sinks confirmed if any (catalog only vs Redshift / OpenSearch / Redis)
[ ] Gold schema shape confirmed (star schema, flat Iceberg, rollup — per ADOP Phase 1)
[ ] Compute profile confirmed (row volume, Iceberg zones, which steps may use Python Shell vs Spark)
```

**If ANY item is missing, ASK THE USER. Do not proceed to Phase 4 build.**

Ask explicitly during Phase 1:

> "Expected rows per run (typical and peak)? Silver/Gold on Iceberg? OK to use Python Shell for quality gates and small ingest, with Spark for Iceberg transforms?"

Record answers in `config/compute.yaml` → `profile` and `pipeline_steps`.

---

## Compute routing (Glue Python Shell vs Glue ETL)

**Source of truth:** `workloads/{name}/config/compute.yaml`

Agents MUST read this file (or create it during Phase 4 Metadata/DevOps) before
writing scripts or Terraform `glue_jobs`. **Never pick job type ad hoc.** Mixed
workloads (some steps Shell, some ETL) are normal and expected.

### Decision matrix

| Pipeline step | Default `job_type` | Use **glueetl** (PySpark 4.x) when | Use **pythonshell** when |
|---|---|---|---|
| **ingest_to_bronze** | `auto` (see rules) | Large files, JSONL complexity, Avro/Parquet conversion, Iceberg bronze, peak **> 50k rows/run** (unless user overrides) | Small landing files, simple copy/CSV parse, demo/sandbox cost guardrail, user confirms low volume |
| **bronze_to_silver** | **glueetl** | **Always when Silver format is Iceberg** (hard rule) | Never for Iceberg Silver — Shell cannot satisfy ADOP Iceberg write path |
| **silver_to_gold** | **glueetl** | **Always when Gold format is Iceberg** (hard rule) | Never for Iceberg Gold |
| **quality_silver / quality_gold** | **pythonshell** | User explicitly requests Spark DQ across full table at scale | Default: score via sidecar JSON, Athena sample, or pandas on aggregated metrics |
| **register_catalog / verifier** | **lambda** | N/A — not Glue | N/A |

### Hard rules (override user preference if violated)

1. **Iceberg transform ⇒ glueetl.** Any step that **writes** Silver or Gold Iceberg MUST be `glueetl` with `--datalake-formats=iceberg`.
2. **Lineage on every glueetl job.** `--enable-data-lineage=true` is non-negotiable for Spark jobs.
3. **One script, one job type.** Do not share a single script between Shell and ETL paths — fork entrypoints or use separate templates in codegen.
4. **Terraform follows compute.yaml.** `iac/terraform/main.tf` `glue_jobs` map MUST match `pipeline_steps.*.job_type` (codegen or agent validates before apply).
5. **Human confirms mixed compute.** If any step is `pythonshell` while others are `glueetl`, state the mix in the Phase 4 plan and get approval.

### Agent algorithm (Phase 4 build)

```
1. Read config/compute.yaml (create if missing from Phase 1 answers).
2. For each pipeline_steps entry:
     a. Apply routing.rules (Iceberg transform → glueetl, quality_* → pythonshell, etc.).
     b. Emit script in the matching style (PySpark vs pandas/boto3).
     c. Emit Terraform glue_jobs[job_key].job_type from pipeline_steps[job_key].job_type.
3. If compute.yaml and an existing script disagree on job_type → fix script OR update compute.yaml with user confirmation — never silently drift.
4. Run pytest for the workload before presenting the plan.
```

Example mixed workload: `workloads/advisory_transactions/config/compute.yaml`
(Spark transforms + Shell quality gates + Shell demo ingest).

### Legacy pilot note

`advisory_transactions` / `web_events` Terraform still deploys **all-pythonshell**
with Parquet paths (pre-migration). Their `compute.yaml` (when present) declares
the **target** routing; migration closes the gap to Terraform + PySpark scripts.

---

## Stack (storage + orchestration)

| Layer | Choice | Notes |
|---|---|---|
| **Compute** | **Per-step** in `config/compute.yaml` | `glueetl` and/or `pythonshell` on same workload |
| **Silver / Gold storage** | **Apache Iceberg** on S3 | Transform steps that write these zones MUST be `glueetl` |
| **Bronze** | Raw landing → Iceberg or staged Parquet | Ingest job type from compute routing |
| **Catalog** | AWS Glue Data Catalog (`glue_catalog.{db}.{table}`) | DDL in `sql/{bronze,silver,gold}/` with `table_type=ICEBERG` where applicable |
| **Orchestration** | Step Functions + EventBridge | No MWAA unless user explicitly opts in |
| **Deploy** | Terraform + `tools/package_and_sync.py` | `glue_jobs` derived from `compute.yaml` |
| **Logging** | `StructuredLogger` in every Glue script | Both job types |
| **Lineage** | `--enable-data-lineage=true` | **glueetl jobs only** (Shell has no lineage flag) |

### Glue ETL job defaults (`job_type: glueetl`)

Agents and Terraform MUST set these on `glueetl` jobs (see
`../agentic-projects/ADOP/TOOL_ROUTING.md`, `../agentic-projects/ADOP/prompts/.../01-fix-iceberg-glue.md`):

```hcl
# Terraform default_arguments (merge into aws_glue_job)
"--datalake-formats"              = "iceberg"
"--enable-data-lineage"           = "true"
"--enable-continuous-cloudwatch-log" = "true"
"--enable-metrics"                = "true"
"--job-language"                  = "python"
```

Job shape: `command.name = "glueetl"`, `glue_version = "4.0"`, `worker_type = "G.1X"`,
`number_of_workers = 2` (scale up only when user confirms volume in `compute.yaml`).

### Glue Python Shell job defaults (`job_type: pythonshell`)

Use for steps declared in `compute.yaml` (typically quality gates, small ingest):

```hcl
# Terraform — pythonshell branch in glue.tf
glue_version     = "3.0"
max_capacity     = 0.0625
command.name     = "pythonshell"
python_version   = "3.9"
# Package shared utils via --extra-py-files / --extra-files (see glue.tf pilot pattern)
# Do NOT set --datalake-formats or --enable-data-lineage (not supported / not applicable)
```

Shell scripts use **pandas + boto3** (or Athena API), read `transformations.yaml` /
`quality_rules.yaml` from `--extra-files`, and MUST NOT attempt Iceberg catalog writes.

### PySpark script contract (`job_type: glueetl` only)

Production scripts under `workloads/{name}/scripts/` MUST:

1. Use `GlueContext`, `Job`, `getResolvedOptions` (not bare pandas in the Glue path).
2. Read/write via **Glue catalog Iceberg tables** (`spark.table` / `writeTo`), not ad-hoc Parquet paths alone.
3. Implement transforms from `config/transformations.yaml` (same spec-driven rule as pilot).
4. Wire in `StructuredLogger` with agent name, workload, run id.
5. Include the 5-line codegen header once `shared/codegen/` exists; until then, comment `# stack: pyspark-iceberg`.

Reference: `../agentic-projects/ADOP/workloads/customer_master/scripts/transform/bronze_to_silver.py`.

### Python Shell script contract (`job_type: pythonshell` only)

1. Use `shared/utils/s3_io.py` + pandas (pilot pattern) or Athena/boto3 for reads.
2. Load rules from `--extra-files` config YAMLs.
3. Write outputs only to formats Shell supports (Parquet paths, CSV sidecars, JSON scores) — **not** Iceberg table commits.
4. Quality gates write score sidecar to S3 for Step Functions branching.

### Local development vs production

| Environment | glueetl steps | pythonshell steps |
|---|---|---|
| **Unit tests** | pyspark local or pandas fixture mirroring config rules | pandas fixtures + `quality.py` |
| **Local demo** | optional `local_runner.py` until Spark local wired | `run_local_pipeline.py` |
| **AWS** | PySpark + Iceberg per compute.yaml | Shell per compute.yaml |

Do not write Silver/Gold Iceberg from Python Shell. Do not pick job type without updating `compute.yaml`.

### NEVER do these

- NEVER guess dedup strategy from column names
- NEVER infer null handling from data observations alone
- NEVER assume quality thresholds without the user stating them (or explicitly saying "use defaults")
- NEVER generate a schedule from source frequency — ask
- NEVER assume PII columns from names alone — ask user to confirm
- NEVER skip the transformation question — even for type casts and masking, ask about derived columns and business logic
- NEVER deploy to AWS (`terraform apply`, sync scripts) without explicit user approval
- NEVER leave MWAA, OpenSearch, Redshift, or Redis running unattended in sandbox accounts

You MAY profile data and PRESENT observations, then MUST ask: "How would you like to handle these?"

---

## Security rules (non-negotiable)

1. **No hardcoded secrets** — Secrets Manager, GitHub OIDC, or env vars only
2. **No infrastructure identifiers in source** — no account IDs, VPC IDs, or bucket names in scripts committed to git (Terraform variables / tfvars handle runtime wiring)
3. **Encryption** — zone-scoped KMS CMKs (rotation on) for Bronze / Silver / Gold
4. **PII governance** — classify in `semantic.yaml`, mask/suppress in Silver/Gold transforms, apply LF-Tags in `register_catalog.py`
5. **Bronze immutability** — never modify Bronze after ingestion
6. **Quality gates block promotion** — no bypassing Silver or Gold gates
7. **Least privilege IAM** — scoped roles per module (`workload_pipeline`, extension modules)
8. **Audit** — CloudTrail for deploy operations; post-deploy verifier must pass before declaring success

---

## Agent behavior protocol

| Phase | Name | Agent may | Agent must not |
|---|---|---|---|
| 0 | Prerequisites | Verify AWS profile, budget, pytest baseline | Deploy or spend without user intent |
| 1 | Discovery | Ask questions, profile sample data | Generate workload artifacts |
| 2 | Dedup | Scan `workloads/*/config/source.yaml` for overlapping paths/keys | Skip overlap check |
| 3 | Profile | Present schema/null/PII observations | Infer business rules from profile |
| 4 | Build | Write specs + scripts + tests under `workloads/{name}/` | Apply Terraform or touch AWS |
| 5 | Deploy | Run `package_and_sync.py`, `terraform plan/apply` **after approval** | Deploy without verifier step |
| 6 | Verify | Run post-deploy verifier (Lambda or local checks) | Mark deploy complete if checks fail |

### Sub-agent separation (build vs deploy)

Even when one Cursor session performs all steps:

- **Build phases (1–4):** produce files only — `config/`, `scripts/`, `orchestration/`, `sql/`, `tests/`
- **Deploy phase (5):** Terraform + sync + CI — only after human approves the artifact plan

Reference workloads: `advisory_transactions` (SOX, star schema, extensions),
`web_events` (GDPR, rollups).

---

## Folder convention

```
workloads/{name}/
├── config/
│   source.yaml, semantic.yaml, transformations.yaml, quality_rules.yaml
│   schedule.yaml, compute.yaml          # compute.yaml = Glue job_type per step
├── scripts/
│   extract/, transform/, quality/, load/
├── orchestration/
│   {name}_state_machine.json, eventbridge_schedule.json
├── sql/
│   bronze/, silver/, gold/
├── tests/
│   unit/, integration/
├── logs/                    # (planned) agent trace output — not yet mandatory in Track A
└── README.md

shared/utils/                # quality.py, pii.py, post_deployment_verifier.py
iac/terraform/               # DevOps Agent output — modules per workload + extensions
tools/package_and_sync.py    # Glue scripts + Lambda zips before apply
```

---

## Data zones

| Zone | Mutability | Quality gate | Format |
|---|---|---|---|
| Bronze | Immutable | None | Raw landing → Iceberg or staged files |
| Silver | Updatable | ≥ 0.80 | **Iceberg** on S3 (always) |
| Gold | Updatable | ≥ 0.95 | **Iceberg** — schema per use case |

Gold shape is a Phase 1 discovery answer (official ADOP options):

- **Star schema** — reporting / BI (`advisory_transactions` target)
- **Flat Iceberg** — analytics / ML (`claims_v2` in reference ADOP)
- **Rollups + side indexes** — streaming / GDPR erasure (`web_events` target)
- **Iceberg + DynamoDB** — low-latency API serving (opt-in extension)

---

## Deploy path (Track A — not official MCP)

After Phase 4 artifacts pass `pytest workloads/{name}/ -v`:

1. `python tools/package_and_sync.py` — sync Glue scripts, build Lambda zips
2. `terraform plan` / `terraform apply` in `iac/terraform/` — user approval required
3. Trigger Step Functions execution or wait for EventBridge schedule
4. **Post-deploy verifier** — `shared/utils/post_deployment_verifier.py` (9 checks in extended pipeline); deployment is not complete until all pass

Optional extensions (per workload): Redshift Spectrum, OpenSearch, Redis — see `docs/EXTENDING_TO_NEW_SERVICES.md`.

---

## Mandatory post-deploy sequence

After deploy verification passes, offer (do not skip):

1. **E2E pipeline test** — full Step Functions run on AWS with row-count / Athena spot-check
2. **DevOps follow-up** — dashboards, SNS routing, runbook updates (`docs/DEMO_RUNBOOK.md`)

---

## Key files for agents

| File | Read when |
|---|---|
| `AGENTS.md` | Every session — this contract |
| `docs/TRACK_B.md` | Comparing to official ADOP / Phase 7 planning |
| `../agentic-projects/ADOP/` | Track B study clone (CLAUDE.md, SKILLS.md, codegen, workloads) |
| `docs/ARCHITECTURE.md` | Artifact map, SFN flow, module layout |
| `docs/ADAPTATION_GAP.md` | Enterprise consulting backlog |
| `docs/EXTENDING_TO_NEW_SERVICES.md` | Adding Redshift / OpenSearch / Redis / new sinks |
| `docs/PILOT_FAILURES_AND_FIXES.md` | Known sandbox pitfalls |
| `.cursor/rules/adop-onboarding.mdc` | Path-scoped onboarding gate |

---

## Framework roadmap (not yet implemented)

These layers turn this repo into a full agentic framework (Phase 7):

| Layer | Status | Location (planned) |
|---|---|---|
| **Compute routing spec** | **Draft** (example workload) | `workloads/*/config/compute.yaml` |
| **PySpark + Iceberg migration** (pilot workloads) | In progress | scripts + Terraform aligned to `compute.yaml` |
| JSON Schema contracts for configs | Not started | `contracts/v1/*.schema.json` (include `compute.schema.json`) |
| Deterministic codegen from specs | Not started | `shared/codegen/` (PySpark + Iceberg Jinja templates) |
| `StructuredLogger` | Not started | `shared/utils/structured_logger.py` |
| Tool registry (MCP / CLI routing) | Partial | Cursor `aws-mcp`; official 13-server set in Track B |
| Agent trace logs | Not started | `workloads/*/logs/trace_events.jsonl` |
| `/onboard-workflow` command | Not started | `.cursor/commands/` or docs prompt |

Until codegen exists, agents may hand-author PySpark scripts **only after Phase 1 gate
passes**, following `../agentic-projects/ADOP/workloads/*/scripts/`. Prefer editing specs
(`config/*.yaml`) over embedding business logic in scripts.

### PySpark + Iceberg migration sequence (pilot workloads)

1. Update `iac/terraform/modules/workload_pipeline/glue.tf` — Iceberg defaults, drop Python Shell-only `--extra-py-files` pattern for Spark jobs.
2. Flip `glue_jobs` in `main.tf` from `pythonshell` → `glueetl` for ingest + transform steps.
3. Rewrite `scripts/transform/*.py` and `scripts/extract/*.py` as PySpark (keep `local_runner` for unit tests or replace with Spark local tests).
4. Align `sql/**/*.sql` DDL with live Iceberg tables; register via `register_catalog.py`.
5. Re-run `pytest`, `package_and_sync`, sandbox E2E, post-deploy verifier.

---

## Cost guardrails (sandbox)

- Default orchestration: **Step Functions + EventBridge** — no always-on MWAA
- Set AWS Budget alert (~$25) before sandbox apply
- Same-session `terraform destroy` when demo is done (`docs/STATUS.md` Phase 6)
- Hourly-risk resources: OpenSearch, Redshift, Redis — destroy or disable when not demoing

See `.cursor/rules/cursor-cost-efficiency.mdc` for token/context discipline when using agents on this repo.
