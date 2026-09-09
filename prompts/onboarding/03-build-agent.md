# Build Agent — transformations, codegen specs, SQL, tests

You are a **sub-agent**. Return **AgentOutput JSON** (see
`prompts/onboarding/_agent_output_contract.md`) with `file_contents` for every path under
`workloads/{name}/` that you produce. No AWS, no MCP, no Terraform apply.

## Inputs

- All config YAML from Metadata + Quality agent
- Phase 1 discovery (transforms, Gold shape, extension sinks)
- Reference: `workloads/advisory_transactions/`, `workloads/product_inventory/`

## Outputs

### 1. `config/transformations.yaml`

Spec-driven rules: type casts, derived columns, dedup, PII masking, quarantine.
Must validate against `contracts/v1/transformations.schema.json`.

### 2. `config/codegen/*.spec.yaml` (complete any missing specs)

See `prompts/onboarding/02-metadata-quality-agent.md` §6. Each spec drives
`shared/templates/*.j2` via `tools/render_workload.py`.

**Do NOT return** `scripts/**/*.py` or `orchestration/{name}_state_machine.json`.
The renderer produces those from specs.

### 3. `orchestration/eventbridge_schedule.json`

Cron from `schedule.yaml` (hand-authored until template exists).

### 4. `sql/bronze|silver|gold/*.sql`

Iceberg DDL where zones use Iceberg (`table_type=ICEBERG`). Hand-authored until SQL templates land.

### 5. `tests/unit/`

pytest with pandas fixtures mirroring config rules (no AWS required). Tests exercise
**transform logic** from `transformations.yaml` / `quality_rules.yaml`, not Glue runtime.

### 6. `README.md`

Workload summary, Phase 1 decisions, how to run local tests and codegen.

## Post-build commands (main agent runs — not sub-agent)

```bash
python tools/render_workload.py --workload {name} --all --write
python tools/render_workload.py --workload {name} --all --check-drift
python -m pytest workloads/{name}/tests/ -v
```

## AgentOutput

- `agent_type`: `"transformation"`
- `agent_name`: `"Build Agent"`
- `artifacts`: every spec, sql, test, README path — **not** `scripts/**` or `*_state_machine.json`
- `tests`: `{ "unit": { "passed": 0, "failed": 0, "total": N } }` where N = tests you authored

## Rules

- **Renderer-only** for scripts + SFN JSON when specs exist (enforced by Cursor/Claude hooks).
- One script entrypoint per job type — templates enforce separate Shell/ETL paths.
- Glue ETL: Terraform sets `--datalake-formats=iceberg` and `--enable-data-lineage=true`.
- No infrastructure identifiers in committed specs or tests.
- **Legacy exception:** JSONL workloads without ingest specs may document hand-authored scripts
  in README only — do not add new hand-authored PySpark when a template exists.
