# What “wire the sandbox AWS deploy” actually means

This **was** Phase 3 of the pilot plan. It is now **done** on the sandbox
account (see `docs/STATUS.md`). Glue jobs run as **Python Shell** (pandas +
`s3_io`), not Spark — the dataset is demo-scale.

Live proof: Step Functions `advisory_transactions_pipeline` execution
`phase3-extensions-3` (SUCCEEDED). Failures we hit getting there:
`docs/PILOT_FAILURES_AND_FIXES.md`. Demo keep/destroy: `docs/DEMO_RUNBOOK.md`.

The rest of this file is the original checklist, kept as a narrative of what
“wire” meant. Some “still stubbed” sentences below are historical.

---

## What we have already vs. what Phase 3 adds

| Already done (this repo) | Still only on your machine | Phase 3 would prove on AWS |
|---|---|---|
| Config, ETL logic, quality gates | Pandas local runner | Glue jobs write Iceberg to S3 |
| Step Functions **definition** (JSON) | Never registered in AWS | A real state machine you can StartExecution |
| Terraform **files** | Never `apply`’d | Real KMS keys, IAM roles, EventBridge, SNS |
| LF-Tag **plan** (printed) | Never applied | Lake Formation tags on real columns |
| Post-deploy verifier (dry-run) | No boto3 calls | Glue tables exist, Athena returns rows, KMS rotation on |
| Synthetic CSV/JSONL | Lives in `demo/sample_data/` | Copied to an S3 landing prefix |

**In one sentence:** Phase 3 is “take the generated artifacts and actually run
them once in a throwaway AWS account so you have screenshots of Glue / Athena /
Step Functions for the client room.”

---

## What “wire” means, step by step

Nothing here is magic. It is a short, ordered checklist.

### 0. Preconditions (before any `apply`)
1. Confirm you are in a **personal sandbox** account — `aws sts get-caller-identity`.
   The account id must **not** be LPL / Perficient / any client.
2. Budget alert already on (~$25). Region chosen (this repo assumes `us-east-1`).
3. A landing / lake bucket exists (Phase 1 Environment Setup Agent), or you create
   one cheap S3 bucket by hand.
4. Glue, Athena, Step Functions, EventBridge, KMS, Lake Formation, SNS, CloudTrail
   are usable in that account (default in a normal sandbox).

### 1. Put artifacts where AWS can see them
- `aws s3 sync workloads/advisory_transactions/ s3://<artifact-bucket>/workloads/...`
- `aws s3 cp demo/sample_data/advisory_transactions.csv s3://<lake>/landing/advisory_transactions/ingestion_date=2026-09-03/`
- Upload Glue job scripts (`scripts/extract/*`, `scripts/transform/*`) as the
  job `--script-location`.

Today those Glue files have a **local pandas path** and a **stubbed Glue path**.
Wiring means filling the stub: SparkSession reads S3, writes Iceberg, same
rules as `local_runner.py`. That is the only real code gap before a live run.

### 2. Apply the Terraform you already have
From `iac/terraform/`:

```text
terraform init
terraform plan     # you review every resource
terraform apply    # creates KMS x3, Glue DB, Step Functions, EventBridge, SNS, IAM, $25 budget
```

After apply you get real ARNs (`terraform output`). That is “wired”: the JSON
state machine is now a live AWS resource with an IAM role that can start Glue.

### 3. Create the Glue jobs the state machine names — DONE
The ASL references job names like `advisory_transactions_ingest_to_bronze`.
Terraform now creates all 10 `aws_glue_job` resources (5 per workload) via
`iac/terraform/modules/workload_pipeline/glue.tf`, pointing at
`s3://<bucket>/workloads/<workload>/scripts/...` — the CI `deploy.yml`
`package_and_sync` job `aws s3 sync`s those scripts there before `apply` runs.

Same for the two Lambdas named in ASL (`register_catalog`, `post_deploy_verifier`):
both now have real `lambda_handler(event, context)` entrypoints and
`aws_lambda_function` resources (`lambda.tf`), deployed from lean zips that
`deploy.yml` builds and uploads to `s3://<bucket>/lambda-artifacts/<workload>/`.

### 4. Run one execution
```text
aws stepfunctions start-execution --state-machine-arn <arn>
```
Watch the graph: Bronze → Silver → Silver gate → Gold → Gold gate → catalog → verify.

