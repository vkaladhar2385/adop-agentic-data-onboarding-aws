# customer_orders — Tier B factory proof (workload #5)

Catalog-only medallion with **MWAA orchestration** (`orchestrator: mwaa`) and **ontology staging**
opt-in. Validates dual-orchestration codegen, Cedar sub-agent boundaries, and semantic layer
staging without requiring live Gateway/MWAA until sandbox redeploy.

## Orchestration

| Setting | Value |
|---------|-------|
| Primary | MWAA — `dags/customer_orders_pipeline.py` (codegen) |
| SFN | Not emitted (Step Functions spec omitted by design) |

## Local demo

```bash
python demo/data_generators/generate_customer_orders.py
pytest workloads/customer_orders/tests/unit/ -v
python tools/render_workload.py --workload customer_orders --all --write
python -c "from shared.semantic_layer import induce_and_stage; induce_and_stage(dataset_name='customer_orders', glue_database='customer_orders_db', glue_table='gold_customer_orders', namespace='commerce')"
```

## Tier B acceptance (file-level)

- [x] `config/codegen/dag.spec.yaml` + rendered DAG
- [x] `ontology_staging: true` → TTL + manifest under `config/`
- [ ] Gateway health (requires AWS — step 13)
- [ ] MWAA UI parse test (requires AWS — step 14)
