# ADOP (Agentic Data Onboarding Platform) — Personal Sandbox Pilot Plan

**Prepared for:** Visu, Cloud Application Architect / Data Architect
**Purpose:** Evaluate AWS's ADOP reference architecture in a personal sandbox AWS account, with an eye toward a future client-facing (LPL-style regulated environment) pitch.
**Guiding principle:** Extract the *pattern*, not the tool. Everything here happens in an isolated sandbox account — nothing touches LPL/Perficient infrastructure.

---

## 1. Objectives

- Understand ADOP's agent architecture hands-on (Data Onboarding Agent, Quality Agent, DevOps Agent, etc.)
- Run the full pipeline lifecycle — from natural-language prompt to deployed, queryable data — at minimal cost
- Produce a concrete demo artifact (before/after time comparison, generated code samples, architecture walkthrough) usable in a client conversation
- Identify, firsthand, where the framework's assumptions break down for a regulated, centrally-governed AWS environment like LPL's — so the eventual client pitch is "pattern adaptation," not "tool adoption"

---

## 2. Cost Control Guardrails (do this first, before anything else)

- [ ] Set an **AWS Budget alert** on your personal account — recommended threshold **$25**, with email/SNS notification at 50%, 80%, 100%
- [ ] Confirm your AWS CLI default region and account before running anything (`aws sts get-caller-identity`)
- [ ] Default orchestration choice: **Step Functions + EventBridge Scheduler**, not MWAA — removes the ~$350–400/month always-on cost risk entirely
- [ ] If you ever do test MWAA, provision and destroy it via Terraform in the **same session**, and verify via `terraform state list | grep mwaa` before and after
- [ ] Never leave generated infrastructure running unattended overnight during the pilot phase

---

## 3. Prerequisites Checklist

| Item | Status | Notes |
|---|---|---|
| Python 3.9+ | ☐ | `python3 --version` |
| `uv` installed | ☐ | Required for MCP server auto-install |
| Claude Code CLI installed + authenticated | ☐ | |
| Git | ☐ | |
| AWS CLI configured with a **sandbox** account/profile | ☐ | Do NOT use LPL/Perficient credentials |
| AWS Budget alert set | ☐ | See Section 2 |
| Terraform installed | ☐ | For the DevOps Agent phase later |

---

## 4. Phased Plan

### Phase 0 — Zero-cost validation (Day 1)
**Goal:** Confirm the framework runs correctly with no AWS spend at all.

1. Clone the repo: `git clone https://github.com/aws-samples/sample-Agentic-Ai-Data-Operations`
2. `pip install -r requirements.txt`
3. Run the full local test suite: `pytest workloads/ -v` — this exercises the pre-built example workloads (including `financial_portfolios` [SOX] and `healthcare_patients` [HIPAA]) with **zero AWS dependency**
4. Read through the generated artifacts for `financial_portfolios/` — config, scripts, tests, README — to understand what "good output" looks like before generating your own
5. Review `CLAUDE.md`, `TOOL_ROUTING.md`, `MCP_GUARDRAILS.md` — these define the agent guardrails and are the "architectural contract" layer you'd eventually customize for a client

**Exit criteria:** All local tests pass; you've read through one full example workload end-to-end.

---

### Phase 1 — MCP + sandbox AWS wiring (Day 1–2)
**Goal:** Confirm tool connectivity without deploying anything expensive.

1. `claude mcp list` — confirm all 13 MCP servers connect (9 auto-install via `uvx`, 4 custom)
2. Confirm the 3 REQUIRED servers pass health checks: `glue-athena`, `lakeformation`, `iam`
3. Run the **Environment Setup Agent** (`prompts/environment-setup-agent/`) against your sandbox account — this provisions S3 buckets, KMS keys, Glue databases, Lake Formation settings
4. Spot-check what it created: S3 buckets, KMS keys (should be zone-specific — Bronze/Silver/Gold), Glue databases

**Exit criteria:** MCP servers healthy; base sandbox infrastructure exists and costs pennies (S3/KMS only, no compute running).

