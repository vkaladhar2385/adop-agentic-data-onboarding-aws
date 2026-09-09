#!/usr/bin/env python3
"""Pre-commit hook: validate Cedar policy syntax before commit."""

from __future__ import annotations

import re
import sys
from pathlib import Path

POLICIES_DIR = Path(__file__).resolve().parents[2] / "policies"
SCHEMA_FILE = POLICIES_DIR / "schema.cedarschema"


def validate_with_cedarpy(filepath: str, content: str) -> tuple[bool, list[str]]:
    try:
        import cedarpy

        if not hasattr(cedarpy, "is_authorized"):
            return False, []
        return False, []
    except ImportError:
        return False, []


def validate_structure(filepath: str, content: str) -> list[str]:
    errors: list[str] = []
    is_schema = filepath.endswith(".cedarschema")

    if not content.strip():
        errors.append(f"{filepath}: file is empty")
        return errors

    open_braces = content.count("{")
    close_braces = content.count("}")
    if open_braces != close_braces:
        errors.append(
            f"{filepath}: unbalanced braces — {open_braces} opening vs {close_braces} closing"
        )

    open_parens = content.count("(")
    close_parens = content.count(")")
    if open_parens != close_parens:
        errors.append(
            f"{filepath}: unbalanced parentheses — {open_parens} opening vs {close_parens} closing"
        )

    if is_schema:
        if "entity" not in content.lower() and "action" not in content.lower():
            errors.append(f"{filepath}: schema file missing 'entity' or 'action' definitions")
    else:
        has_forbid = bool(re.search(r"\bforbid\b", content))
        has_permit = bool(re.search(r"\bpermit\b", content))
        if not has_forbid and not has_permit:
            errors.append(f"{filepath}: policy file must contain 'forbid' or 'permit'")
        if not re.search(r"\bprincipal\b", content):
            errors.append(f"{filepath}: missing 'principal' in policy")
        if not re.search(r"\baction\b", content):
            errors.append(f"{filepath}: missing 'action' in policy")
        if not re.search(r"\bresource\b", content):
            errors.append(f"{filepath}: missing 'resource' in policy")

    return errors


def validate_file(filepath: str) -> list[str]:
    try:
        content = Path(filepath).read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{filepath}: cannot read file: {exc}"]

    attempted, cedarpy_errors = validate_with_cedarpy(filepath, content)
    if attempted:
        return cedarpy_errors
    return validate_structure(filepath, content)


def main() -> int:
    if len(sys.argv) < 2:
        return 0

    all_errors: list[str] = []
    for filepath in sys.argv[1:]:
        all_errors.extend(validate_file(filepath))

    if not all_errors:
        return 0

    print("\n  CEDAR POLICY VALIDATOR — Syntax errors found\n")
    for error in all_errors:
        print(f"  [BLOCK] {error}")
    print(f"\n  {len(all_errors)} error(s) found. Fix before committing.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
