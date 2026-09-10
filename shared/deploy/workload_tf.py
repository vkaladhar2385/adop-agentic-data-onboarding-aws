"""Generate Terraform workload_pipeline module blocks from workload config."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def load_workload_configs(workload: str, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    wl_dir = root / "workloads" / workload
    compute = _load_yaml(wl_dir / "config" / "compute.yaml")
    source = _load_yaml(wl_dir / "config" / "source.yaml")
    schedule = _load_yaml(wl_dir / "config" / "schedule.yaml")
    return {"workload_dir": wl_dir, "compute": compute, "source": source, "schedule": schedule}


def _compliance_tag(source: dict[str, Any], compute: dict[str, Any]) -> str:
    comp = (source.get("compliance") or {}).get("regulation")
    if comp:
        return str(comp).upper()
    profile = compute.get("profile") or {}
    if profile.get("compliance"):
        return str(profile["compliance"]).upper()
    return "none"


def _schedule_suffix(schedule: dict[str, Any], source: dict[str, Any]) -> str:
    cron = (schedule.get("schedule") or {}).get("cron") or ""
    freq = (source.get("cadence") or {}).get("frequency") or ""
    if "hour" in freq.lower() or " * * * ?" in cron:
        return "hourly"
    return "daily"


def _schedule_cron(schedule: dict[str, Any]) -> str:
    cron = (schedule.get("schedule") or {}).get("cron")
    if cron:
        return str(cron)
    return 'cron(0 7 * * ? *)'


def _database_name(workload: str, source: dict[str, Any]) -> str:
    zones = source.get("zones") or {}
    for zone in ("silver", "bronze", "gold"):
        db = (zones.get(zone) or {}).get("database")
        if db:
            return str(db)
    return f"{workload}_db"


def _silver_table(workload: str, source: dict[str, Any]) -> str:
    table = (source.get("zones") or {}).get("silver", {}).get("table")
    return str(table or f"silver_{workload}")


def _mcp_owners(workload: str, repo_root: Path | None = None) -> dict[str, str]:
    """Align with infrastructure_config: default terraform unless compute.yaml opts into MCP."""
    from shared.deploy.infrastructure_config import load_infrastructure_owners

    owners = load_infrastructure_owners(workload, repo_root)
    return {
        "catalog_owner": owners["catalog_owner"],
        "kms_owner": owners["kms_owner"],
        "iam_owner": owners["iam_owner"],
        "lakeformation_owner": owners["lakeformation_owner"],
    }


def _glue_job_hcl(step: str, spec: dict[str, Any], *, database: str, silver_table: str) -> str:
    script = spec.get("script") or spec.get("script_path") or f"scripts/{step}.py"
    if not script.startswith("scripts/"):
        script = f"scripts/{script}"
    job_type = spec.get("job_type", "pythonshell")
    if step.startswith("quality_"):
        zone = "silver" if "silver" in step else "gold"
        return (
            f'    {step} = {{ script_path = "{script}", job_type = "{job_type}", '
            f'default_arguments = {{ "--zone" = "{zone}", "--data_lake_bucket" = var.data_lake_bucket }} }}'
        )
    if job_type == "glueetl" and step == "bronze_to_silver":
        return (
            f"    {step} = {{\n"
            f'      script_path = "{script}",\n'
            f'      job_type      = "{job_type}",\n'
            f"      default_arguments = {{\n"
            f'        "--database"     = "{database}",\n'
            f'        "--silver_table" = "{silver_table}",\n'
            f"      }},\n"
            f"    }}"
        )
    if job_type == "glueetl" and step == "silver_to_gold":
        return (
            f"    {step} = {{\n"
            f'      script_path = "{script}",\n'
            f'      job_type      = "{job_type}",\n'
            f"      default_arguments = {{\n"
            f'        "--database" = "{database}",\n'
            f"      }},\n"
            f"    }}"
        )
    return f'    {step} = {{ script_path = "{script}", job_type = "{job_type}" }}'


def render_module_hcl(workload: str, repo_root: Path | None = None) -> str:
    cfg = load_workload_configs(workload, repo_root)
    compute = cfg["compute"]
    source = cfg["source"]
    schedule = cfg["schedule"]
    if not compute.get("pipeline_steps"):
        raise ValueError(f"{workload}: missing pipeline_steps in compute.yaml")

    root = repo_root or REPO_ROOT
    owners = _mcp_owners(workload, root)
    database = _database_name(workload, source)
    silver_table = _silver_table(workload, source)
    compliance = _compliance_tag(source, compute)
    cron = _schedule_cron(schedule)
    suffix = _schedule_suffix(schedule, source)

    glue_blocks = []
    for step, spec in compute["pipeline_steps"].items():
        if isinstance(spec, dict):
            glue_blocks.append(_glue_job_hcl(step, spec, database=database, silver_table=silver_table))

    glue_jobs = "\n".join(glue_blocks)
    handler_prefix = f"workloads.{workload}.scripts.load.register_catalog"

    return f"""# AUTO-GENERATED by tools/ensure_terraform_module.py — {date.today().isoformat()}
