# Snowflake platform pack

**Mode A (default): Gold sink** — medallion runs on the host cloud (AWS/Azure/GCP);
Snowflake exposes Gold Iceberg as an external table for BI/warehouse queries.

**Mode B (7.5):** full medallion in Snowflake (`snowflake_mode: platform`).

## Mode A capability mapping

| Capability | Snowflake resolution |
|------------|---------------------|
| Sink | External **Iceberg** table over host-cloud object store |
| TransformEngine | N/A (read-only sink; pipeline stays on host profile) |
| DeployAdapter | **Terraform** or **snowflake_cli** |
| Gate C | Blocked until Snowflake account + storage integration |

Render sink SQL: `python tools/render_workload.py --workload <name> --artifact snowflake_sink --write`
