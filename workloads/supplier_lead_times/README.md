# supplier_lead_times

Tier A **workload #4** — factory acceptance proof. Weekly CSV of supplier lead times by
category; **catalog-only** (no Redshift/OpenSearch/Redis). Default orchestrator: Step Functions.

## Local

```powershell
python demo/data_generators/generate_supplier_lead_times.py
python tools/render_workload.py --workload supplier_lead_times --all --write
pytest workloads/supplier_lead_times/tests/ -v
```

## Hand-authored (not codegen)

- `scripts/transform/local_runner.py`, `spark_transforms.py`
- `scripts/load/register_catalog.py`
- `sql/`, `orchestration/eventbridge_schedule.json`

## Generated (do not edit)

- `scripts/extract/ingest_to_bronze.py`
- `scripts/transform/bronze_to_silver.py`, `silver_to_gold.py`
- `scripts/quality/run_quality_checks.py`
- `orchestration/supplier_lead_times_state_machine.json`

## AWS E2E

Tier A acceptance + Tier B green run: SFN `tier-b-e2e-fix-v3-20260909-124345` (see `docs/STATUS.md`).
Deploy: `python tools/deploy_workload.py --workload supplier_lead_times --auto-provision` or
`docs/CLIENT_DEMO_RUNBOOK.md`.
