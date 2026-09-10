# Git remotes — personal + corporate push

This repo can push to **two GitHub remotes** on your machine. Remote URLs are **local git config** — they are not committed to the repo.

---

## One-time setup (per clone)

```powershell
# Personal (if not already origin)
git remote add origin https://github.com/YOUR_USER/adop-agentic-data-onboarding-aws.git

# Corporate
git remote add perficient https://github.com/Perficient-Corporate/ai-agentic-data-onboarding.git

git remote -v
```

---

## Push script

From repo root:

```powershell
# Preview
python tools/git_push_both.py --dry-run

# Push current branch to both remotes
python tools/git_push_both.py

# First push of a new branch (sets upstream on each remote)
python tools/git_push_both.py --set-upstream

# One remote only
python tools/git_push_both.py --personal-only
python tools/git_push_both.py --corporate-only

# Explicit branch
python tools/git_push_both.py --branch feature/agent-contract
```

Manual equivalent:

```powershell
git push origin feature/agent-contract
git push perficient feature/agent-contract
```

---

## What to commit vs keep local

### Safe to check in (this mission)

| Path | Notes |
|------|--------|
| `docs/API_ONLY_FACTORY.md` | Harness-only demo |
| `docs/PERSONAL_SANDBOX_RUNBOOK.md` | Demo + destroy runbook |
| `docs/GIT_REMOTES.md` | This file |
| `docs/CLIENT_DEMO_RUNBOOK.md`, `FACTORY_PROVISION_DESIGN.md`, `MODE_C1_HARNESS.md` | Updated docs |
| `orchestration/factory_provision_state_machine.json` | Audit SFN step |
| `iac/terraform/modules/factory_provision/**` | Audit Lambda, IAM, SFN template |
| `iac/terraform/backend.tf.example` | S3 backend stub for CodeBuild |
| `shared/deploy/factory_provision.py` | Audit + provision library |
| `shared/deploy/sandbox_lifecycle.py` | Factory teardown |
| `shared/deploy/sfn_e2e.py` | E2E fixes |
| `tests/test_factory_provision.py` | Audit tests |
| `tools/git_push_both.py` | Dual push helper |
| `tools/factory_codebuild_deploy.py` | CodeBuild entry |
| `tools/invoke_agentcore_harness.py` | UTF-8 fix |
| `README.md` | Doc links |

### Do **not** commit

| Path | Why |
|------|-----|
| `iac/terraform/backend.hcl` | Contains **your account id** and bucket — copy from `backend.hcl.example` locally |
| `iac/terraform/terraform.tfvars` | Account-specific (already gitignored) |
| `iac/terraform/*.tfstate*` | Live resource IDs (gitignored) |
| `build/` | Generated deploy artifacts (gitignored) |
| `iac/terraform/backend.tf` | Optional: same as `backend.tf.example`; prefer **example only** if your team copies at init |

Add locally if missing:

```powershell
copy iac\terraform\backend.hcl.example iac\terraform\backend.hcl
# Edit YOUR_ACCOUNT, then never commit backend.hcl
```

---

## Suggested commit before push

After review, stage everything **except** secrets/scratch:

```powershell
git add docs/ README.md orchestration/ shared/ tests/ tools/git_push_both.py tools/factory_codebuild_deploy.py tools/invoke_agentcore_harness.py iac/terraform/modules/factory_provision/ iac/terraform/backend.tf.example
git status
```

Confirm `backend.hcl` and `terraform.tfvars` are **not** staged, then commit and push:

```powershell
python tools/git_push_both.py --set-upstream
```
