# Phase 7 — Multi-Platform Factory (decision record)

**Status:** 7.0 backbone COMPLETE (2026-10-01) · 7.1 Azure next
**Branch:** `feature/multi-platform-factory`
**Goal:** The ADOP factory produces the same workload SKU on **any** target —
AWS, Azure, GCP, **Databricks**, and **Snowflake** — selected entirely by the
client's **specs/config**, not by forking the pipeline.

This is a decision record. The live checklist is [`PHASE_7_TODO.md`](PHASE_7_TODO.md).

---

## 1. Reframe: platform profiles, not "another cloud"

Databricks and Snowflake are **not** a fourth/fifth cloud. They are **platform
profiles** that run *on top of* a host cloud (AWS/Azure/GCP). Snowflake in
particular is warehouse-centric and does not use a Glue/Spark job model at all.

```text
Discovery + specs (cloud-neutral, unchanged)
        v
platform.yaml  ->  profile: aws | azure | gcp | databricks | snowflake
        v
Capability resolution (store, table-format, transform-engine, catalog, govern, orchestrate, sink)
        v
Provider template pack  ->  rendered artifacts  ->  deploy adapter
```

The **factory process** (HITL -> specs -> render -> test -> deploy) is one SKU.
Only the **platform pack** changes.

---

## 2. Agreed decisions

| # | Decision | Resolution |
|---|----------|------------|
| 1 | Snowflake scope | **Mode A (Gold sink) default**; flip to Mode B (full platform) per `platform.yaml` on request |
| 2 | Table format | **Iceberg default**; `delta` selectable per profile |
| 3 | Repo layout | **Single repo** with isolated `platform-packs/<profile>/`; promote to submodule only if it bloats |
| 4 | Profile priority | **Azure-native -> GCP-native -> Databricks -> Snowflake** |
| 5 | "Any cloud" definition | Driven 100% by client specs/config; no hardcoded per-cloud logic in `workloads/` |

## 3. What stays universal (the actual product — never forked)

- Phase 1 HITL discovery gate (`AGENTS.md`)
- Business specs: `source/semantic/transformations/quality_rules/schedule.yaml`
- Medallion **logical** zones Bronze -> Silver -> Gold and their quality-gate contract
- Pipeline **graph** (ingest -> transform -> quality -> promote)
- Codegen discipline (spec -> render -> drift check), build-vs-deploy separation

If this layer is preserved, we have one multi-platform factory — not N forks.

---

## 4. The three resolvers that make "client's choice" work

Everything reduces to three provider-resolved axes, declared in config and
validated by `tools/validate_platform.py`:

1. **TableFormat** — `iceberg | delta | native`
2. **TransformEngine** — `spark | snowpark | sql`  ← this is what lets Snowflake exist without being a Glue clone
3. **DeployAdapter** — `terraform | bundle | snowflake_cli | mcp`

The current AWS hard rule *"Iceberg Silver/Gold => glueetl"* generalizes to a
resolution matrix:

| lake_format | transform_engine | resolves to |
|-------------|------------------|-------------|
| iceberg | spark | Glue ETL (aws) / Dataproc (gcp) / Synapse or Databricks Job |
| delta | spark | Databricks Job / Synapse |
| iceberg | snowpark | Snowflake external Iceberg + Snowpark |
| native | sql | Snowflake managed tables + SQL tasks |

---

## 5. Capability interface (minimum set for "any platform")

```text
 1. ObjectStore      zone-scoped read/write
 2. TableFormat      iceberg | delta | native
 3. TransformEngine  spark | snowpark | sql
 4. BatchPython      quality gates, small ingest
 5. Catalog          register tables/columns/tags
 6. Governance       PII tags, grants, masking
 7. Orchestrator     DAG with conditional quality branches
 8. Observability    structured logs + lineage hook
 9. Sink (optional)  warehouse | search | cache | reverse-ETL
10. DeployAdapter    terraform | bundle | snowflake_cli | mcp
```

Each **profile** implements these 10. `BatchPython`, quality scoring, and the
orchestration *graph* are shared/common — only I/O and runtime shell change.

---

## 6. Repo layout (single repo, partitioned)

```text
ADOP/
  workloads/{name}/config/
    platform.yaml         # NEW - profile + host_cloud + lake_format + capabilities
    compute.yaml          # capability -> engine resolver (adds transform_engine)
    source/semantic/transformations/quality_rules/schedule.yaml   # cloud-neutral
  platform-packs/         # NEW - all cloud weight lives here
    aws/        { templates/, terraform/, deploy/ }
    azure/      { templates/, terraform/, deploy/ }
    gcp/        { templates/, terraform/, deploy/ }
    databricks/ { templates/, bundles|terraform/, deploy/ }
    snowflake/  { templates/, terraform/, deploy/ }
  shared/
    templates/common/     # quality, PII, logger, orchestration graph (cloud-neutral)
    codegen/              # renderer, drift validator (profile-aware resolver)
  contracts/v1/           # + platform.spec.schema.json, capability schema
  tools/
    render_workload.py    # --profile selects pack (defaults to aws)
    validate_platform.py  # NEW - capability resolution rules per profile
    deploy_workload.py    # --profile routes to pack deploy adapter
```

