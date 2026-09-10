# Workload: `product_inventory`

Daily SKU inventory snapshot. **Tier A factory proof #3** via `/onboard-workflow`:
full medallion, **flat Iceberg** Gold, **catalog only**, no PII regulation. Status: `docs/STATUS.md`.

## Phase 1 decisions

| Item | Answer |
|------|--------|
| PK / dedup | `sku` / `keep_latest` by `updated_at` |
| Quarantine | blank `sku`, negative `on_hand_qty` |
| Derived | `available_qty`, `inventory_value`, `margin_pct` |
| Gold | flat Iceberg, grain = `sku` |
| Quality | Silver ≥ 0.80, Gold ≥ 0.95 |
| Schedule | `cron(0 8 * * ? *)` UTC |
| Compute | Shell ingest + quality; Spark Iceberg transforms |

## Local tests (no AWS)

```bash
python demo/data_generators/generate_product_inventory.py
python -m pytest workloads/product_inventory/tests/ -v
python workloads/product_inventory/scripts/run_local_pipeline.py
```

## Deploy

Not wired in Terraform yet (`compute.yaml` `terraform_sync.status: pending`).
Do not `terraform apply` until a module block is added and the user approves Phase 5.
