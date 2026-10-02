# snowflake_demo

Phase 7.5 proof — **Snowflake Mode B (full platform)**.

Medallion runs entirely in Snowflake (`profile: snowflake`, `snowflake_mode: platform`)
using Snowpark transforms + Snowflake Tasks orchestration.

- **Transform engine:** Snowpark
- **Lake format:** native (managed tables)
- **Orchestrator:** `snowflake_tasks`

Render: `python tools/render_workload.py --workload snowflake_demo --all --write`

Gate C blocked until Snowflake account exists.
