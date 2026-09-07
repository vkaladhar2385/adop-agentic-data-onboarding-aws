# From Weeks to Hours: Agentic Data Engineering on Your AWS Estate

### A worked example using the ADOP pattern — `advisory_transactions` (SOX)

> This is a **demonstrated AWS reference pattern**, proven end-to-end on a synthetic
> wealth-management dataset. It is not a proposal to run this specific codebase
> against your regulated production environment — it shows *what the pattern
> delivers* and *how it drops into your existing AWS + CI/CD*.

---

## 1. The problem we all recognize

Onboarding a single new data source into a governed lake is slow and repetitive:

- Data engineers hand-write PySpark for Bronze -> Silver -> Gold
- Analysts hand-author quality rules column by column
- Someone hand-builds the orchestration DAG and the IaC
- PII handling, KMS zoning, Lake Formation tags, and audit wiring are redone every time
- Bugs surface in production, not in review

For a mid-size firm onboarding dozens of feeds a year, that is **2–3 weeks of skilled effort per source** — and inconsistent governance across sources.

## 2. What ADOP changes

You describe the source in plain English. Specialized agents generate a **complete,
tested, governed pipeline** — config, PySpark, quality rules, star schema, Step
Functions orchestration, IaC, and tests — in **hours**, not weeks. Agents run only
in **Dev**; they emit version-controlled artifacts that flow through *your* CI/CD to
QA/Staging/Prod. **Agents never touch production.**

## 3. What the client actually receives (this repo is the proof)

The same pattern produced two contrasting workloads: `advisory_transactions` (SOX,
daily batch, star schema) and `web_events` (GDPR, hourly clickstream, rollups).
A single natural-language request for the wealth feed produced:

| Deliverable | File(s) | Value to the client |
|---|---|---|
| Declarative spec | `config/*.yaml` | One source of truth; readable by auditors, not just engineers |
| ETL Bronze->Silver->Gold | `scripts/transform/*` | Production PySpark + a local mode that runs anywhere |
| SOX quality gates | `config/quality_rules.yaml`, `shared/utils/quality.py` | Financial-integrity checks block bad data from promotion |
| Star schema (Gold) | `sql/gold/create_gold_star_schema.sql` | BI/QuickSight-ready fact + dimensions |
| Orchestration | `orchestration/*.json` | Step Functions + EventBridge (no always-on Airflow bill) |
| IaC | `iac/terraform/*` | Zone-scoped KMS, IAM least-privilege, budget guardrail |
| CI/CD | `.github/workflows/*` | Tests + validation on every PR; gated deploys via OIDC |
| Tests | `tests/**` (17 passing) | Confidence before a single AWS resource is created |
| Governance | LF-Tags plan, PII masking/suppression, quarantine | Column-level access control + auditable data handling |

## 4. The measurable win

See `BEFORE_AFTER.md` for the full table. Headline for one workload:

- **Manual:** ~14 engineer-days
- **Agentic (ADOP):** ~0.5 day (agent run + human review)
- **Time reduction:** ~90–95%
- **LLM token cost per workload:** ~$0.75 (Sonnet) to ~$3.65 (Opus)
- **AWS infra cost, this design:** near-zero at rest (no MWAA); pay-per-run Glue only

At 20 sources/year, that is roughly **270 engineer-days reclaimed** for the cost of
a few dollars of tokens and a consistent, auditable governance posture on every feed.

## 5. Why it fits *your* AWS + CI/CD (not a rip-and-replace)

- **Native AWS only:** S3, Glue, Athena, Iceberg, KMS, Lake Formation, Step Functions,
  EventBridge, SNS, CloudTrail — services you already run.
- **Dev-only agents:** no production credentials for any agent. Artifacts are the product.
- **Your pipeline, your gates:** generated artifacts are committed to git and promoted
  through your existing GitHub Actions / CodePipeline with your approvals.
- **Your modules:** generated Terraform is a starting point that maps onto your approved
  module library — the exact adaptation points are enumerated in `ADAPTATION_GAP.md`.
- **Your guardrails:** Cedar policies + invariants (immutable Bronze, mandatory lineage,
  zone-scoped KMS, PII masking, quality gates) travel with every workload.

See `AWS_CICD_FIT.md` for the integration diagram and the mapping to a typical
enterprise landing zone.

## 6. The consulting offer (how we engage)

1. **Pilot (this):** prove the pattern in a sandbox on a representative feed.
2. **Adaptation:** wire the generator to the client's module library, landing zone,
   IAM boundaries, and CI/CD (the `ADAPTATION_GAP.md` backlog).
3. **Enablement:** the client's platform team onboards subsequent feeds themselves,
   in hours, with governance guaranteed by policy — not by tribal knowledge.

**The pitch is pattern adaptation, not tool adoption.**