**Estimated cost:** <$5

---

### Phase 2 — First pipeline: generate only, don't deploy (Day 2–3)
**Goal:** Experience the core "natural language → pipeline artifacts" flow at near-zero cost.

1. Use synthetic/public data (not real LPL-adjacent data) — a simple CSV in S3 is fine
2. Write a prompt describing source, schema, cadence, and compliance framework (see the README's example prompts for shape/detail level)
3. Explicitly instruct: **target Step Functions, not Airflow**, for orchestration
4. Let the agent run Phases 0–4 (Health Check → Discovery → Dedup → Profile → Build)
5. **Stop before Phase 5 (Deploy).** Review the generated artifacts under `workloads/{name}/`: config YAMLs, PySpark scripts, quality rules, Step Functions definition, tests
6. Run the generated unit tests locally: `pytest workloads/{name}/tests/unit -v`

**Exit criteria:** You have a full, reviewed, tested pipeline definition — entirely generated, entirely unpaid-for beyond Bedrock token cost (~$0.75–3.65 per workload).

**Estimated cost:** <$5 (LLM tokens only)

---

### Phase 3 — Deploy for real, verify, tear down same day (Day 3–4)
**Goal:** See the deployed, working pipeline — for the shortest possible billable window.

1. Deploy: sync artifacts to S3 / apply the Step Functions Terraform
2. Run the mandatory post-deployment verifier (7 automated checks: Glue tables exist, Athena returns data, LF-Tags applied, KMS rotation enabled, orchestration loads without error, audit events logged)
3. Trigger one manual pipeline run, confirm data lands correctly in Bronze → Silver → Gold
4. Capture screenshots / a short screen recording for later client use
5. **Tear down same day**: `terraform destroy` (if Terraform-managed) or manually delete Glue jobs, Step Functions state machine, S3 test data
6. Confirm nothing is left running: check AWS Cost Explorer the next day

**Exit criteria:** One fully working, verified, deployed-and-destroyed pipeline, with demo material captured.

**Estimated cost:** $5–15

---

### Phase 4 — DevOps Agent / IaC exercise (Day 4–5, optional)
**Goal:** Understand the IaC generation path and its limits — this is the part most relevant to the LPL-modules conversation.

1. Run `/devops-workflow {workload_name} terraform`
2. Inspect the generated `.tf` files closely — check whether it references raw AWS resources or assumes reusable modules
3. Note every place a real client's module library would need to be substituted in (this becomes your "adaptation gap" analysis)
4. Do **not** apply this against anything beyond your sandbox

**Exit criteria:** A written list of exactly where ADOP's generated IaC would need adaptation to comply with an enterprise's existing Terraform module standards.

---

### Phase 5 — Synthesize into client-facing material (Day 5–6)
**Goal:** Convert the pilot into something presentable, without ever proposing to run ADOP against LPL's AWS estate directly.

Deliverables to produce:
- 1-page architecture overview (agents-in-dev / deterministic-artifacts-in-prod, Cedar guardrails, audit tracing)
- Before/after time comparison table (manual pipeline dev vs. agent-assisted, using your own pilot's numbers)
- "Adaptation gap" list from Phase 4 — this becomes the actual consulting pitch: *what LPL's platform team would need to build to run this pattern safely*
- Explicit framing: this is a demonstrated AWS reference pattern, not a proposal to deploy this specific codebase into a regulated environment

---

## 5. Explicit Non-Goals for This Pilot

- Do **not** connect this to any LPL/Perficient AWS account or credentials
- Do **not** use real client or regulated data, even synthetic-looking production exports
- Do **not** treat the generated Terraform as production-ready without a real module-compatibility review
- Do **not** leave MWAA (if tested at all) running unattended

---

## 6. Comparable Frameworks & Portability

There is no single drop-in "ADOP equivalent" for other AWS serving targets (OpenSearch, DynamoDB, Redshift). What exists is a spectrum of AWS-official building blocks that cover pieces of the same idea. This section captures the landscape so it can feed the Phase 5 client material and the "adaptation gap" narrative.

### Closest in spirit (agentic / AI-assisted)

- **AWS Labs MCP servers** (github.com/awslabs/mcp) — the most direct parallel. Official MCP servers give AI agents "hands" on specific services, including dedicated ones for **DynamoDB**, **Redshift**, **OpenSearch**, **Aurora/RDS**, and **Neptune**. ADOP composes a subset of these; the natural-language → target experience for other services is assembled from these plus your own agent prompts.
- **Amazon Q Developer** — general agentic code/IaC generation; not target-specific but can scaffold DynamoDB/Redshift/OpenSearch integration code and CDK/Terraform.
- **Amazon Bedrock Agents + AgentCore** — the primitives ADOP itself is built on; used to build a target-specific onboarding agent.

### Template / accelerator-driven (deterministic, not agentic)

| Target | Framework / Accelerator |
|---|---|
| **Redshift / analytics** | **AWS SDLF** (Serverless Data Lake Framework) — CloudFormation/CDK Bronze/Silver/Gold blueprints, ADOP's deterministic predecessor. **AWS DataOps Development Kit (DDK)** — CDK pipeline constructs. |
| **Redshift specifically** | Redshift Data API + zero-ETL integrations; **AWS Analytics Reference Architecture (ARA)** CDK library. |
| **OpenSearch** | **OpenSearch Ingestion (OSIS)** — config-driven ingestion (S3/DynamoDB/Kinesis → OpenSearch), the native "framework" for that target. |
| **DynamoDB** | AWS Amplify / CDK patterns for app-data; DynamoDB zero-ETL to OpenSearch/Redshift for downstream serving. |
| **Any (search-based)** | **serverless-patterns** (serverlessland.com/patterns) — hundreds of curated source→target IaC snippets. |

### The architectural read (for the client pitch)

ADOP is differentiated not because it targets S3/Glue/Athena, but because it bundles **agentic generation + compliance guardrails (Cedar / Lake Formation) + audit tracing** into one opinionated workflow. No published framework offers that same *end-to-end agentic + governed* experience for OpenSearch/DynamoDB/Redshift yet.

- **The pattern is portable** — swap the MCP servers (glue-athena → dynamodb/redshift/opensearch) and rewrite the Build-phase templates, and ADOP's *architecture* generalizes.
- **The packaging is not** — there is no drop-in agentic accelerator for those targets; you assemble it from AWS Labs MCP servers + Bedrock Agents + a deterministic accelerator (SDLF/DDK) for the IaC layer.

The differentiated value a client's platform team could build is *the governed agentic wrapper around whichever target service they need* — exactly what ADOP demonstrates for the lakehouse case.

### Adding a new sink to ADOP — two-tier effort model

Extending ADOP to a new target (e.g., OpenSearch) is **mostly integration + template work, not authoring a new MCP server**. The custom-server path is the exception, only when no official server exists or it lacks a governance operation you need.

- **Tier 1 — Integrate + extend templates (the common case).** Reuse an existing AWS Labs MCP server and teach ADOP to route to it and emit the sink.
- **Tier 2 — Author a custom MCP server (the exception).** Only if no official server covers the target, or the official one doesn't expose a required governance/index-template operation.

### Concrete steps — add OpenSearch as a sink

1. **Provisioning path (Tier 1 or 2):**
   - Check for an existing AWS Labs OpenSearch MCP server (github.com/awslabs/mcp). If present, register it in ADOP's MCP config and confirm it health-checks like `glue-athena`/`lakeformation`.
   - If none covers your index-template/mapping + KMS/VPC governance needs, author a thin custom MCP server exposing just those operations (create domain, create index + mappings, apply access policy).
2. **Tool routing:** Add the OpenSearch server to `TOOL_ROUTING.md` (and any guardrail file like `MCP_GUARDRAILS.md`) so the agent is allowed to select it during the Build phase.
3. **Config schema:** Extend the workload config (e.g., `workloads/{name}/config/transformations.yaml` or a new `sink.yaml`) to allow declaring an `opensearch` target — domain endpoint, index name, id field, mapping/template, KMS key, VPC/subnet, and (for regulated envs) fine-grained access policy.
4. **Build-phase template:** Update the Build/transformation templates so a declared `opensearch` sink generates a Gold→OpenSearch indexing job. Options for the generated Glue/PySpark job:
   - `df.write.format("opensearch")…` via the `opensearch-hadoop` connector (bulk, high volume), or
   - a `boto3` / `opensearch-py` bulk-index step (smaller volumes, simpler IAM), or
   - **OpenSearch Ingestion (OSIS)** as the native pipeline (Gold S3 → OSIS → OpenSearch), keeping the agent responsible only for config generation.
5. **Orchestration:** Add a post-Gold step to the generated Step Functions state machine that runs the indexing job after Gold succeeds.
6. **Verification:** Extend the post-deployment verifier with an OpenSearch check (domain reachable, index exists, doc count > 0, access policy applied).
7. **Cost guardrail:** OpenSearch domains are always-on compute — provision/destroy same-session (like the MWAA note in Section 2) or use **OpenSearch Serverless** to stay inside the pilot budget.

---

## 7. LPL / Regulated-Environment Fit — What Breaks & How to Adapt

ADOP is a **pattern to adapt, not a tool to install** in a regulated, centrally-governed AWS estate. It would run technically, but hits governance blockers. Per Section 5, it must never be pointed at LPL/Perficient infrastructure — this analysis is for the client pitch and Phase 4 adaptation-gap work.

### What breaks

- **Permissions & agent autonomy** — ADOP agents expect broad create/modify rights (IAM, KMS, Glue, Lake Formation). SCPs / permission boundaries block agent-driven IAM and KMS creation; an LLM provisioning IAM live is a security-review non-starter.
- **IaC / module standards** — ADOP emits **raw AWS resources**, not calls to an approved client Terraform module library, so its output fails module-compliance review (this is the Phase 4 exercise).
- **Networking** — Regulated estates require private VPCs, VPC endpoints/PrivateLink, and egress controls; ADOP's MCP servers and generated jobs assume more open connectivity. Bedrock access may be restricted or region-locked.
- **Governance & compliance** — Existing Lake Formation tag taxonomy and central data-governance ownership; enterprise CMKs with fixed rotation/key policies; prod changes require tickets/approvals/audit — incompatible with an agent applying infra directly.
- **Data & model governance** — Bedrock model usage, data residency, and prompt/response logging must clear model-risk and DLP review before real data flows through the agent path.

### How to adapt

| ADOP does | In LPL you'd instead |
|---|---|
| Agent provisions IAM/KMS/LF live | Platform team pre-provisions via approved modules; agent only **generates artifacts** |
| Emits raw Terraform | Emit code that **calls LPL's module library** |
| Agent applies infra | Artifacts go through **CI/CD + change approval**; humans apply |
| Self-defined LF-Tags/KMS | Consume **central governance** taxonomy & CMKs |
| Open connectivity assumed | Run inside **private VPC + endpoints**, restricted egress |

**Client message:** adopt ADOP's *architecture* — agents-in-dev generating deterministic, reviewed artifacts; humans/CI deploy in prod; Cedar/LF guardrails; audit tracing — and let LPL's platform team build the **governed wrapper** around it, rather than run this codebase against their account.

---

## 8. Reference Links

- Repo: https://github.com/aws-samples/sample-Agentic-Ai-Data-Operations
- Styled docs site: https://aws-samples.github.io/sample-Agentic-Ai-Data-Operations/
- AWS Prescriptive Guidance — Governing agentic AI at scale (search: "AWS Prescriptive Guidance governing agentic AI at scale")
- AgentOps blog series on Bedrock AgentCore best practices (search: "AWS AgentOps Bedrock AgentCore governance blog")

---

*This plan is scoped for a personal sandbox pilot only. Any extension toward client infrastructure should go through your firm's and the client's standard security/architecture review process before any credential or environment is connected.*
