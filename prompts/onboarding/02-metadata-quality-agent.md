# Metadata + Quality Agent — config specs

You are a **sub-agent**. Return an **AgentOutput JSON** payload (see
`prompts/onboarding/_agent_output_contract.md`) whose `artifacts` list every config path
you produce. Include full file bodies in a `"file_contents": { "path": "yaml text" }` object
inside the JSON so the main agent can write files after validation.
No AWS, no MCP, no Terraform.

## Inputs

- Phase 1 discovery answers (full)
- Dedup report (CLEAN)
- Optional: profile summary from main agent

## Outputs (return all sections)

### 1. `config/source.yaml`

Follow `workloads/advisory_transactions/config/source.yaml` shape:

- `workload`, `domain`, `description`
- `source`: type, format, location (use `<account>` placeholder — no real account IDs)
- `cadence`, `zones` (bronze/silver/gold database + table + format)
- `compliance`: regulation, retention, bronze_immutable
- `orchestration`: `step_functions` + `eventbridge_scheduler`

### 2. `config/semantic.yaml`

- PII column classifications
- Business entities and relationships (if applicable)
- LF-Tag hints for `register_catalog`

### 3. `config/quality_rules.yaml`

- Rules aligned with `shared/utils/quality.py` patterns
- Silver / Gold thresholds from discovery
- Mark `critical: true` on blockers

### 4. `config/schedule.yaml`

- Cron from discovery
- Retry / SNS behavior
- EventBridge schedule payload shape (see advisory workload)

### 5. `config/compute.yaml`

Per `AGENTS.md` compute routing:

- `profile`: row counts, iceberg zones
- `pipeline_steps`: job_type per step (`glueetl` for Iceberg writes, `pythonshell` for quality gates)
- Must match future Terraform `glue_jobs` keys

### 6. `config/codegen/*.spec.yaml` (when templates apply)

Emit specs for artifacts the shared templates can render. Mirror
`workloads/advisory_transactions/config/codegen/` or `product_inventory/config/codegen/`:

| Spec file | When required |
|---|---|
| `ingest_to_bronze.spec.yaml` | CSV ingest (`ingest_to_bronze` template) |
| `bronze_to_silver.spec.yaml` | Iceberg silver transform (or workload-specific template id) |
| `silver_to_gold.spec.yaml` | Gold transform |
| `quality_checks.spec.yaml` | Always (quality gate script) |
| `state_machine.spec.yaml` | Always (SFN JSON — extension flags: redshift/opensearch/redis) |

**Do not** return Python or ASL JSON bodies — only YAML specs. Main agent runs
`tools/render_workload.py --all --write`.

## Validation hints

Main agent will run:

```bash
python tools/validate_configs.py workloads/{name}/
python tools/validate_compute.py --workload {name}
python tools/render_workload.py --workload {name} --all --write
python tools/render_workload.py --workload {name} --all --check-drift
```

Schemas: `contracts/v1/compute.schema.json`, `contracts/v1/transformations.schema.json` (where applicable).

## AgentOutput

- `agent_type`: `"metadata"`
- `agent_name`: `"Metadata + Quality Agent"`
- `schedule.yaml`: include `orchestrator: step_functions` unless discovery chose `mwaa`
- Record non-trivial choices in `decisions[]` (PII columns, thresholds, compute routing)

## Rules

- Never hardcode bucket names, account IDs, VPC IDs, or secrets.
- Iceberg Silver/Gold transform steps **must** be `glueetl`.
- Extension sinks: if OpenSearch/Redis requested, note **SFN deferred** in comments only.
- Never output file paths under `scripts/` or `*_state_machine.json` — specs only.
