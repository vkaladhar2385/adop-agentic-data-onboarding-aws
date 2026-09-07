# Pilot failures and fixes

Categorized log of what broke while deploying `advisory_transactions` to the
sandbox (`us-east-1`, account `199064440913`) and how it was fixed. Use this
as the “we already paid for these lessons” list before the next account.

## A. Credentials and CLI (environment, not product bugs)

| Failure | Symptom | Fix |
|---|---|---|
| AWS CLI v1 vs v2 / SSO | Terraform Go SDK could not read `login_session` profile | `aws configure export-credentials --profile aws-agent` → `AWS_ACCESS_KEY_ID` / `SECRET` / `SESSION_TOKEN` |
| Session expiry mid-apply | OpenSearch create (~20 min) died with `ExpiredToken` | Re-`aws login`, `terraform untaint` if needed, re-apply |
| MCP `uvx` not on PATH | Cursor AWS MCP failed | Absolute path to `uvx.exe` in MCP settings |
| PowerShell quoting | `terraform apply -replace=module....job[\"x\"]` parsed wrong | `terraform apply --%` + escaped resource addresses |

**Pattern:** long AWS creates outlive SSO tokens. Export fresh env creds
immediately before `apply`, and do not start OpenSearch at the end of a
session.

## B. Networking / VPC (sandbox has no default VPC)

| Failure | Symptom | Fix |
|---|---|---|
| Redis assumed default VPC | `no matching EC2 VPC found` | `vpc_id` variable + `sandbox_vpc_id` |
| Redis SG description | Apostrophe rejected | Remove `'` from description |
| ElastiCache subnet group | Underscores invalid | Hyphens in name |
| Redshift Serverless | `A default VPC wasn't detected` | Explicit `subnet_ids` + workgroup SG |
| Redis Lambda in VPC + S3 sidecar | Timeout on `GetObject` (no NAT) | S3 **Gateway** VPC endpoint on the VPC route tables |

**Pattern:** never assume a default VPC. Redis is the only service that
*must* be in a VPC; give it a gateway endpoint for S3 rather than a NAT.

## C. Glue Python Shell (largest product-adaptation gap)

| Failure | Symptom | Fix |
|---|---|---|
| Python Shell 3.6 retired | `Python Shell version selected is no longer available` | `python_version = "3.9"` |
| Job type `glueetl` → `pythonshell` in place | `Worker Type is not supported for Job Command pythonshell` | `terraform apply -replace` on each job (cannot send `worker_type` on Python Shell) |
| `Path.parents[4]` on Glue | `IndexError: 4` | Depth-safe `_REPO_ROOT` |
| `--extra-py-files` zip of `shared/` | `No module named 'workloads'` | Flat files (`pii.py`, `quality.py`, `s3_io.py`, `local_runner.py` + two YAMLs) + `try/except ImportError` |
| Glue injects `--JOB_NAME` etc. | `argparse` rejected unknown flags | `parse_known_args()` / `s3_io.get_arg()` |
| Missing `pyarrow` | Parquet write fail | `--additional-python-modules=pyarrow==15.0.2` |

**Pattern:** demo-scale pandas does **not** need Spark. Python Shell is cheaper
but has a different packaging contract than `glueetl`. Document that in every
new job.

## D. Step Functions ASL (orchestration)

| Failure | Symptom | Fix |
|---|---|---|
| No `ResultPath` | After ingest, `$.bronze_path` gone; Glue job-run JSON replaced `$` | `"ResultPath": null` on every Task |
| Hardcoded SNS topic | `advisory-transactions-alerts` vs real `advisory_transactions-alerts` | `${workload}-alerts` via `templatefile` |
| Verifier payload incomplete | `KeyError: 'workload'` | Pass `workload`, `database`, `state_machine`, `table`, `pii_columns` |
| Verifier “passed: false” but SFN green | Checks were informational | `lambda_handler` now **raises** if any check fails |
| Input JSON BOM / `$input` | `InvalidExecutionInput` | ASCII file + PowerShell `$body` |

**Pattern:** Glue `.sync` tasks overwrite state. If later states need the
original input, you must keep `$` (`ResultPath: null`) or nest results.

## E. Quality / data shape

| Failure | Symptom | Fix |
|---|---|---|
| Gold gate read every parquet under `gold/` | Score ~0.62 (dims concatenated as nulls) | Grade only `fact_transactions/` (same as local runner) |
| Gold files all in one prefix | Catalog table would mix schemas | Write `gold/<table>/<table>.parquet` |

## F. Lake Formation and catalog

| Failure | Symptom | Fix |
|---|---|---|
| No Glue tables | `glue_tables_exist: false` | `register_catalog.register_tables()` (Silver + Gold fact) |
| `CreateLFTag` denied | Lambda not an LF principal | Add SSO admin as LF admin; `CREATE_TAG` + table `SELECT`/`ALTER` |
| Tag key exists, new value missing | `InvalidInputException: Tag key already exists` | `update_lf_tag(TagValuesToAdd=...)` |
| `UpdateLFTag` IAM missing | After the above | Add `lakeformation:UpdateLFTag` + LF `ALTER` on the tag (`TagValues=["*"]`) |

## G. Athena / verifier IAM

| Failure | Symptom | Fix |
|---|---|---|
| Results bucket fallback was the Glue DB name | Athena wrote to a non-existent bucket | `DATA_LAKE_BUCKET` / `athena-results/` |
| Verifier could not read Silver parquet | `athena_returns_data: false` | S3 Get on `silver/*` + `gold/*`, `kms:Decrypt`, `lakeformation:GetDataAccess` |
| Console “set a query result location” | Workgroup location set but not enforced | `EnforceWorkGroupConfiguration=true` on `primary` |
| OpenSearch Lambda Athena | `Unable to verify/create output bucket` | `s3:GetBucketLocation` on the lake bucket |

## H. Extensions (Redshift / OpenSearch / Redis)

| Failure | Symptom | Fix |
|---|---|---|
| OpenSearch domain name too long | `invalid value for domain_name` | `substr(workload, 0, 8)` → `advisory-dev-search` |
| Modules not in ASL | Pipeline “succeeded” without touching them | Three Task states after `RegisterCatalog` |
| Redis needed `{zone, score}` in the event | `ResultPath: null` discarded Glue output | Quality jobs write `s3://.../quality-scores/<w>/<zone>.json`; cache Lambda reads S3 |
| Redshift `permission denied for database dev` | Data API ran as the Lambda IAM user | `SecretArn` = namespace admin secret + `secretsmanager:GetSecretValue` |
| SFN role could not invoke extension Lambdas | Cycle if ARNs passed into `workload_pipeline` | Extra `aws_iam_role_policy` at **root** |

## What we would do first next time

1. Export SSO creds into the environment before any Terraform that can run
   longer than ~30 minutes.
2. Decide Python Shell vs Spark **before** the first `apply` (no in-place
   `glueetl` → `pythonshell`).
3. Put `ResultPath: null` on every SFN Glue/Lambda task that should keep
   the execution input.
4. Treat LF admin + `CREATE_TAG` as a Phase 0 checklist item, not a surprise
   at `RegisterCatalog`.
5. Wire warehouse/search/cache as SFN states from day one if the demo
   claims they are “in the pipeline.”
