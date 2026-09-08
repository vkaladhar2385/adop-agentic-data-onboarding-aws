"""Load YAML specs and validate against contracts/v1."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
import yaml

from .exceptions import SpecValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "contracts" / "v1"


def canonical_json(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def compute_spec_hash(spec: dict) -> str:
    return hashlib.sha256(canonical_json(spec).encode("utf-8")).hexdigest()


def load_yaml_spec(path: Path) -> dict:
    with Path(path).open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: root must be a mapping")
    return data


def validate_against_schema(spec: dict, schema_name: str) -> None:
    schema_path = CONTRACTS_DIR / schema_name
    with schema_path.open(encoding="utf-8") as fh:
        schema = json.load(fh)
    validator = jsonschema.Draft202012Validator(schema)
    errors = [err.message for err in validator.iter_errors(spec)]
    if errors:
        raise SpecValidationError(str(schema_path), errors)
