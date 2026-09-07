# How ADOP Fits an Existing AWS + CI/CD Estate

The whole point: **no rip-and-replace.** Agents run in Dev and emit git-committed
artifacts. Your existing pipeline promotes them. Only native AWS services run in
your accounts.

## Environment model (agents never touch prod)

```
 DEVELOPMENT (agent zone)              GIT / CI-CD                 AWS RUNTIME (per env)
 ─────────────────────────            ───────────────            ───────────────────────
 Claude Code + ADOP agents            PR: ci.yml                  QA  -> Staging -> Prod
   Data Onboarding Agent      ──►      - pytest (17)       ──►     Step Functions
   Quality / Transform / DAG          - validate configs          Glue jobs (PySpark)
   DevOps Agent (IaC)                 - terraform validate        S3 + Iceberg (Bronze/
        │  generate only                                          Silver/Gold)
        ▼                             merge -> deploy.yml         KMS (zone-scoped)
   workloads/…  +  iac/…              - OIDC assume-role          Lake Formation (LF-Tags)
   (committed to git)                 - terraform apply           EventBridge Scheduler
                                      - s3 sync artifacts         SNS + CloudTrail
                                      - post-deploy verify
```

## Service mapping (all services you likely already run)

| Concern | AWS service | In this repo |
|---|---|---|
| Storage / zones | S3 + S3 Tables (Iceberg) | `sql/*`, `config/source.yaml` |
| ETL | AWS Glue (PySpark) | `scripts/transform/*` |
| Query | Athena | `sql/gold/*` example queries |
| Encryption | KMS (per-zone CMK, rotation) | `iac/terraform/main.tf` |
| Column security | Lake Formation LF-Tags (TBAC) | `scripts/load/register_catalog.py` |
| Orchestration | Step Functions | `orchestration/*_state_machine.json` |
| Scheduling | EventBridge Scheduler | `orchestration/eventbridge_schedule.json` |
| Alerting | SNS | ASL `NotifyFailure` / IaC topic |
| Audit | CloudTrail | post-deploy verifier |
| Cost guardrail | AWS Budgets | `iac/terraform/main.tf` |

## CI/CD mapping (GitHub Actions shown; portable to CodePipeline / GitLab / Azure DevOps)

| Stage | GitHub Actions | Equivalent elsewhere |
|---|---|---|
| PR validation | `.github/workflows/ci.yml` | CodeBuild buildspec / GitLab `test` / Azure `ci` |
| Auth to AWS | OIDC `configure-aws-credentials` | CodePipeline role / GitLab OIDC / Azure WIF |
| Approvals | GitHub `environment` gates | CodePipeline manual approval / protected envs |
| Deploy | `deploy.yml` -> terraform apply + s3 sync | CodeDeploy/CDK pipeline stage |
| Post-deploy gate | `post_deployment_verifier.py` | same script, any runner |

## Security posture that travels with every workload

- **No long-lived keys** — CI authenticates via OIDC to a least-privilege role.
- **Dev agents have no AWS creds** — enforced by design + Cedar `sub-agent-no-mcp`.
- **Invariants as code** — immutable Bronze, mandatory data lineage, zone-scoped KMS,
  PII masking in logs, quality gates that block promotion.
- **Everything version-controlled** — auditable diffs, instant git rollback.

## Multi-account landing zones

ADOP supports a split topology (catalog + Lake Formation in one account, Glue/S3 in a
consumer account) with `sts:AssumeRole` wiring parameterized in the generated IaC —
which maps cleanly onto a typical Control Tower / landing-zone setup.
