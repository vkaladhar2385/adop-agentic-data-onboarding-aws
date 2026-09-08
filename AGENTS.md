---
project: adop-client-demo
stack: Python (Glue Python Shell, Step Functions), SQL, Terraform, AWS
status: track-a-deployed, agent-contract-layer-in-progress
agent_host: Cursor (primary), Claude Code (optional, Track B study)
---

# AGENTS.md — ADOP Agent Contract (Track A)

Bronze → Silver → Gold data pipeline orchestration for this repo. This file is the
**source of truth for agent behavior** when working in Cursor (or any agent host
that loads project instructions).

**Relationship to official ADOP:** The AWS sample in `reference/ADOP/` (Track B,
gitignored) is the reference *agent factory*. This repo (Track A) proves the
*pattern* on real AWS. This document adapts official ADOP guardrails to **our**
choices: Step Functions (not MWAA), Python Shell + pandas (not PySpark/Iceberg
yet), Terraform deploy (not MCP Phase 5). See `docs/TRACK_B.md` for the
comparison and Phase 7 roadmap.

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
```

**If ANY item is missing, ASK THE USER. Do not proceed to Phase 4 build.**

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
│   source.yaml, semantic.yaml, transformations.yaml, quality_rules.yaml, schedule.yaml
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

| Zone | Mutability | Quality gate | Format (Track A) |
|---|---|---|---|
| Bronze | Immutable | None | Raw / Parquet landing |
| Silver | Updatable | ≥ 0.80 | Parquet + Glue table |
| Gold | Updatable | ≥ 0.95 | Parquet star schema or rollups |

Gold shape is a Phase 1 discovery answer: star schema (`advisory_transactions`) vs hourly rollup + erasure index (`web_events`).

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
| `docs/ARCHITECTURE.md` | Artifact map, SFN flow, module layout |
| `docs/ADAPTATION_GAP.md` | Enterprise consulting backlog |
| `docs/EXTENDING_TO_NEW_SERVICES.md` | Adding Redshift / OpenSearch / Redis / new sinks |
| `docs/PILOT_FAILURES_AND_FIXES.md` | Known sandbox pitfalls |
| `.cursor/rules/adop-onboarding.mdc` | Path-scoped onboarding gate |

---

## Framework roadmap (not yet implemented)

These layers will turn Track A from a demo into a full agentic framework (Phase 7):

| Layer | Status | Location (planned) |
|---|---|---|
| JSON Schema contracts for configs | Not started | `contracts/v1/*.schema.json` |
| Deterministic codegen from specs | Not started | `shared/codegen/` |
| Tool registry (MCP / CLI routing) | Partial | Cursor `aws-mcp`; official 13-server set in Track B |
| Agent trace logs | Not started | `workloads/*/logs/trace_events.jsonl` |
| `/onboard-workflow` command | Not started | `.cursor/commands/` or docs prompt |

Until codegen exists, agents may hand-author artifacts **only after Phase 1 gate passes**, following patterns in existing workloads. Prefer editing specs (`config/*.yaml`) and shared utils over one-off script logic.

---

## Cost guardrails (sandbox)

- Default orchestration: **Step Functions + EventBridge** — no always-on MWAA
- Set AWS Budget alert (~$25) before sandbox apply
- Same-session `terraform destroy` when demo is done (`docs/STATUS.md` Phase 6)
- Hourly-risk resources: OpenSearch, Redshift, Redis — destroy or disable when not demoing

See `.cursor/rules/cursor-cost-efficiency.mdc` for token/context discipline when using agents on this repo.
