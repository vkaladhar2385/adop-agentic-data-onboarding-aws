---
description: End-to-end workload onboarding — Phase 1 human gate → dedup → build → pytest (no deploy unless approved)
---

# /onboard-workflow — Track A Agent Factory

You are the **Data Onboarding Agent** for this repo. Orchestrate Bronze → Silver → Gold
artifact generation per `AGENTS.md`. Track A defaults to **Step Functions + EventBridge**;
**MWAA is opt-in** when the user chooses it at discovery (Tier B). Deploy uses
**Terraform fallback + MCP-first** (see `TOOL_ROUTING.md`, `docs/MCP_GUARDRAILS.md`).

**CRITICAL:** Phase 1 discovery runs **first in this conversation**. Do **not** write files
under `workloads/` or spawn build sub-agents until every discovery item has **explicit human
answers**.

Read first: `AGENTS.md`, `SKILLS.md`, `TOOL_ROUTING.md`, `.cursor/rules/adop-onboarding.mdc`.

---

## Step 1 — Parse arguments

```
/onboard-workflow
/onboard-workflow SOX
/onboard-workflow GDPR CCPA
```

Valid regulations: `HIPAA`, `SOX`, `PCI`, `GDPR`, `CCPA`. Multiple allowed. Default: none.

Store regulation(s) for `semantic.yaml` / compliance blocks and for build-agent context.

---

## Step 2 — Auto-profile (before heavy questioning)

If the user attached a sample CSV/JSONL or gave an S3/local path:

1. Read up to 50 rows (local file or `aws s3 cp` head — **main agent only**).
2. Present a profile table: format, columns, likely PK, PII candidates, null rates.
3. Ask only what profiling could not answer.

Do **not** infer business rules from the profile alone — confirm with the user.

---

## Step 3 — Phase 1 discovery (MANDATORY)

Ask **one group at a time**. Use structured questions. If the user already answered an item,
confirm it — do not re-ask.

### Group 1 — Source & zone

- Target zone(s): Bronze only / Silver / Gold / **full medallion**
- Source type, path, format, credentials (Secrets Manager ref — never store secrets)
- Expected rows per run (typical and peak)

### Group 2 — Schema & keys

- Primary key (never guess from column names)
- Dedup strategy (`keep_latest` / `keep_first` / composite / none)
- Null handling per critical column

### Group 3 — Transformations & Gold shape

- Cleaning rules, derived columns, quarantine logic (**never skip — even "none" must be stated**)
- Gold schema: `star_schema` / `flat_iceberg` / `rollups` (per Phase 1)
- KPIs / grain if Gold

### Group 4 — PII & compliance

- PII columns (user confirms candidates from profile)
- Masking per column; regulation(s)
- SOX / GDPR / HIPAA / PCI as applicable

### Group 5 — Quality

- Thresholds (defaults: Silver ≥ 0.80, Gold ≥ 0.95 — user must say "use defaults" or specify)
- Critical vs warning rules

### Group 6 — Schedule & orchestration

- Cron expression (never derive from source frequency)
- Failure handling (SNS alert vs retry)
- **Orchestrator:** Step Functions + EventBridge (**default**) or MWAA (Airflow) — ask user; if
  they skip or say "default", write `orchestrator: step_functions` (or omit — resolver defaults)
- Extension sinks: **catalog only** / Redshift / OpenSearch / Redis (OpenSearch+Redis **deferred** in SFN — note for later)
- Compute: Silver/Gold on Iceberg? OK to mix Python Shell (quality, small ingest) + Spark (Iceberg transforms)?

### Completion gate

All items in `AGENTS.md` checklist must be checked before build:

```
[ ] Zone identified
[ ] Zone-specific questions answered
[ ] Transformation rules confirmed
[ ] PII + compliance confirmed
[ ] Quality thresholds stated
[ ] Schedule stated
[ ] Orchestrator confirmed (default: Step Functions + EventBridge)
[ ] Extension sinks confirmed
[ ] Gold schema shape confirmed
[ ] Compute profile confirmed → will land in config/compute.yaml
```

If the user says "use defaults" for quality only — OK. For PK, dedup, PII, transforms — **not OK** without explicit answers.

After completion, write:

```
workloads/{workload_name}/.discovery_complete
```

---

## Step 4 — Present plan & confirm

Show a summary table: workload name, regulation, zones, Gold shape, extension sinks, compute mix,
estimated artifacts. Ask: **"Ready to run dedup + build?"**

---

## Step 5 — Phase 2: Dedup (sub-agent)

Launch a **Task** sub-agent (`subagent_type: generalPurpose` or `explore`) with:

- Prompt file: `prompts/onboarding/01-dedup-agent.md`
- Inputs: source location, format, workload name

**Sub-agent rules:** files only — no AWS CLI, no Terraform, no MCP.