# Workload: {workload}. Regenerate; do not hand-edit.

module "{workload}" {{
  source = "./modules/workload_pipeline"

  catalog_owner       = "{owners['catalog_owner']}"
  kms_owner           = "{owners['kms_owner']}"
  iam_owner           = "{owners['iam_owner']}"
  lakeformation_owner = "{owners['lakeformation_owner']}"
  workload         = "{workload}"
  environment      = var.environment
  aws_region       = var.aws_region
  account_id       = var.account_id
  data_lake_bucket = var.data_lake_bucket
  alert_email      = var.alert_email
  compliance_tag   = "{compliance}"
  tags             = var.tags

  schedule_expression  = "{cron}"
  schedule_name_suffix = "{suffix}"
  state_machine_input = {{
    source_path = "s3://${{var.data_lake_bucket}}/landing/{workload}/"
    bronze_path = "s3://${{var.data_lake_bucket}}/bronze/{workload}/"
    silver_path = "s3://${{var.data_lake_bucket}}/silver/{workload}/"
    gold_path   = "s3://${{var.data_lake_bucket}}/gold/{workload}/"
  }}

  glue_jobs = {{
{glue_jobs}
  }}

  lambda_functions = {{
    register_catalog     = {{ handler = "{handler_prefix}.lambda_handler", artifact_key = "register_catalog" }}
    post_deploy_verifier = {{ handler = "shared.utils.post_deployment_verifier.lambda_handler", artifact_key = "post_deploy_verifier", timeout = 180 }}
  }}
}}
"""


def terraform_module_file(workload: str, terraform_dir: Path | None = None) -> Path:
    tf_dir = terraform_dir or (REPO_ROOT / "iac" / "terraform")
    return tf_dir / f"workloads_{workload}.tf"


def ensure_terraform_module(
    workload: str,
    *,
    repo_root: Path | None = None,
    terraform_dir: Path | None = None,
    dry_run: bool = False,
    update_compute_sync: bool = True,
) -> Path:
    """Write workloads_{workload}.tf and optionally flip terraform_sync to enforced."""
    root = repo_root or REPO_ROOT
    hcl = render_module_hcl(workload, root)
    out_path = terraform_module_file(workload, terraform_dir or (root / "iac" / "terraform"))

    if dry_run:
        print(f"[dry-run] would write {out_path}")
        print(hcl[:500] + "...")
        return out_path

    out_path.write_text(hcl, encoding="utf-8")
    print(f"Wrote {out_path}")

    if update_compute_sync:
        compute_path = root / "workloads" / workload / "config" / "compute.yaml"
        if compute_path.is_file():
            text = compute_path.read_text(encoding="utf-8")
            if "terraform_sync:" in text:
                text = re.sub(
                    r"(terraform_sync:\s*\n\s*status:\s*)pending",
                    r"\1enforced",
                    text,
                    count=1,
                )
                text = re.sub(
                    r"(terraform_sync:\s*\n\s*status:\s*)[^\n]+",
                    r"\1enforced",
                    text,
                    count=1,
                )
            compute_path.write_text(text, encoding="utf-8")
            print(f"Updated {compute_path} terraform_sync.status=enforced")

    return out_path


def terraform_module_declared(workload: str, terraform_dir: Path | None = None) -> bool:
    """True when module is in main.tf or auto-generated workloads_{name}.tf."""
    tf_dir = terraform_dir or (REPO_ROOT / "iac" / "terraform")
    auto_tf = tf_dir / f"workloads_{workload}.tf"
    if auto_tf.is_file() and re.search(
        rf'module\s+"{re.escape(workload)}"\s*\{{', auto_tf.read_text(encoding="utf-8")
    ):
        return True
    main_tf = tf_dir / "main.tf"
    if not main_tf.is_file():
        return False
    return bool(re.search(rf'module\s+"{re.escape(workload)}"\s*\{{', main_tf.read_text(encoding="utf-8")))
