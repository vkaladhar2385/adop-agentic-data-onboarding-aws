# Demo runbook — time, cost, what to keep

**Sandbox lifecycle:** prefer `python tools/provision_sandbox.py --bucket …` to bring up Gateway +
workloads, and `python tools/destroy_sandbox.py --yes` when done. See `docs/SANDBOX_LIFECYCLE.md`.
**Live client script:** `docs/CLIENT_DEMO_RUNBOOK.md`.

## 1. From-scratch time (clean replay, credentials already logged in)

A **first-time** `terraform apply` in an empty account is dominated by
OpenSearch, not by Glue or Step Functions.

| Step | Wall clock | Notes |
|---|---|---|
| `python tools/package_and_sync.py` | 2–4 min | Uploads scripts + 5 Lambda zips |
| Terraform: S3/IAM/KMS/Glue/SFN/Lambda/SNS | 3–5 min | Cheap, fast |
| Terraform: ElastiCache Redis | 5–10 min | Single `cache.t3.micro` |
| Terraform: Redshift Serverless | 3–8 min | Namespace + workgroup ENIs |
| Terraform: OpenSearch domain | **15–25 min** | One-node `t3.small.search` |
| One-time Lake Formation grants + Athena workgroup | 2–5 min | Admin must be an LF admin |
| First Step Functions run | 6–12 min | Mixed Glue ETL (Iceberg transforms) + Python Shell quality gates + Lambdas |
| **Total, no surprises** | **~35–50 min** | |

The first time we did this it took **hours**, almost all of it credential
expiry, Glue Python Shell packaging, and ASL/IAM bugs. Those are now fixed
in code. A clean replay should stay in the 35–50 minute band **if** the SSO
session stays alive (OpenSearch create is longer than a typical `aws login`
token).

## 2. If 35–50 minutes is too long before a client demo

**Do not destroy the cheap, slow-to-recreate control plane.** Destroy only the
three always-on hourly services.

### Keep (near-zero idle cost; slow or painful to recreate)

| Resource | Why keep |
|---|---|
| S3 data-lake bucket + landing/bronze/silver/gold objects | $0.00-something/day; landing CSV is the demo input |
| Glue database + tables + LF-Tags | Recreating tags/grants is fiddly (LF admin) |
| KMS CMKs (`alias/advisory_transactions-*`) | **Deletion window is 7 days** — destroying them still bills for a week |
| IAM roles/policies (Glue, SFN, Lambdas, Spectrum) | Instant to recreate, but coupled to LF grants |
| Step Functions + EventBridge + SNS + budget | Pennies |
| Lambda functions + their S3 zips | Pennies; code is already packaged |
| Glue job definitions | Pennies; 0.0625 DPU only when a job runs |
| S3 Gateway VPC endpoint | Free (gateway type) |
| Athena `primary` workgroup output location | One CLI call, but easy to forget in the room |

### Destroy before the idle period / recreate the morning of the demo

| Resource | Why destroy | Recreate time |
|---|---|---|
| OpenSearch `advisory-dev-search` | Largest hourly cost | **15–25 min** |
| ElastiCache Redis `advisory-transactions-dev-cache` | Always-on node | 5–10 min |
| Redshift Serverless workgroup + namespace | RPUs while active / resume | 3–8 min |

Comment out (or `-target`-destroy) the three module blocks in
`iac/terraform/main.tf`:

```hcl
module "advisory_transactions_redshift" { ... }
module "advisory_transactions_opensearch" { ... }
module "advisory_transactions_redis" { ... }
```

Then `terraform apply`. The **core** pipeline (Glue → Athena → LF-Tags →
verifier lake checks) still runs. The three extension states will fail until
you bring those modules back and re-apply.

**Morning-of-demo sequence (extensions off overnight):**

1. `aws login --profile aws-agent` (keep the session alive).
2. Uncomment the three modules; `terraform apply` (~20–30 min, OpenSearch).
3. `python tools/package_and_sync.py --workload advisory_transactions` if any
   Lambda code changed.
4. Start `advisory_transactions_pipeline` (~7 min).
5. Athena: `SELECT * FROM fact_transactions LIMIT 20;`

## 3. What a “cheap core-only” demo still shows

Without OpenSearch/Redis/Redshift you can still show:

- Step Functions graph, Glue job runs, S3 medallion prefixes
- Athena on `fact_transactions` / `silver_advisory_transactions`
- Lake Formation LF-Tags on `client_ssn` / `client_email` / `client_name`
- Quality gates and quarantine CSV

That is enough for a 15-minute client walkthrough. Bring the three extensions
back when you want “warehouse + search + cache” in the same run.
