# Snowflake platform pack

**Mode A (7.4): Gold sink** — medallion on host cloud; Snowflake external Iceberg table for BI.

**Mode B (7.5): Full platform** — Snowpark transforms + native tables + Snowflake Tasks.

## Capability mapping

| Mode | TransformEngine | Lake format | Orchestrator |
|------|-----------------|-------------|--------------|
| A (sink) | N/A (host cloud) | Iceberg external | host orchestrator |
| B (platform) | **Snowpark** | **native** | **snowflake_tasks** |

## Render

```bash
# Mode A — Gold sink SQL (AWS workload + sinks.snowflake: true)
python tools/render_workload.py --workload snowflake_sink_demo --artifact snowflake_sink --write

# Mode B — full medallion
python tools/render_workload.py --workload snowflake_demo --all --write
```

Gate C blocked until Snowflake account exists.
