---
workload: advisory_transactions
updated: 2026-09-04
type: ledger
---

# advisory_transactions — Workload Memory

Persistent learnings that carry forward to future runs (ADOP Workload Memory).
On the next run the agent loads this first, pre-fills known answers, and avoids
re-asking.

## project (schema facts)
- Primary key is `transaction_id` (unique, never null).
- SOX financial integrity is enforced by two derived-formula checks:
  `gross_amount == quantity * unit_price` and
  `net_amount == gross_amount - commission - fees`.
- Settlement is T+2 (`settlement_date = trade_date + 2 days`).

## feedback (corrections learned)
- Bad financial rows must be QUARANTINED for human review, never dropped
  silently (SOX). See `quarantine_when` in transformations.yaml.

## reference (paths / names)
- Landing: s3://data-lake-<account>-us-east-1/landing/advisory_transactions/
- Glue DB: advisory_transactions_db
- KMS aliases: alias/advisory_transactions-{bronze,silver,gold}

## user (operator preferences)
- Orchestration = Step Functions + EventBridge (no MWAA) for cost control.
- Gold zone = star schema for BI/QuickSight consumption.
