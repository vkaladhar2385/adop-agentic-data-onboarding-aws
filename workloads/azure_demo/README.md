# azure_demo — Azure-native Phase 7.1 proof workload

Demonstrates the multi-platform factory rendering **Synapse Spark + ADLS + ADF**
from the same cloud-neutral codegen specs used by AWS workloads.

| Config | Value |
|--------|-------|
| `platform.yaml` | `profile: azure`, `transform_engine: spark`, `orchestrator: adf` |
| `schedule.yaml` | `orchestrator: adf` |
| Pack | `platform-packs/azure/templates/` |

## Render

```powershell
python tools/render_workload.py --workload azure_demo --all --write
```

## Verify (no Azure account)

```powershell
python tools/render_workload.py --workload azure_demo --all --check-drift
python tools/validate_platform.py
pytest tests/test_azure_pack.py tests/test_orchestrator.py -v
```

Gate C (live E2E on Azure) is blocked until a sandbox subscription is available.
