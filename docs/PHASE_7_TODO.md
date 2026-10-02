# Phase 7 — Multi-Platform Factory: TODO tracker

Living checklist. Tick items as gates pass. Decision record:
[`PHASE_7_MULTI_PLATFORM.md`](PHASE_7_MULTI_PLATFORM.md).

Legend: `[ ]` todo · `[x]` done · `[~]` in progress · `[B]` blocked on sandbox (Gate C)

---

## Phase 7.0 — Abstraction backbone (AWS-only, fully verifiable now)

- [x] 7.0-a Decision record `docs/PHASE_7_MULTI_PLATFORM.md`
- [x] 7.0-a Tracking doc `docs/PHASE_7_TODO.md` (this file)
- [x] 7.0-b Platform + capability JSON Schema in `contracts/v1/` (`platform.schema.json`)
- [x] 7.0-b `platform.yaml` added to all 5 workloads (`profile: aws`)
- [x] 7.0-b `validate_configs.py` picks up `platform.yaml` (35 config PASS)
- [x] 7.0-c Profile-aware template resolver in `shared/codegen/renderer.py` (defaults to aws)
- [x] 7.0-c Relocate AWS templates -> `platform-packs/aws/templates/` (git mv, history kept)
- [x] 7.0-c `profile` threaded through `render_workload.py` + `verify_artifact` (from `platform.yaml`)
- [x] 7.0-d `transform_engine` lives in `platform.yaml` capabilities (single source)
- [x] 7.0-d `tools/validate_platform.py` with per-profile resolution rules (+ 9 unit tests)
- [x] 7.0-e Import-boundary lint `tools/check_import_boundaries.py` (+ 4 unit tests; renderer allowlisted)
- [x] 7.0-f Parity gate: re-render all workloads, drift byte-identical (verified)
- [x] 7.0-f Full suite green (tests + workloads + drift + validators), baseline preserved
- [x] 7.0-f New gates wired into CI (`validate_platform`, `check_import_boundaries`)

**Gate for 7.0 complete:** ✅ **PASSED (2026-10-01)**
- pytest: 195 passed, 1 pre-existing fail (MCP target count, unrelated) — +13 new Phase 7 tests, no regression
- `check_codegen_drift`: clean (parity byte-identical after template relocation)
- `validate_configs`: PASS (35 config, 25 codegen) · `validate_compute`: PASS
- `validate_platform`: PASS (5 workloads) · `check_import_boundaries`: PASS (114 files)

---

## Phase 7.1 — Azure-native pack (Synapse Spark + ADLS Gen2 + ADF)

- [x] 7.1-a Scaffold: `platform-packs/azure/{templates,terraform,deploy}/` + README + deploy adapter
- [x] 7.1-b Templates: ingest (ADLS), bronze→silver + silver→gold (Synapse PySpark + Iceberg), quality (python) — render Gate A
- [x] 7.1-c Orchestration exporter: `adf_pipeline.json.j2` (ADF pipeline, quality-gated promotion)
- [x] 7.1-d Terraform skeleton (azurerm: RG, ADLS Gen2, Synapse workspace+pool, ADF) — `terraform validate` PASS (Gate B)
- [x] 7.1-b Unit tests: `tests/test_azure_pack.py` (+12, render + Synapse-not-Glue + ADF JSON)
- [x] 7.1-e `workloads/azure_demo/` — profile azure, orchestrator adf, full render via `render_workload --all --write`
- [x] 7.1-e ADF routing: `resolve_orchestration_artifacts` + `render_workload` adf_pipeline synthesis + write_guard
- [x] 7.1-e `validate_compute` skips AWS TF drift for non-aws profiles
- [x] 7.1-e Push skill: `.cursor/skills/push-both-remotes/` (origin + perficient)
- [B] 7.1-f C Live E2E on Azure sandbox (1 workload) — **blocked: no Azure account**

**7.1 Gate A+B status:** ✅ **COMPLETE (2026-10-01)**
- `azure_demo` renders Synapse scripts + ADF pipeline; drift clean
- pytest 209 passed (+14), 1 pre-existing MCP failure unrelated
- azurerm `terraform validate` passes · all validators PASS
- Gate C parked until Azure sandbox

## Phase 7.2 — GCP-native pack (Dataproc + GCS + Composer)

- [x] 7.2-a Composer orchestrator routing + `composer_dag` synthesis in `render_workload`
- [x] 7.2-b `platform-packs/gcp/` templates (Dataproc PySpark, GCS ingest, Composer DAG)
- [x] 7.2-c `platform-packs/gcp/terraform/` (GCS + Dataproc) — `terraform validate` PASS
- [x] 7.2-d `workloads/gcp_demo/` full render e2e + `tests/test_gcp_pack.py`
- [B] 7.2-e C Live E2E on GCP sandbox — **blocked: no GCP account**

**7.2 Gate A+B status:** ✅ **COMPLETE (2026-10-01)**

## Phase 7.3 — Databricks pack

- [x] 7.3-a Workflows orchestrator routing + `databricks_workflow` synthesis in `render_workload`
- [x] 7.3-b `platform-packs/databricks/` templates (UC PySpark, Delta default, Workflows JSON)
- [x] 7.3-c `platform-packs/databricks/terraform/` (databricks_job) — `terraform validate` PASS
- [x] 7.3-d `workloads/databricks_demo/` full render e2e + `tests/test_databricks_pack.py`
- [B] 7.3-e C Live E2E on Databricks workspace — **blocked: no workspace**

**7.3 Gate A+B status:** ✅ **COMPLETE (2026-10-01)**

## Phase 7.4 — Snowflake Mode A (Gold sink)

- [x] 7.4-a `platform-packs/snowflake/` Gold Iceberg external table SQL template + renderer `.sql.j2`
- [x] 7.4-b `render_workload` snowflake_sink artifact (synthesized when `sinks.snowflake: true`)
- [x] 7.4-c `platform-packs/snowflake/terraform/` — `terraform validate` PASS
- [x] 7.4-d `workloads/snowflake_sink_demo/` + `tests/test_snowflake_pack.py`
- [B] 7.4-e C Live: Gold -> Snowflake Iceberg external table — **blocked: no Snowflake account**

**7.4 Gate A+B status:** ✅ **COMPLETE (2026-10-01)**

## Phase 7.5 — Snowflake Mode B (full platform, on request)

- [x] 7.5-a `snowflake_tasks` orchestrator routing + Tasks SQL synthesis in `render_workload`
- [x] 7.5-b Snowpark templates (ingest, bronze→silver, silver→gold, quality)
- [x] 7.5-c `platform-packs/snowflake/terraform/tasks.tf` — `terraform validate` PASS
- [x] 7.5-d `workloads/snowflake_demo/` + extended `tests/test_snowflake_pack.py`
- [B] 7.5-e C Live E2E full medallion in Snowflake — **blocked: no Snowflake account**

**7.5 Gate A+B status:** ✅ **COMPLETE (2026-10-01)**

**Phase 7 multi-platform factory:** all packs through Gate A+B complete (Gate C parked on sandboxes).

---

## Sandbox acquisition (unblocks Gate C)

- [ ] Azure subscription (own trial or Perficient sandbox)
- [ ] GCP project + billing (own trial or Perficient sandbox)
- [ ] Databricks workspace (trial or Perficient)
- [ ] Snowflake account (trial or Perficient)
