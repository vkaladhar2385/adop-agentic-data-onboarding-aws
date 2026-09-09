#!/usr/bin/env python3
"""Validate workload YAML configs against contracts/v1 JSON Schemas."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = REPO_ROOT / "contracts" / "v1"

CONFIG_SCHEMA_MAP = {
    "compute.yaml": "compute.schema.json",
    "transformations.yaml": "transformations.schema.json",
}

CODEGEN_SCHEMA_MAP = {
    "ingest_to_bronze.spec.yaml": "codegen_ingest_to_bronze.spec.schema.json",
    "bronze_to_silver.spec.yaml": "codegen_bronze_to_silver.spec.schema.json",
    "silver_to_gold.spec.yaml": "codegen_silver_to_gold.spec.schema.json",
    "quality_checks.spec.yaml": "codegen_quality_checks.spec.schema.json",
    "state_machine.spec.yaml": "codegen_state_machine.spec.schema.json",
    "dag.spec.yaml": "codegen_dag.spec.schema.json",
}


def load_schema(name: str) -> dict:
    with (CONTRACTS / name).open(encoding="utf-8") as fh:
        return json.load(fh)


def validate_yaml_against_schema(path: Path, schema_name: str) -> list[str]:
    schema = load_schema(schema_name)
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    return [f"{path}: {err.message}" for err in errors]


def validate_file(path: Path) -> list[str]:
    schema_name = CONFIG_SCHEMA_MAP.get(path.name)
    if not schema_name:
        return []
    return validate_yaml_against_schema(path, schema_name)


def validate_codegen_spec(path: Path) -> list[str]:
    schema_name = CODEGEN_SCHEMA_MAP.get(path.name)
    if not schema_name:
        return [f"{path}: unknown codegen spec filename (no schema contract)"]
    return validate_yaml_against_schema(path, schema_name)


def main(argv: list[str] | None = None) -> int:
    del argv
    errors: list[str] = []
    validated_config: list[Path] = []
    validated_codegen: list[Path] = []

    for path in sorted(REPO_ROOT.glob("workloads/*/config/*.yaml")):
        if path.name in CONFIG_SCHEMA_MAP:
            validated_config.append(path)
        errors.extend(validate_file(path))

    for path in sorted(REPO_ROOT.glob("workloads/*/config/codegen/*.spec.yaml")):
        validated_codegen.append(path)
        errors.extend(validate_codegen_spec(path))

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        print("validate_configs: FAIL", file=sys.stderr)
        return 1

    for path in validated_config:
        print(f"OK {path.relative_to(REPO_ROOT)}")
    for path in validated_codegen:
        print(f"OK {path.relative_to(REPO_ROOT)}")
    print(
        f"validate_configs: PASS "
        f"({len(validated_config)} config, {len(validated_codegen)} codegen specs)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
