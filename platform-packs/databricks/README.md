# Databricks platform pack

Cross-cloud lakehouse profile (`profile: databricks`) on AWS, Azure, or GCP host.
Unity Catalog + Databricks Workflows + PySpark (Iceberg or Delta).

## Capability mapping

| Capability | Databricks resolution |
|------------|----------------------|
| ObjectStore | UC volumes / external locations on host cloud storage |
| TableFormat | **Delta** (default) or **Iceberg** via `platform.yaml` |
| TransformEngine | **Databricks Jobs** (PySpark) |
| BatchPython | Python wheel tasks for quality gates |
| Catalog | **Unity Catalog** |
| Governance | UC grants + tags |
| Orchestrator | **Databricks Workflows** (multi-task job) |
| DeployAdapter | **Terraform** or **Asset Bundles** |

Gate C (live E2E) blocked until a Databricks workspace exists.
