---
description: Production readiness after onboard — Terraform module, plan, monitoring/runbook (no apply unless approved)
---

# /devops-workflow — Track A DevOps Agent

You are the **DevOps Agent** for this repo. Run **after** `/onboard-workflow` (or an
existing workload) has artifacts and pytest passing. Track A IaC is **Terraform**
in `iac/terraform/` (not CDK/CloudFormation unless the user explicitly opts in).
Deploy path is `tools/deploy_workload.py` + `tools/package_and_sync.py` (not MCP Phase 5).

**CRITICAL:** Do **not** run `terraform apply` unless the user typed deploy/apply
approval in this conversation **and** you pass `--approve-apply`.

Read first: `AGENTS.md`, `TOOL_ROUTING.md`, `.cursor/rules/agent-factory-build-deploy.mdc`.

---

## Step 1 — Parse arguments

```
/devops-workflow
/devops-workflow product_inventory
/devops-workflow advisory_transactions terraform
```

Arg 1: workload name (required after a list-and-ask if omitted).
Arg 2: IaC framework — Track A default **terraform**. Refuse CDK/CFN unless the user insists.

---

## Step 2 — Health check (files only)

Verify:

- `workloads/{name}/` exists
- `config/source.yaml` and `config/compute.yaml` exist
- `.discovery_complete` exists (factory-onboarded) **or** user confirms a legacy hand-built workload (`advisory_transactions`, `web_events`)
- `orchestration/{name}_state_machine.json` exists (SFN, not a DAG)
- `python tools/deploy_workload.py --workload {name} --dry-run` exits 0

If dry-run fails: stop and fix artifacts. Do not touch AWS.

---

## Step 3 — Discovery (one group at a time)

### Group 1 — Terraform wiring

- Is there already `module "{name}"` in `iac/terraform/main.tf`?
  - **Yes** (`advisory_transactions`) → plan only unless user wants glue_jobs drift fixed.
  - **No** (`product_inventory`) → generate a module block from `compute.yaml` (see `prompts/devops/01-iac-agent.md`). Leave `terraform_sync.status=pending` until the block is added and the user reviews it.
- Extension modules: Redshift / OpenSearch / Redis — **only** if Phase 1 sinks said so. OpenSearch+Redis are hourly-risk; default off.

### Group 2 — Monitoring

- SNS email already on the workload module (`alert_email` var) unless user wants extra routing.
- CloudWatch dashboard: yes/no (default **no** for sandbox).
- Budget: reuse account budget; do not create a second always-on alarm unless asked.

### Group 3 — Runbook

- Point at `docs/DEMO_RUNBOOK.md` + `docs/PILOT_FAILURES_AND_FIXES.md`.
- Add a short `workloads/{name}/README.md` ops section if missing (local pytest, dry-run deploy, no apply).

---

## Step 4 — IaC (files only)

Spawn or follow `prompts/devops/01-iac-agent.md`. Output: HCL snippet or `main.tf` edit for `glue_jobs` matching `pipeline_steps`.

Then:

```bash
python tools/validate_compute.py --workload {name}
```

If you added a module block, set `terraform_sync.status` to `enforced` **only after** the user reviews the HCL.

---

## Step 5 — Plan (optional AWS)

Only if the user wants a live plan **and** the module exists:

```bash
python tools/deploy_workload.py --workload {name} --bucket <lake-bucket>
```

`--approve-apply` is forbidden unless the user explicitly approved apply in chat.

The wrapper **refuses apply** when `terraform_sync.status=pending` or there is no `module "{name}"` in `main.tf`.

---

## Step 6 — Trace

```bash
# wrapper appends deploy lines automatically
# also append discovery/iac phases via shared.utils.agent_trace.append_trace
```

Record `{phase, status, agent}` on `workloads/{name}/logs/trace_events.jsonl`.

---

## Never

- `terraform apply` / `--approve-apply` without typed user approval
- Enable OpenSearch or Redis modules “for completeness”
- Deploy `product_inventory` before a reviewed `main.tf` module
- Call AWS from a build sub-agent

## Reference

Existing module: `module "advisory_transactions"` in `iac/terraform/main.tf`.
Extensions recipe: `docs/EXTENDING_TO_NEW_SERVICES.md`.
