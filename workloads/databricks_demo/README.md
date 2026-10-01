# databricks_demo

Phase 7.3 proof workload — same supplier lead-time rules as `gcp_demo`, rendered via
`platform-packs/databricks` (Unity Catalog + Delta + Databricks Workflows).

- **Profile:** `databricks`
- **Host cloud:** `aws` (cross-cloud lakehouse)
- **Orchestrator:** `workflows`
- **Lake format:** `delta`

Render: `python tools/render_workload.py --workload databricks_demo --all --write`

Gate C (live workspace E2E) blocked until a Databricks workspace exists.
