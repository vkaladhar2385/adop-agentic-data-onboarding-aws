# Platform vision — from medallion factory to general DE on AWS

**North star:** A **spec-driven data engineering platform on AWS** with **human-in-the-loop deploy** — agents help discover, validate, and provision pipelines; IaC and codegen stay the source of truth for production paths.

**Today:** An **agentic factory for governed lakehouse (medallion) pipelines** — the reference profile.  
**Target (~6 months):** The same platform shell supports **multiple DE profiles** (not only Bronze/Silver/Gold), still without heavy always-on compute.

This doc is the **strategy + AWS scope** reference. Implementation status lives in [`STATUS.md`](STATUS.md).

---

## What we mean by “general DE platform”

| Term | Meaning |
|------|---------|
| **General DE** | Composable batch/lake patterns: ingest, transform, quality, catalog, optional warehouse/search — driven by **specs**, not one-off scripts |
| **Not in v1 scope** | EMR/Spark clusters, always-on streaming platforms, “any arbitrary notebook job,” full MLOps |
| **Serverless-first** | Glue (ETL + Python Shell), Lambda, Step Functions, S3, Iceberg, Athena, Lake Formation — scale per run, not per cluster |

We are **not** building “Spark everywhere.” We are building **repeatable DE onboarding + deploy** on managed AWS services.

---

## Pitch (client-facing)

### Today

> **Agentic factory for governed lakehouse pipelines, extensible to other DE profiles.**

- Specs in YAML → generated Glue scripts and Step Functions
- Bronze → Silver → Gold on **Iceberg**, quality gates, catalog + LF-Tags
- **Cursor or Harness** for discovery; **APPROVE** before deploy
- **Option B:** Harness → AWS factory (CodeBuild + SFN) — no laptop deploy path
- Sandbox **provision / destroy** for demos without idle spend

### Target (~6 months)

> **Spec-driven DE platform on AWS with human-in-the-loop deploy.**

- **Pipeline profiles** (medallion, ingest-only, batch SQL, …) on the same agent + Gateway + factory shell
- Spec upload (S3) and job registry — not git-only workloads
- Composable Step Functions steps; audit trail per run
- Same governance: validation, codegen drift, Cedar/sub-agent boundaries

---

## AWS footprint (in scope)

What a fully demo’d sandbox typically contains:

| Category | AWS services | Role |
|----------|--------------|------|
| **Storage** | S3, KMS (zone keys) | Landing, Bronze/Silver/Gold Iceberg, artifacts, audit JSON |
| **Compute** | Glue ETL (PySpark), Glue Python Shell | Transforms vs lightweight quality/sidecar steps |
| **Orchestration** | Step Functions, EventBridge Scheduler | Medallion pipeline + factory provision SFN |
| **Catalog & access** | Glue Data Catalog, Lake Formation, LF-Tags | Tables, PII tags, grants |
| **Query** | Athena | Verify, ad-hoc checks |
| **Deploy** | Terraform, CodeBuild | Workload modules + factory repo sync |
| **Agents** | Bedrock Harness, AgentCore Gateway, Lambda (MCP targets) | Discovery, tools, `trigger_provision` |
| **Notify** | SNS | Pipeline / quality failures |
| **Optional extensions** | Redshift Serverless, OpenSearch, ElastiCache | Pilot extensions — **disable for low-cost demos** |

### Explicitly out of scope (unless separate engagement)

| Service / pattern | Why |
|-------------------|-----|
| **EMR / EMR Serverless** | Heavy ops, cluster mindset — conflicts with serverless cost guardrails |
| **Always-on MWAA** | Hourly cost; MWAA is opt-in demo only |
| **Always-on OpenSearch / Redshift / Redis** | Hourly cost; destroy when not demoing |
| **Generic “run any JAR”** | No job registry + profile contract yet |

Streaming-lite (Kinesis → S3, Lambda) may appear as a **future profile**, not EMR-based stream processing.

---

## Architecture (conceptual)

