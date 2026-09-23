# Demo runbook — time, cost, what to keep

**Live client script:** `docs/CLIENT_DEMO_RUNBOOK.md` (laptop) and `docs/API_ONLY_FACTORY.md` (Harness).
**Sandbox up/down:** `docs/SANDBOX_LIFECYCLE.md`.

The catalog-only demo (`supplier_lead_times`) does not create the hourly services below.
This page is the cost table for when `advisory_transactions` sinks are turned on.

## 1. From-scratch time (extensions on)

A first `terraform apply` in an empty account is dominated by OpenSearch, not by Glue or Step Functions.

| Step | Wall clock | Notes |
|---|---|---|
| `python tools/package_and_sync.py` | 2–4 min | Uploads scripts + Lambda zips |
| Terraform: S3/IAM/KMS/Glue/SFN/Lambda/SNS | 3–5 min | Cheap, fast |
| Terraform: ElastiCache Redis | 5–10 min | Single `cache.t3.micro` |
| Terraform: Redshift Serverless | 3–8 min | Namespace + workgroup ENIs |
| Terraform: OpenSearch domain | **15–25 min** | One-node `t3.small.search` |
| One-time Lake Formation grants + Athena workgroup | 2–5 min | Admin must be an LF admin |
| First Step Functions run | 6–12 min | Glue ETL (Iceberg) + Python Shell quality gates + Lambdas |
| **Total, no surprises** | **~35–50 min** | With OpenSearch + Redis + Redshift |

A clean replay stays in that band if the SSO session stays alive. OpenSearch create is longer than a typical `aws login` token.

## 2. Keep vs destroy

Extension modules are **off by default** (`compute.yaml` `sinks.*: false`). Turn a sink on only for that demo, then set it back to `false` and apply so Terraform destroys the module.

### Keep (near-zero idle cost; slow or painful to recreate)

| Resource | Why keep |
|---|---|
| S3 data-lake bucket + landing/bronze/silver/gold objects | Pennies per day; landing file is the demo input |
| Glue database + tables + LF-Tags | Recreating tags and grants is fiddly (LF admin) |
| KMS CMKs (`alias/advisory_transactions-*`) | **Deletion window is 7 days** — destroying them still bills for a week |
| IAM roles/policies (Glue, SFN, Lambdas, Spectrum) | Fast to recreate, coupled to LF grants |
| Step Functions + EventBridge + SNS + budget | Pennies |
| Lambda functions + their S3 zips | Pennies |
| Glue job definitions | Pennies; DPU only while a job runs |
| S3 Gateway VPC endpoint | Free (gateway type) |
| Athena `primary` workgroup output location | One CLI call, easy to forget in the room |

### Destroy before the idle period

| Resource | Why destroy | Recreate time |
|---|---|---|
| OpenSearch `advisory-dev-search` | Largest hourly cost | **15–25 min** |
| ElastiCache Redis `advisory-transactions-dev-cache` | Always-on node | 5–10 min |
| Redshift Serverless workgroup + namespace | RPUs while active | 3–8 min |

The core pipeline (Glue → Athena → LF-Tags → verifier) still runs with all sinks false.

## 3. What a core-only demo still shows

- Step Functions graph, Glue job runs, S3 medallion prefixes
- Athena on `fact_transactions` / `silver_advisory_transactions`
- Lake Formation LF-Tags on `client_ssn` / `client_email` / `client_name`
- Quality gates and quarantine CSV

That covers a 15-minute walkthrough. Bring the three extensions back when the room needs warehouse, search, and cache in the same run.
