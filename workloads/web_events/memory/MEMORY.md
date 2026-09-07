---
workload: web_events
type: ledger
---

# web_events — Workload Memory

- GDPR: `consent_analytics=false` is suppressed, not quarantined (different from SOX dirty-row review).
- Right-to-erasure uses the hashed `user_id` token, never the raw id.
- Gold is hourly rollups, not a star schema (contrast with advisory_transactions).
- Orchestration: EventBridge hourly at :05, Step Functions, no MWAA.
