# Azure-native platform pack

Implements the Phase 7 capability interface for `profile: azure`.
See [`docs/PHASE_7_MULTI_PLATFORM.md`](../../docs/PHASE_7_MULTI_PLATFORM.md).

## Capability mapping

| Capability | Azure-native resolution |
|------------|-------------------------|
| ObjectStore | **ADLS Gen2** (`abfss://<container>@<account>.dfs.core.windows.net/...`) |
| TableFormat | **Iceberg** (default) or Delta |
| TransformEngine | **Azure Synapse Spark** (PySpark) |
| BatchPython | Azure Functions / Synapse Python — quality gates, small ingest |
| Catalog | Synapse Spark catalog / Purview registration |
| Governance | Microsoft Purview tags + RBAC |
| Orchestrator | **Azure Data Factory (ADF)** pipeline |
| DeployAdapter | **Terraform (azurerm)** |

## Why Synapse (not Databricks-on-Azure)

Keeps the `azure` profile distinct from the dedicated `databricks` profile (7.3).
Swap the transform engine per workload in `config/platform.yaml` if a client
standardizes on Fabric or Azure Databricks — the capability wiring is unchanged.

## Layout

```text
platform-packs/azure/
  templates/     # Jinja codegen: ADLS ingest, Synapse PySpark transforms, python quality
  terraform/     # azurerm modules: resource group, ADLS Gen2, Synapse, ADF
  deploy/        # deploy adapter (terraform plan/apply wrapper, no account needed to plan)
```

## Verification status

- **Gate A (build/render):** templates render from cloud-neutral codegen specs.
- **Gate B (plan):** `terraform -chdir=platform-packs/azure/terraform validate`.
- **Gate C (live E2E):** BLOCKED — no Azure subscription yet. Parked until a
  sandbox (own trial or Perficient) is available. See `docs/PHASE_7_TODO.md`.

## Specs are shared

Azure consumes the **same** `config/codegen/*.spec.yaml` slot shape as AWS
(`schema_version`, `workload`, `database`, `silver_table`, `source_format`).
Only `config/platform.yaml` `profile: azure` changes — the renderer selects this
pack's templates. No business logic is duplicated.
