# Pilot status — what's done, what's left

Last verified live AWS run: Step Functions execution
`phase3-extensions-3` (**SUCCEEDED**, 2026-09-07). All 9 post-deploy checks
passed, including Redshift Spectrum, OpenSearch, and Redis.

## Phase checklist

| Phase | Track A (this repo on AWS) | Status |
|---|---|---|
| 0 | Credentials, region `us-east-1`, Terraform CLI, budget | **Done** |
| 1a | Data-lake bucket `adop-datalake-199064440913-us-east-1` | **Done** |
| 1b | `tools/package_and_sync.py` — scripts, flat Glue deps, Lambda zips | **Done** |
| 2 | `terraform apply` (core pipeline + Redshift + OpenSearch + Redis + `adop-pilot-monthly` budget) | **Done** |
| 3 | First Step Functions execution end-to-end | **Done** (`phase3-extensions-3`) |
| 4 | Lake Formation LF-Tags via `register_catalog` | **Done** (3 PII columns tagged) |
| 5 | Live `post_deployment_verifier` (9 checks, fail the state if any fail) | **Done** |
| 6 | Same-day teardown (`terraform destroy`) + confirm nothing bills overnight | **Not done** — stack is still up; you are watching billing |
| 7 | Design doc for your own cloud-native, multi-provider framework | **Not done** |

Track B (how the reference `aws-samples` ADOP repo would have done each step)
was deferred so we could finish a real deploy. It belongs with Phase 7.

## What a “full pipeline” means now

```
IngestToBronze → BronzeToSilver → SilverQualityGate → SilverToGold
  → GoldQualityGate → RegisterCatalog
  → RegisterRedshiftSpectrum → IndexGoldToOpenSearch → CacheQualityScores
  → PostDeploymentVerify → Succeed
```

`web_events` is still **PILOT-DISABLED** in `iac/terraform/main.tf` (advisory-only
sandbox). Local pytest for that workload still runs.

## Next decisions (your list)

1. **GitHub** — save this repo without `reference/` (see below).
2. **Demo timing** — `docs/DEMO_RUNBOOK.md`.
3. **Keep vs destroy** — same runbook.
4. **Failure taxonomy** — `docs/PILOT_FAILURES_AND_FIXES.md`.
5. **Docs** — README / ARCHITECTURE / PHASE3 / EXTENDING updated to match AWS.
6. **Leftover phases** — 6 (teardown) and 7 (your framework design doc).
