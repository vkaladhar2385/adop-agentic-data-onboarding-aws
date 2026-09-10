# Adaptation Gap — What a Regulated Enterprise Must Add

This is the **honest** part of the pitch (and the actual consulting backlog). ADOP's
generated artifacts are excellent starting points, but they assume a greenfield/raw
setup. In a centrally-governed environment (e.g. an LPL-style landing zone) the
following must be substituted or added. Each item below is a scoped work package.

> **Update:** the Glue-job/Lambda IaC gap and the Lake Formation/verifier code
> gaps that used to be listed here have been closed — see
> [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) and the "closed" note at the end of
> this file. What remains below is genuine enterprise-integration work, not
> missing demo code.

## 1. IaC: raw resources -> approved module library
- **Gap:** generated Terraform declares raw `aws_kms_key`, `aws_iam_role`, etc.
  (now organized as a reusable `modules/workload_pipeline` module instantiated
  once per workload — see `iac/terraform/main.tf` — but still *raw* AWS
  resources, not the client's own module library).
- **Adaptation:** replace with the client's mandated modules (`module "kms"`,
  `module "s3_bucket"`, `module "iam_role"`), inheriting tagging, naming, logging,
  and boundary policies.
- **Files:** `iac/terraform/main.tf`, `iac/terraform/modules/workload_pipeline/*.tf`.

## 2. IAM: permissions boundaries + no self-authored roles
- **Gap:** demo creates roles directly.
- **Adaptation:** roles created via the platform team's vending process, with
  permissions boundaries attached; CI assumes pre-provisioned roles only.

## 3. Networking: VPC, endpoints, no public paths
- **Gap:** demo omits VPC wiring.
- **Adaptation:** Glue connections in private subnets; S3/Glue/KMS/STS VPC endpoints;
  egress controls; no internet-facing resources.

## 4. Data classification -> the firm's taxonomy
- **Gap:** LF-Tags use generic `PII_Type` / `Data_Sensitivity`.
- **Adaptation:** map to the client's data-classification standard and existing
  LF-Tag ontology and TBAC role grants.

## 5. Landing zone / multi-account topology
- **Gap:** single-account defaults.
- **Adaptation:** wire catalog-account vs consumer-account split, RAM shares, and
  `sts:AssumeRole` chains to match Control Tower OUs.

## 6. Orchestration standards
- **Gap:** standalone Step Functions state machine.
- **Adaptation:** conform to the client's naming, logging (execution history to
  centralized CloudWatch/S3), and error-routing/runbook standards.

## 7. CI/CD: house pipeline + change management
- **Gap:** sample GitHub Actions.
- **Adaptation:** port to the client's CI system (or CodePipeline), integrate change
  tickets/approvals, artifact signing, and environment promotion policy.

## 8. Secrets & connections
- **Gap:** placeholder connection strings.
- **Adaptation:** Secrets Manager / approved connection registry only
  (already required by the `no-credentials-in-code` invariant).

## 9. Compliance evidence & retention
- **Gap:** retention declared in config.
- **Adaptation:** wire S3 lifecycle + Object Lock (WORM) for 7-year SOX retention;
  route CloudTrail to the central audit account; produce audit evidence artifacts.

## 10. Model governance for the agents themselves
- **Gap:** agent runs are ad hoc in the pilot.
- **Adaptation:** govern the Dev agent environment (Bedrock AgentCore, prompt/version
  pinning, human-approval gates, decision-trace retention) per the firm's AI policy.

---

### How to use this in the room
Present items 1–10 as the **scoped statement of work**. The message: the pattern is
proven (this repo); the engagement is wiring it safely into *their* estate. That is
consulting value the client cannot get from the open-source repo alone.

---

## Closed since the last review ("close the gap" pass)
These were previously listed as gaps in this document and are now implemented in the repo
(still sandbox-grade, not enterprise-hardened — that's still items 1–10 above):

| Was a gap | Now |
|---|---|
| No `aws_glue_job` resources | 5 per workload (10 total), `iac/terraform/modules/workload_pipeline/glue.tf` |
| No Lambda resources for `register_catalog` / `post_deploy_verifier` | 4 `aws_lambda_function` resources, `lambda.tf`, real `lambda_handler()` entrypoints in the Python scripts |
| Lake Formation apply was print-only | `apply_lf_tags()` in each workload's `register_catalog.py` calls real `boto3 lakeformation` APIs (falls back to a printed plan when boto3/creds are absent) |
| Verifier checks 2/3/6 were stubbed `True` | `shared/utils/post_deployment_verifier.py` now runs real Athena, Lake Formation, and CloudTrail boto3 calls |
| `<account>` literal in ASL SNS ARNs | Both state machines use Terraform `templatefile()` placeholders (`${account_id}`, `${aws_region}`), substituted at `terraform apply` time |
| `web_events` pipeline was 3 steps (no ingest, no Gold gate, no catalog/verify) | Symmetric 8-state pipeline identical in shape to `advisory_transactions` |
| Single-workload Terraform (`var.workload` default) | Reusable module, root `main.tf` instantiates it once per workload |
| Lambda packaging undefined | `deploy.yml` builds lean, dependency-free zips (stdlib + boto3 only) and uploads to S3 before `terraform apply` |

Remaining before an actual `terraform apply` in a live sandbox: nothing code-side — use
`tools/provision_sandbox.py` or `tools/deploy_workload.py` when ready (`docs/SANDBOX_LIFECYCLE.md`).