**Health guardrails for single-repo:**
- **Lazy packs** — render/deploy load only the active profile's pack; CI matrix tests packs independently.
- **Hard import boundary** — `workloads/` and `shared/` must never import `platform-packs/*` (lint-enforced).
- **Promote later** — if `platform-packs/` bloats, it lifts to a submodule with zero change to `workloads/`.

---

## 7. Orchestration: one graph, many exporters

A cloud-neutral `orchestration.graph` (nodes = steps, edges = gates) renders to:

- `*_state_machine.json` (AWS Step Functions)
- `databricks_workflow.json` (Databricks Workflows)
- `snowflake_tasks.sql` (Snowflake Tasks + Streams)
- `composer_dag.py` / ADF / Durable Functions (GCP / Azure)

We do **not** force Step Functions semantics onto Tasks/Workflows — same graph
shape, different exporter.

---

## 8. Rollout phases and gates

Every phase has three gates. Parallel sub-agents compress Gate A/B only;
Gate C is calendar-bound on sandbox access.

| Gate | Meaning | Needs a cloud account? |
|------|---------|------------------------|
| **A — Build** | specs + templates + render | No |
| **B — Plan** | `terraform plan` / bundle validate / SQL compile; unit tests | No (free auth at most) |
| **C — Live E2E** | real pipeline run, row-count/Athena-style spot check | **Yes — blocked until sandbox** |

| Phase | Deliverable | Gate C blocker |
|-------|-------------|----------------|
| **7.0** | Backbone: schema + `platform.yaml` + resolver + `validate_platform.py` + AWS pack + parity | None (AWS verifiable now) |
| **7.1** | Azure-native pack | Azure sandbox |
| **7.2** | GCP-native pack | GCP sandbox |
| **7.3** | Databricks pack (Iceberg or Delta) | Databricks workspace |
| **7.4** | Snowflake Mode A (Gold sink) | Snowflake account (partial on AWS Iceberg) |
| **7.5** | Snowflake Mode B (full platform, on request) | Snowflake account |

**7.0 is the whole game:** refactor AWS into a pack with **byte-identical**
rendered output. If parity breaks, the abstraction is wrong — fix it there,
cheaply, before any new cloud.

---

## 9. Sandbox constraint (current reality)

Only an **AWS** sandbox exists today. Azure/GCP/Databricks/Snowflake accounts
must be set up (own trials or Perficient's governed sandbox). Therefore every
non-AWS pack is built to **Gate B** (render + plan + unit test, zero spend) and
its **Gate C** checklist is parked until the account lands. No agent can
compress Gate C — it is procurement/calendar, not build time.

---

## 10. 7.0 scope decisions (risk-based, this branch)

1. **Templates move into `platform-packs/aws/templates/`.** Drift is a
   byte-identical re-render keyed on `template_hash` (hash of template *source
   bytes*), so relocating identical bytes + a profile-aware resolver keeps every
   workload drift-clean. Fully verifiable on AWS/laptop.
2. **AWS Terraform modules stay in `iac/terraform/` for 7.0.** The live AWS
   deploy path is the *only* path we can verify end-to-end; physically moving
   `modules/workload_pipeline/` would break the `workloads_*.tf` generator
   (`shared/deploy/workload_tf.py`) and the green deploy path with no way to
   re-verify without a re-apply. The generator becomes **profile-aware** so
   Azure/GCP/Databricks/Snowflake packs emit into their own pack dirs; the
   physical AWS TF relocation is deferred to a later, separately-tested step.
3. **Default `profile: aws`.** Absent or `aws` profile resolves to today's exact
   paths/behavior — zero behavior change for existing workloads.
4. **`compute.yaml` keeps its existing `profile:` block** (row volume/format).
   The platform selector lives in the new `platform.yaml` to avoid key collision.

---

## 11. Known baseline (start of 7.0)

- `tests/`: 126 passed, **1 pre-existing failure** (`test_switch_mcp_mode.py::test_gateway_target_names_from_manifest`, 13-vs-14 MCP targets) caused by already-modified `.mcp.json` — unrelated to Phase 7.
- `workloads/`: 56 passed.
- `check_codegen_drift.py`: clean. `validate_configs.py`: PASS (30 config, 25 codegen). `validate_compute.py`: PASS.

7.0 must keep all of the above green (the one pre-existing failure excepted).
