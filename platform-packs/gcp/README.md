# GCP-native platform pack

Implements Phase 7 capability interface for `profile: gcp`.
See [`docs/PHASE_7_MULTI_PLATFORM.md`](../../docs/PHASE_7_MULTI_PLATFORM.md).

## Capability mapping

| Capability | GCP-native resolution |
|------------|----------------------|
| ObjectStore | **GCS** (`gs://<bucket>/bronze|silver|gold/...`) |
| TableFormat | **Iceberg** (default) or Delta |
| TransformEngine | **Dataproc Spark** (PySpark) |
| BatchPython | **Cloud Functions** — quality gates, small ingest |
| Catalog | Dataproc Metastore / BigLake |
| Governance | Dataplex + IAM |
| Orchestrator | **Cloud Composer** (Airflow DAG) |
| DeployAdapter | **Terraform (google)** |

## Layout

```text
platform-packs/gcp/
  templates/     # GCS ingest, Dataproc PySpark, Composer DAG
  terraform/     # google provider: GCS bucket, Dataproc cluster
  deploy/        # deploy adapter (validate/plan; apply blocked until sandbox)
```

## Verification

- **Gate A:** `pytest tests/test_gcp_pack.py` + render `gcp_demo`
- **Gate B:** `terraform -chdir=platform-packs/gcp/terraform validate`
- **Gate C:** BLOCKED — no GCP project yet
