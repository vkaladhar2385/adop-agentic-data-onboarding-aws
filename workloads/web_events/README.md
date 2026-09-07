# Workload: `web_events` (GDPR contrast)

Hourly website clickstream (JSONL, Kinesis-landing shape) vs. the daily SOX
brokerage feed. Same ADOP pattern, different regulation and Gold shape.

| | `advisory_transactions` | `web_events` |
|---|---|---|
| Cadence | Daily batch CSV | Hourly micro-batch JSONL |
| Regulation | SOX | GDPR |
| Gold | Star schema (fact + dims) | Hourly traffic rollup |
| PII | Mask SSN/email; suppress in Gold | Hash user_id; mask email/IP; suppress in Gold |
| Special control | Quarantine bad financial math | Drop no-consent; erasure index by hashed token |

```bash
python demo/data_generators/generate_web_events.py
python workloads/web_events/scripts/run_local_pipeline.py
pytest workloads/web_events/tests/ -v
```
