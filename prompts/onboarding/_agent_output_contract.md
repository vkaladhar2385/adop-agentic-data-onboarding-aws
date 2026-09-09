# Sub-agent output contract (mandatory)

Every onboarding sub-agent **must finish with a single JSON object** matching
`shared/templates/agent_output_schema.py` → `AgentOutput`.

The main agent:

1. Parses your JSON (`AgentOutput.from_dict` or `extract_json_from_subagent_response`)
2. Calls `parse_agent_output_payload` — **blocks** if `status != success` or `blocking_issues` non-empty
3. Writes `workloads/{workload_name}/logs/agent_outputs/{agent_type}.json`
4. Writes artifact files from your payload **only after** validation passes

**Required fields:** `agent_name`, `agent_type`, `workload_name`, `run_id`, `started_at`,
`completed_at`, `status`, `artifacts`, `blocking_issues`, `tests`

**artifacts:** `[{ "path": "config/source.yaml", "type": "config", "checksum": "<sha256 or pending>" }]`
List every file the main agent should write. Use `content` blocks in a separate keyed map
only when the main agent prompt allows inline YAML — prefer listing paths + full file bodies
in a top-level `"file_contents": { "config/source.yaml": "..." }` **inside** the JSON if needed.

**tests:** `{ "unit": { "passed": 0, "failed": 0, "total": 0 } }` — sub-agents that do not run
pytest use zeros; main agent updates after pytest.

**Do not** finish with markdown-only prose. Wrap JSON in a ` ```json ` fence if needed.

**Bedrock / Runtime:** call tool `submit_agent_output` with the same payload shape.
