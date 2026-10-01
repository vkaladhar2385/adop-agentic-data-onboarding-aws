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

## Phase 7.1 — Azure-native pack

- [ ] A Build: `platform-packs/azure/` templates + specs render
- [ ] B Plan: `terraform plan` clean + unit tests
- [B] C Live E2E on Azure sandbox (1 workload) — **blocked: no Azure account**

## Phase 7.2 — GCP-native pack

- [ ] A Build: `platform-packs/gcp/` templates + specs render
- [ ] B Plan: `terraform plan` clean + unit tests
- [B] C Live E2E on GCP sandbox (1 workload) — **blocked: no GCP account**

## Phase 7.3 — Databricks pack

- [ ] A Build: `platform-packs/databricks/` (Iceberg or Delta via `lake_format`)
- [ ] B Plan: bundle validate / `terraform plan` + unit tests
- [B] C Live E2E on Databricks workspace — **blocked: no workspace**

## Phase 7.4 — Snowflake Mode A (Gold sink)

- [ ] A Build: `platform-packs/snowflake/` sink adapter
- [ ] B Plan: SQL compile / `terraform plan` + unit tests
- [B] C Live: Gold -> Snowflake Iceberg external table — **blocked: no Snowflake account**

## Phase 7.5 — Snowflake Mode B (full platform, on request)

- [ ] A Build: Snowpark/SQL transform engine + Tasks orchestration exporter
- [ ] B Plan: SQL compile + unit tests
- [B] C Live E2E full medallion in Snowflake — **blocked: no Snowflake account**

---

## Sandbox acquisition (unblocks Gate C)

- [ ] Azure subscription (own trial or Perficient sandbox)
- [ ] GCP project + billing (own trial or Perficient sandbox)
- [ ] Databricks workspace (trial or Perficient)
- [ ] Snowflake account (trial or Perficient)
