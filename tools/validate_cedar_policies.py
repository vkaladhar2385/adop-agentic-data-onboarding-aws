#!/usr/bin/env python3
"""Validate Cedar policy syntax under shared/policies/."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.utils.hook_validators.cedar_validator import validate_file  # noqa: E402

POLICIES_DIR = REPO_ROOT / "shared" / "policies"


def main() -> int:
    paths = sorted(POLICIES_DIR.rglob("*.cedar*"))
    if not paths:
        print("No Cedar policy files found.", file=sys.stderr)
        return 1

    all_errors: list[str] = []
    for path in paths:
        all_errors.extend(validate_file(str(path)))

    if all_errors:
        print("\n  CEDAR POLICY VALIDATOR — errors found\n")
        for error in all_errors:
            print(f"  [BLOCK] {error}")
        print(f"\n  {len(all_errors)} error(s). Fix before committing.\n")
        return 1

    print(f"OK {len(paths)} Cedar file(s) validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
