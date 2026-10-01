# gcp_demo — GCP-native Phase 7.2 proof workload

Renders **Dataproc Spark + GCS + Composer** from cloud-neutral codegen specs.

```powershell
python tools/render_workload.py --workload gcp_demo --all --write
python tools/render_workload.py --workload gcp_demo --all --check-drift
```

Gate C (live E2E) blocked until a GCP project is available.