```text
                    ┌─────────────────────┐
                    │  Bedrock Harness    │  Human: discovery + APPROVE
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ AgentCore Gateway   │  MCP tools (catalog, LF, factory, …)
                    └──────────┬──────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
   Specs + codegen        Terraform modules      factory SFN
   (workloads/*/config)    (Glue, SFN, Lambda)     → CodeBuild → E2E
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               ▼
              S3 (Iceberg) + Glue Catalog + Lake Formation
```

**Factory path (Option B):** [`API_ONLY_FACTORY.md`](API_ONLY_FACTORY.md) · [`FACTORY_PROVISION_DESIGN.md`](FACTORY_PROVISION_DESIGN.md)

---

## Today vs target (product)

| Dimension | Today (shipped) | Target (platform) |
|-----------|-----------------|-------------------|
| **Pipeline shape** | Medallion B/S/G + quality gates | **Profiles:** medallion, ingest-only, batch SQL, … |
| **Workload definition** | Git repo `workloads/{name}/` | Registry + optional S3 spec upload |
| **Codegen** | 5 templates (ingest, b2s, s2g, quality, SFN) | Profile-specific template packs |
| **Deploy** | Laptop `deploy_workload.py` or Harness factory | Same HITL; profile-aware CodeBuild |
| **Agents** | Onboarding + MCP ops | + profile selection at discovery |
| **Compute** | Glue ETL + Shell | + Lambda for small steps; still no EMR |
| **Proof** | 5 workloads, Option B E2E green | 2+ profiles E2E through Harness |

~**60–70%** of current code (Gateway, Harness, MCP, lifecycle, audit, IaC patterns) transfers to the platform. ~**30–40%** (zone rules, medallion templates, quality gates) stays profile-specific until abstracted.

---

## Evolution roadmap (phases)

### Phase 1 — Platform shell (~4–6 weeks)

- Introduce `pipeline_profile` in config (`medallion` default)
- Job / workload **registry** (YAML or DynamoDB)
- Document rebuild path: factory resync vs full Terraform ([`PERSONAL_SANDBOX_RUNBOOK.md`](PERSONAL_SANDBOX_RUNBOOK.md))
- Medallion remains **Profile A** — no regression

### Phase 2 — Second profile (~3–4 weeks)

Pick one non-medallion pattern, e.g.:

- **`ingest_only`** — land → catalog → optional Athena check  
- **`medallion_lite`** — Bronze + Silver only  

New codegen + SFN variant; prove “same factory, different shape.”

### Phase 3 — Spec-from-outside-git (~3–4 weeks)

- S3 `client-specs/` + validation
- Harness / factory accepts registered jobs without a git commit

### Phase 4 — Composable ops (~6–8 weeks)

- Step library for Step Functions
- Run history, cost notes, audit (extend `provision-runs/`)
- Optional Kinesis→S3 profile (no EMR)

**Rough total:** 4–6 months part-time to a credible **general DE platform v1** (two+ profiles, Harness deploy, serverless only).

---

## Positioning for Perficient

| Audience | Message |
|----------|---------|
| **Technical** | Serverless AWS DE factory: specs, codegen, Iceberg, SFN, agents, Terraform |
| **Executive** | Faster time-to-lake with governance and approval gates — not black-box ETL |
| **Honest boundary** | Medallion-first today; platform extensibility is roadmap, not marketing fluff |

Do **not** claim “any DE workload” until **Phase 2** ships with a second green E2E profile.

---

## Related docs

| Doc | Topic |
|-----|--------|
| [`STATUS.md`](STATUS.md) | Milestones done / deferred |
| [`CLIENT_PITCH.md`](CLIENT_PITCH.md) | Narrative for presentations |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Current artifact map |
| [`EXTENDING_TO_NEW_SERVICES.md`](EXTENDING_TO_NEW_SERVICES.md) | Adding Redshift / OpenSearch / Redis |
| [`AGENTS.md`](../AGENTS.md) | Agent contract (medallion rules today) |
| [`ADAPTATION_GAP.md`](ADAPTATION_GAP.md) | Enterprise backlog |
