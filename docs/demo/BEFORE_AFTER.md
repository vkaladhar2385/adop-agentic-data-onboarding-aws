# Before / After — Time & Cost, `advisory_transactions`

Effort to onboard **one** governed, SOX-compliant data source, Bronze->Silver->Gold
with a star schema, quality gates, orchestration, IaC, CI/CD, and tests.

## Per-task comparison

| Task | Manual (skilled engineer) | Agentic (ADOP) | Reduction |
|---|---|---|---|
| Analyze source + design schema/semantics | 1.0 day | 10 min | ~98% |
| Bronze->Silver->Gold ETL (PySpark) | 3.0 days | 15 min | ~95% |
| Column-level quality rules + gates | 1.5 days | 10 min | ~90% |
| PII detection, masking, LF-Tag plan | 1.0 day | 10 min | ~95% |
| Gold star schema (fact + dims) | 1.5 days | 10 min | ~95% |
| Orchestration (Step Functions + schedule) | 1.0 day | 10 min | ~95% |
| IaC (KMS, IAM, SFN, EventBridge, budget) | 2.0 days | 15 min | ~90% |
| CI/CD wiring (tests, validate, deploy) | 1.5 days | 15 min | ~90% |
| Unit + integration tests | 1.5 days | (generated) | ~95% |
| **Total** | **~14 engineer-days** | **~0.5 day** | **~90–95%** |

> "Agentic" time includes the human-in-the-loop review at each phase, which is where
> the remaining half-day goes. The agent generates; the engineer approves.

## Cost comparison (one workload)

| Line item | Manual | Agentic (ADOP) |
|---|---|---|
| Engineer effort @ ~14 vs ~0.5 days | fully loaded 14 days | fully loaded 0.5 day |
| LLM tokens | n/a | ~$0.75 (Sonnet) – ~$3.65 (Opus) |
| Orchestration at rest | MWAA ~$350/mo if used | **$0** (Step Functions + EventBridge) |
| Storage/compute | S3 + Glue per run | S3 + Glue per run (same) |

## Scaled view (illustrative: 20 sources / year)

| Metric | Manual | Agentic |
|---|---|---|
| Engineer-days | ~280 | ~10 |
| Days reclaimed | — | **~270** |
| Token cost (all Opus, worst case) | — | ~$73 |
| Governance consistency | varies per engineer | identical, policy-enforced |

## How these numbers were derived (be honest in the room)

- **Manual estimates**: typical senior data-engineer effort for a governed feed;
  adjust to the client's actuals.
- **Agentic timings**: ADOP's published per-phase run times (Discovery→Build→Deploy)
  plus review overhead. This repo's local run completes in seconds on 200 rows.
- **Token cost**: ADOP's measured `financial_portfolios` run (~135K tokens/workload)
  at Anthropic list prices.
- **AWS infra cost is separate** from tokens and depends on data volume and run
  frequency; the design deliberately avoids always-on compute.
