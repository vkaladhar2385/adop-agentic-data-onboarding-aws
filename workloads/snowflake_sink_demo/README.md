# snowflake_sink_demo

Phase 7.4 proof — **Snowflake Mode A (Gold sink)**.

Medallion pipeline runs on **AWS** (`profile: aws`). After Gold Iceberg lands on S3,
`sinks.snowflake: true` renders external Iceberg DDL via `platform-packs/snowflake/`.

Render: `python tools/render_workload.py --workload snowflake_sink_demo --all --write`

Gate C blocked until Snowflake account + storage integration.