Then prove data:
- Athena: `SELECT COUNT(*) FROM advisory_transactions_db.gold_fact_transactions;`
- Confirm quarantine table has the seeded bad rows.
- Confirm Gold has **no** `client_ssn` / `client_email` / `client_name`.

### 5. Run the post-deployment verifier (live, not `--dry-run`)
The 7 checks the pilot plan lists:

1. Glue tables exist in the catalog
2. Athena returns non-empty data
3. LF-Tags applied on PII / PHI columns
4. TBAC restricts CRITICAL columns (or at least tags are present)
5. Zone KMS keys exist with rotation enabled
6. Orchestration loads (state machine, not MWAA DAG)
7. CloudTrail shows the deploy / LF / KMS events

Deployment is not “done” until these pass. That is the screenshot set for clients.

### 6. Tear down the same day
```text
terraform destroy
```
Then manually confirm: no Glue jobs left running, no EventBridge schedule still
firing, no leftover S3 test prefixes if you want the bill at pennies. Check Cost
Explorer the next morning.

**Estimated cost if you stay disciplined:** $5–15 (Glue DPU-seconds + a few Athena
queries + KMS/S3). The cost risk is **forgetting to destroy**, not the run itself.

---

## What Phase 3 is *for* in a client conversation

| You can say today (no Phase 3) | You can say after Phase 3 |
|---|---|
| “Here is the generated pipeline; it runs locally and tests pass.” | “Here is the same pipeline on AWS: Athena result, Step Functions graph, LF-Tags.” |
| “IaC is ready; we have not applied it.” | “We applied, verified, and destroyed in a sandbox the same day.” |
| Pattern is demonstrated | Pattern is **exercised** on AWS, with evidence |

For many first meetings, **today is enough**. Phase 3 is insurance for the skeptic
who says “show me it actually runs on Glue.”

---

## What Phase 3 is *not*

- Not connecting to LPL / Perficient / any client account
- Not using real client data
- Not leaving MWAA or any always-on compute running
- Not treating generated Terraform as production-ready (see `ADAPTATION_GAP.md`)
- Not “the client engagement.” The engagement is adapting this pattern to *their*
  modules, IAM, VPC, and CI/CD.

---

## Code gaps you would close if/when you choose to do Phase 3

Of the original six, one remains open on purpose, one is optional, and four
are now closed:

1. **Glue PySpark bodies** — still open. `run_glue()` in each transform script
   is a stub with the Spark code written as a comment; only the `--local`
   pandas path actually executes. This is the one real code gap left before a
   live Glue run would produce data. (Bronze `ingest_to_bronze.py` and the
   quality-gate scripts are already runnable as-is under Glue Python Shell —
   `run_quality_checks.py` has no Spark dependency at all.)
2. ~~`aws_glue_job` + Lambda resources in Terraform~~ — **closed.** 10 Glue jobs
   + 4 Lambdas, `iac/terraform/modules/workload_pipeline/{glue,lambda}.tf`.
3. ~~Replace `<account>` placeholders in ASL SNS ARNs~~ — **closed.** Both state
   machines use `${account_id}` / `${aws_region}` Terraform template vars.
   (SQL DDL files still show `<account>` — those are illustrative reference
   DDL, not executed by Terraform or any script, so left as-is intentionally.)
4. ~~Lake Formation apply~~ — **closed.** `apply_lf_tags()` in each workload's
   `register_catalog.py` calls real `boto3 lakeformation` create/associate
   APIs, invoked from `lambda_handler()`.
5. ~~Verifier live checks~~ — **closed.** `shared/utils/post_deployment_verifier.py`
   now runs real Athena `start_query_execution`, Lake Formation
   `get_resource_lf_tags`, and CloudTrail `lookup_events` calls.
6. **OIDC deploy role** — still open (optional). Only needed if you use
   `deploy.yml` against the sandbox; you can also apply Terraform from your
   laptop with `aws configure` / SSO credentials and skip OIDC entirely.

With #1 as the only remaining code gap, `terraform apply` would now create
everything the state machine needs (Glue jobs, Lambdas, KMS, IAM); the Silver
and Gold ETL job runs would need the Spark bodies filled in to actually
transform data on Glue (they'd currently raise `SystemExit` in `run_glue()`).

---

## Decision guide

- **Stay local (current):** client pitch, live pandas demo, tests, IaC review.
- **Do Phase 3 later:** when you want AWS console screenshots, or before a
  technical deep-dive with a client platform team.
- **Never do Phase 3 against a client account** without their security review.
  The pilot plan is explicit about that.
