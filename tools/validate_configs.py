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

# config filename -> schema filename (skip files without a contract)
CONFIG_SCHEMA_MAP = {
    "compute.yaml": "compute.schema.json",
    "transformations.yaml": "transformations.schema.json",
}


def load_schema(name: str) -> dict:
    with (CONTRACTS / name).open(encoding="utf-8") as fh:
        return json.load(fh)


def validate_file(path: Path) -> list[str]:
    schema_name = CONFIG_SCHEMA_MAP.get(path.name)
    if not schema_name:
        return []

    schema = load_schema(schema_name)
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    return [f"{path}: {err.message}" for err in errors]


def main(argv: list[str] | None = None) -> int:
    errors: list[str] = []
    for path in sorted(REPO_ROOT.glob("workloads/*/config/*.yaml")):
        errors.extend(validate_file(path))

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        print("validate_configs: FAIL", file=sys.stderr)
        return 1

    validated = [p for p in REPO_ROOT.glob("workloads/*/config/*.yaml") if p.name in CONFIG_SCHEMA_MAP]
    for path in validated:
        print(f"OK {path.relative_to(REPO_ROOT)}")
    print("validate_configs: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
