#!/usr/bin/env python3
"""
Validate workloads/*/config/compute.yaml and optional drift vs Terraform glue_jobs.

ADOP parallel: official ADOP uses shared.codegen.drift_validator to ensure
generated scripts match JSON specs (re-render + hash compare). This tool is the
Track A stepping stone — compute.yaml is the spec; Terraform glue_jobs is the
deployed intent. Drift between them means the agent contract is lying.

Usage:
  python tools/validate_compute.py                    # all workloads with compute.yaml
  python tools/validate_compute.py --workload advisory_transactions
  python tools/validate_compute.py --strict-terraform # fail on TF drift even if pending
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
TERRAFORM_MAIN = REPO_ROOT / "iac" / "terraform" / "main.tf"

VALID_JOB_TYPES = frozenset({"glueetl", "pythonshell"})
ICEBERG_TRANSFORM_STEPS = frozenset({"bronze_to_silver", "silver_to_gold"})
QUALITY_STEP_PREFIX = "quality_"

# Terraform: job_key = { script_path = "...", job_type = "..." ... }
GLUE_JOB_ENTRY_RE = re.compile(
    r"(\w+)\s*=\s*\{[^}]*?script_path\s*=\s*\"([^\"]+)\"[^}]*?"
    r"job_type\s*=\s*\"([^\"]+)\"",
    re.DOTALL,
)


@dataclass
class Issue:
    level: str  # error | warning
    message: str


@dataclass
class WorkloadReport:
    workload: str
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.level == "error" for i in self.issues)


def load_compute_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: root must be a mapping")
    return data


def _resolve_effective_job_type(step: str, step_cfg: dict, profile: dict, defaults: dict) -> str:
    explicit = step_cfg.get("job_type")
    if explicit and explicit != "auto":
        return explicit

    peak = profile.get("peak_rows_per_run") or 0
    if step == "ingest_to_bronze":
        if peak > 50_000:
            return "glueetl"
        return "pythonshell"

    if step in ICEBERG_TRANSFORM_STEPS:
        silver_fmt = profile.get("silver_format", "")
        gold_fmt = profile.get("gold_format", "")
        if step == "bronze_to_silver" and silver_fmt == "iceberg":
            return "glueetl"
        if step == "silver_to_gold" and gold_fmt == "iceberg":
            return "glueetl"
        return defaults.get("transform_job_type", "glueetl")

    if step.startswith(QUALITY_STEP_PREFIX):
        return defaults.get("quality_job_type", "pythonshell")

    return explicit or defaults.get("transform_job_type", "glueetl")


def validate_compute_rules(workload_dir: Path, data: dict) -> list[Issue]:
    issues: list[Issue] = []
    workload = data.get("workload")
    if not workload:
        issues.append(Issue("error", "missing top-level 'workload'"))
        return issues

    if workload != workload_dir.name:
        issues.append(
            Issue(
                "error",
                f"workload field '{workload}' does not match directory '{workload_dir.name}'",
            )
        )

    profile = data.get("profile") or {}
    defaults = data.get("defaults") or {}
    steps: dict = data.get("pipeline_steps") or {}
    if not steps:
        issues.append(Issue("error", "pipeline_steps is empty or missing"))
        return issues

    silver_fmt = profile.get("silver_format")
    gold_fmt = profile.get("gold_format")

    for step_name, step_cfg in steps.items():
        if not isinstance(step_cfg, dict):
            issues.append(Issue("error", f"pipeline_steps.{step_name} must be a mapping"))
            continue

        job_type = _resolve_effective_job_type(step_name, step_cfg, profile, defaults)
        if job_type not in VALID_JOB_TYPES:
            issues.append(
                Issue("error", f"{step_name}: invalid job_type '{job_type}'")
            )

        script = step_cfg.get("script")
        if not script:
            issues.append(Issue("error", f"{step_name}: missing 'script'"))
        else:
            script_path = workload_dir / script
            if not script_path.is_file():
                issues.append(Issue("error", f"{step_name}: script not found: {script}"))

        # Hard rule: Iceberg Silver/Gold transforms require glueetl (AGENTS.md)
        if step_name == "bronze_to_silver" and silver_fmt == "iceberg":
            if job_type != "glueetl":
                issues.append(
                    Issue(
                        "error",
                        f"{step_name}: silver_format=iceberg requires job_type=glueetl, got {job_type}",
                    )
                )
        if step_name == "silver_to_gold" and gold_fmt == "iceberg":
            if job_type != "glueetl":
                issues.append(
                    Issue(
                        "error",
                        f"{step_name}: gold_format=iceberg requires job_type=glueetl, got {job_type}",
                    )
                )

        if step_name in ICEBERG_TRANSFORM_STEPS and job_type == "glueetl":
            requires = step_cfg.get("requires") or []
            for flag in ("datalake-formats=iceberg", "enable-data-lineage=true"):
                if flag not in requires:
                    issues.append(
                        Issue(
                            "warning",
                            f"{step_name}: glueetl step should list '{flag}' in requires (Terraform defaults)",
                        )
                    )

    return issues


def _extract_balanced_block(text: str, start: int) -> tuple[str, int] | None:
    """Return (block_including_braces, index_after_block) from text[start] == '{'."""
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    i = start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1], i + 1
        i += 1
    return None


def parse_terraform_glue_jobs(main_tf: Path) -> dict[str, dict[str, dict[str, str]]]:
    """
    Parse module glue_jobs from main.tf without an HCL library.
    Returns {module_name: {job_key: {script_path, job_type}}}.
    """
    text = main_tf.read_text(encoding="utf-8")
    result: dict[str, dict[str, dict[str, str]]] = {}

    for mod_match in re.finditer(r'module\s+"([^"]+)"\s*\{', text):
        module_name = mod_match.group(1)
        mod_start = mod_match.end() - 1
        mod_block = _extract_balanced_block(text, mod_start)
        if not mod_block:
            continue
        mod_body, _ = mod_block

        gj_match = re.search(r"glue_jobs\s*=\s*\{", mod_body)
        if not gj_match:
            continue
        brace_start = mod_body.find("{", gj_match.start())
        gj_block = _extract_balanced_block(mod_body, brace_start)
        if not gj_block:
            continue
        gj_body, _ = gj_block

        jobs: dict[str, dict[str, str]] = {}
        for entry in GLUE_JOB_ENTRY_RE.finditer(gj_body):
            job_key, script_path, job_type = entry.groups()
            jobs[job_key] = {"script_path": script_path, "job_type": job_type}
        if jobs:
            result[module_name] = jobs

    return result


def compare_terraform(
    workload: str,
    data: dict,
    tf_jobs: dict[str, dict[str, str]] | None,
) -> list[Issue]:
    issues: list[Issue] = []
    if tf_jobs is None:
        issues.append(
            Issue(
                "warning",
                f"no glue_jobs block found in Terraform for module '{workload}'",
            )
        )
        return issues

    steps: dict = data.get("pipeline_steps") or {}
    profile = data.get("profile") or {}
    defaults = data.get("defaults") or {}

    tf_keys = set(tf_jobs)
    yaml_keys = set(steps)
    for missing in yaml_keys - tf_keys:
        issues.append(
            Issue(
                "warning",
                f"pipeline_steps.{missing} not present in Terraform glue_jobs",
            )
        )
    for extra in tf_keys - yaml_keys:
        issues.append(
            Issue(
                "warning",
                f"Terraform glue_jobs.{extra} not declared in compute.yaml pipeline_steps",
            )
        )

    for step_name in yaml_keys & tf_keys:
        yaml_type = _resolve_effective_job_type(
            step_name, steps[step_name], profile, defaults
        )
        tf_type = tf_jobs[step_name]["job_type"]
        yaml_script = steps[step_name].get("script", "")
        tf_script = tf_jobs[step_name]["script_path"]

        if yaml_type != tf_type:
            issues.append(
                Issue(
                    "warning",
                    f"DRIFT {step_name}: compute.yaml job_type={yaml_type}, "
                    f"Terraform job_type={tf_type}",
                )
            )
        if yaml_script and yaml_script != tf_script:
            issues.append(
                Issue(
                    "warning",
                    f"DRIFT {step_name}: compute.yaml script={yaml_script}, "
                    f"Terraform script_path={tf_script}",
                )
            )

    return issues


def validate_workload(
    workload_dir: Path,
    tf_modules: dict[str, dict[str, dict[str, str]]],
    strict_terraform: bool,
) -> WorkloadReport:
    compute_path = workload_dir / "config" / "compute.yaml"
    data = load_compute_yaml(compute_path)
    workload = data.get("workload") or workload_dir.name
    report = WorkloadReport(workload=workload)

    report.issues.extend(validate_compute_rules(workload_dir, data))

    sync_cfg = data.get("terraform_sync") or {}
    sync_status = sync_cfg.get("status", "enforced")

    tf_issues = compare_terraform(
        workload,
        data,
        tf_modules.get(workload),
    )

    drift_issues = [i for i in tf_issues if i.message.startswith("DRIFT")]
    other_tf = [i for i in tf_issues if not i.message.startswith("DRIFT")]

    if sync_status == "pending":
        for issue in drift_issues:
            report.issues.append(
                Issue(
                    "warning",
                    f"{issue.message} (terraform_sync.status=pending — expected until migration)",
                )
            )
        report.issues.extend(other_tf)
    elif strict_terraform or sync_status == "enforced":
        for issue in drift_issues:
            report.issues.append(Issue("error", issue.message))
        report.issues.extend(other_tf)
    else:
        report.issues.extend(tf_issues)

    return report


def discover_workloads(workload: str | None) -> list[Path]:
    if workload:
        path = REPO_ROOT / "workloads" / workload
        if not (path / "config" / "compute.yaml").is_file():
            raise SystemExit(f"No compute.yaml for workload: {workload}")
        return [path]
    return sorted(
        p.parent.parent
        for p in REPO_ROOT.glob("workloads/*/config/compute.yaml")
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate compute.yaml and Terraform glue_jobs drift.")
    parser.add_argument("--workload", help="Single workload name (default: all with compute.yaml)")
    parser.add_argument(
        "--strict-terraform",
        action="store_true",
        help="Fail on Terraform drift even when terraform_sync.status=pending",
    )
    args = parser.parse_args(argv)

    if not TERRAFORM_MAIN.is_file():
        print(f"ERROR: Terraform main not found: {TERRAFORM_MAIN}", file=sys.stderr)
        return 2

    tf_modules = parse_terraform_glue_jobs(TERRAFORM_MAIN)
    workloads = discover_workloads(args.workload)

    if not workloads:
        print("No workloads/*/config/compute.yaml found — nothing to validate.")
        return 0

    exit_code = 0
    for wl_dir in workloads:
        report = validate_workload(wl_dir, tf_modules, args.strict_terraform)
        print(f"\n=== {report.workload} ===")
        if not report.issues:
            print("OK — no issues")
            continue
        for issue in report.issues:
            prefix = issue.level.upper()
            print(f"  [{prefix}] {issue.message}")
            if issue.level == "error":
                exit_code = 1

    if exit_code == 0:
        print("\nvalidate_compute: PASS")
    else:
        print("\nvalidate_compute: FAIL", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
