# Extending ADOP to a New AWS Service

This doc captures the **repeatable recipe** used to add Redshift, OpenSearch,
and Redis to `advisory_transactions`, so the same steps generalize to any
future AWS service (or, per the Track B design-doc goal, to any other cloud
provider's equivalent service). It is written after the fact, based on the
three extensions actually built in `iac/terraform/modules/` — read it as "here
is what changing/adding a capability actually costs," not as a spec.

## Why these three

Everything in the core pilot (`advisory_transactions`, `web_events`) uses only
S3 + Glue + Athena + Lambda + Step Functions + EventBridge + Lake Formation —
all **serverless, no VPC, no persistent compute**. That's deliberate (cheap
sandbox, matches AGENTS.md cost guardrails) but it hides an entire class
of AWS services: anything that isn't a managed HTTP API. Redshift, OpenSearch,
and Redis were chosen because together they cover the three shapes you'll hit
adding *any* new service:

| Service | New AWS resource type | Reachable how | Needs a VPC? |
|---|---|---|---|
| Redshift Serverless | `aws_redshiftserverless_namespace`/`workgroup` | Redshift Data API (boto3, signed) | No |
| OpenSearch | `aws_opensearch_domain` | HTTPS + SigV4 (boto3-signed, no client lib) | No |
| ElastiCache Redis | `aws_elasticache_cluster` | Redis wire protocol (needs `redis` client lib) | **Yes** |

## The recipe, step by step

This is the same 6-step pattern every time, mirroring how the reference ADOP
framework's DevOps Agent generates one Terraform module per capability from a
schema-validated config, rather than hand-writing bespoke HCL per workload.

1. **New Terraform module** under `iac/terraform/modules/<service>_workload/`
   with the same 3-file shape as `workload_pipeline`: `variables.tf` (inputs:
   workload name, region, account, data lake bucket, tags — the same "contract"
   every module accepts), `main.tf` (the actual resources + their own IAM
   role), `outputs.tf` (ARNs/endpoints the root module or other modules need).

2. **IAM role scoped to the new resource only.** Every module in this repo
   creates its *own* IAM role rather than reusing a shared one — e.g. the
   Redshift Spectrum role can `glue:Get*` + read Gold S3 objects, nothing else;
   the OpenSearch domain's access policy names exactly the indexing Lambda's
   role ARN, not `*`. This is the same least-privilege discipline as the core
   `workload_pipeline` module's `glue.tf`/`lambda.tf`.

3. **Decide: does this need a VPC?** Redshift Data API and OpenSearch's
   HTTPS/SigV4 endpoint are both public AWS-managed API endpoints reachable
   from any Lambda without VPC config — same as Athena/Glue/S3 already are.
   Redis has no such API; it's a raw TCP wire protocol, so the Lambda that
   talks to it **must** join a VPC. Once it also reads the quality-score
   sidecar from S3, it needs an S3 Gateway VPC endpoint (this account has no
   NAT). A Lambda that *only* spoke Redis would not need that endpoint.
   **This is the single biggest branch point when extending to a new service**:
   check whether the service exposes a signed HTTPS control-plane API (cheap,
   no networking) or a raw protocol (needs a VPC decision, security groups,
   subnet groups).

4. **Decide: lean Lambda or bundled dependency?** Every existing Lambda in
   this repo (`register_catalog`, `post_deploy_verifier`) is stdlib + boto3
   only — boto3 ships in the Lambda runtime, so the deployment zip stays a few
   KB. `register_redshift_spectrum` and `index_gold_to_opensearch` kept that
   rule: the Redshift Data API is a boto3 client call, and OpenSearch bulk
   indexing was implemented with `botocore.auth.SigV4Auth` + `urllib` instead
   of pulling in `opensearch-py`. `cache_quality_scores` is the one exception —
   there's no boto3 client for the Redis wire protocol, so `redis-py` had to be
   `pip install --target`-ed into that one zip in `deploy.yml`. **Prefer lean;
   bundle only when the AWS SDK genuinely has no surface for the service.**

5. **Wire it into the critical path only after the integration contract is
   explicit.** The three extensions started as standalone Lambdas, then were
   added as sequential SFN states after `RegisterCatalog`. Two contracts that
   were *not* obvious up front:
   - Glue `.sync` + `ResultPath: null` means later Lambdas **cannot** read
     quality scores from the execution input — they read an S3 sidecar.
   - Redis is VPC-only; if that Lambda also reads S3, add a **Gateway** VPC
     endpoint (do not assume NAT).
   - Redshift Data API without `SecretArn` runs as the Lambda IAM user and
     gets `permission denied for database dev`.
   A Parallel branch after Gold is still a valid alternative if you want
   warehouse/search/cache to run concurrently instead of in series.

6. **Instantiate from the root module, once per workload that needs it.**
   `iac/terraform/main.tf` adds `module "advisory_transactions_redshift"` etc.
   the same way it already instantiates `workload_pipeline` twice (once per
   workload) — new capability = new module block, not a new copy of the whole
   stack.

## What this cost, concretely

- 3 new Terraform modules (9 files), ~450 lines of HCL.
- 3 new Lambda scripts (~280 lines of Python), following the exact
  `run_local()` / `apply_*()` / `lambda_handler()` shape every other script in
  this repo uses.
- 1 new IAM role + 1 new Lambda per service (least-privilege, no shared roles).
- 1 VPC decision (Redis only) — reused the account's *default* VPC/subnets
  rather than building new networking, which is a demo-scale shortcut; a real
  rollout would target existing private subnets (see `docs/ADAPTATION_GAP.md`
  for the same "sandbox vs. enterprise" framing applied elsewhere).
- 1 packaging exception (`redis-py` bundled) vs. 2 packages that stayed lean.
- $0 in new IAM policy sprawl beyond what each service strictly needs — every
  new `data "aws_iam_policy_document"` in these modules is service-specific.

## Generalizing beyond AWS

Because each module's `variables.tf` only depends on generic inputs (workload
name, region, account id, bucket, tags) and never reaches into AWS-specific
globals, the same 6-step recipe is what a multi-cloud version of this
framework would need per *(capability, provider)* pair — e.g. `redshift_workload`
on AWS and `bigquery_workload` on GCP would be two modules implementing the
same *interface* (a queryable warehouse over Gold), selected by a provider
flag rather than duplicating the whole pipeline. That's the seed of the
Track B design-doc question: "what's the smallest set of capability
interfaces (warehouse, search, cache, object store, orchestrator) a workload
config needs to declare, independent of which cloud implements them?"