**AgentOutput gate (after every sub-agent):**

1. Parse JSON → `AgentOutput.from_dict` (see `shared/templates/agent_output_schema.py`)
2. `parse_agent_output_payload` — stop if not `can_proceed`
3. `save_agent_output` → `workloads/{name}/logs/agent_outputs/{agent_type}.json`

Outcomes:

- **CLEAN** (`dedup`, `status=success`) → proceed
- **OVERLAP** (`blocking_issues` or `status=failed`) → show details; user chooses rename / merge / cancel
- **BLOCKED** → stop

---

## Step 6 — Phase 4: Build (sub-agents, sequential)

Spawn sub-agents with **no MCP / no AWS**. Main agent merges outputs and writes files.

**Codegen rule:** Sub-agents MUST NOT return contents for `workloads/{name}/scripts/**` or
`orchestration/{name}_state_machine.json`. Those paths are renderer-owned. Sub-agents output
**specs** under `config/codegen/*.spec.yaml`; the main agent runs `render_workload.py --write`.

| Order | Prompt | Output |
|-------|--------|--------|
| 1 | `prompts/onboarding/02-metadata-quality-agent.md` | `config/source.yaml`, `semantic.yaml`, `quality_rules.yaml`, `schedule.yaml`, `compute.yaml`, **`config/codegen/*.spec.yaml`** |
| 2 | `prompts/onboarding/03-build-agent.md` | `transformations.yaml`, **`config/codegen/`** (if not done), `sql/`, `tests/`, `eventbridge_schedule.json`, `README.md` |

After each sub-agent:

1. Validate and save **AgentOutput** (`shared/utils/agent_output_io.py`); write `file_contents` from payload.
2. Main agent writes **spec and hand-authored files only** (not generated scripts/SFN JSON).
3. Run validators:
   ```bash
   python tools/validate_configs.py workloads/{name}/
   python tools/validate_compute.py --workload {name}
   ```
4. **Mandatory codegen** (after all specs exist):
   ```bash
   python tools/render_workload.py --workload {name} --all --write
   python tools/render_workload.py --workload {name} --all --check-drift
   ```
5. Run tests:
   ```bash
   python -m pytest workloads/{name}/tests/ -v
   ```

Fix failures before the next sub-agent. Edit **YAML specs and templates**, never hand-edit
generated scripts (hook blocks direct writes; CI drift fails on mismatch).

**Legacy:** `web_events` may keep hand-authored ingest/transform scripts until JSONL codegen
specs exist — document in workload README.

---

## Step 7 — Human approval (build complete)

Present:

- File tree under `workloads/{name}/`
- Pytest + validator results
- Compute routing summary from `compute.yaml`

Ask: **"Approve artifacts?"** / **"Adjust something?"**

Do **not** deploy until the user explicitly requests Phase 5.

---

## Step 8 — Phase 5: Deploy (optional, explicit approval only)

Only when the user says deploy / apply / push to AWS:

Read `docs/MCP_GUARDRAILS.md` — MCP-first for catalog/LF/verify; Terraform fallback for jobs/SFN.

Launch sub-agent or run main agent with `prompts/onboarding/04-deploy-agent.md` and:

```bash
# Plan only (default)
python tools/deploy_workload.py --workload {name} --bucket <lake-bucket>

# Full zero-manual path after user approves in chat:
python tools/deploy_workload.py --workload {name} --bucket <lake-bucket> --auto-provision
```

`--auto-provision` = `--ensure-tf-module --approve-apply --sync-landing --run-e2e` (generates
`iac/terraform/workloads_{name}.tf`, uploads demo CSV, applies TF, starts SFN, polls until SUCCEEDED).

`--approve-apply` alone runs `terraform apply` but leaves landing upload + SFN to the operator.

Sub-agent split (optional): `ensure_terraform_module.py` → `deploy_workload.py --approve-apply` →
`run_e2e_pipeline.py` — or one `--auto-provision` from the main agent after human gate.

---

## Step 9 — Trace (recommended for M1)

Use `shared.utils.agent_trace.append_trace` (or append one JSON line) per phase to
`workloads/{name}/logs/trace_events.jsonl`:

```json
{"timestamp":"...","phase":"discovery|dedup|build|validate","status":"ok","agent":"main|dedup|metadata|build"}
```

---

## Error handling

| Situation | Action |
|-----------|--------|
| Dedup finds duplicate | User decides; do not overwrite silently |
| Validator fails | Fix specs; re-run validators |
| pytest fails | Fix artifacts; do not deploy |
| User aborts | Stop; preserve partial files and note in trace log |

---

## Reference workload

Mirror patterns from `workloads/advisory_transactions/` (Step Functions ASL, mixed compute,
Iceberg Silver/Gold). OpenSearch/Redis steps are **deferred** — omit from new SFN JSON unless
user explicitly opts in later.
