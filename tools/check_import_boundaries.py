#!/usr/bin/env python3
"""Enforce the Phase 7 import boundary.

`workloads/` and `shared/` must stay cloud-neutral: they must NOT import from or
reference `platform-packs/*`. Only `tools/` (render/deploy drivers) may bridge
the neutral core to a platform pack. This keeps the factory one SKU and lets
`platform-packs/` be promoted to a submodule later without touching the core.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARDED_DIRS = ("workloads", "shared")

# Sanctioned bridge: the codegen renderer is the single resolver that maps a
# profile to its pack's template *directory* (template data, not pack code). It
# may reference the platform-packs path; nothing else under shared/ or
# workloads/ may.
ALLOWLIST = {Path("shared/codegen/renderer.py")}

# Matches `import platform_packs...`, `from platform_packs...`, or a literal
# path reference to the pack tree.
PATTERNS = (
    re.compile(r"^\s*(?:from|import)\s+platform[_-]packs", re.MULTILINE),
    re.compile(r"platform-packs[\\/]"),
    re.compile(r"platform_packs\."),
)


def _rel(path: Path) -> Path:
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


def scan_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    hits = []
    for pat in PATTERNS:
        if pat.search(text):
            hits.append(f"{_rel(path)}: references platform pack ({pat.pattern})")
    return hits


def main(argv: list[str] | None = None) -> int:
    del argv
    violations: list[str] = []
    scanned = 0
    for guarded in GUARDED_DIRS:
        for path in (REPO_ROOT / guarded).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if _rel(path) in ALLOWLIST:
                continue
            scanned += 1
            violations.extend(scan_file(path))

    if violations:
        for v in violations:
            print(f"ERROR: {v}", file=sys.stderr)
        print("check_import_boundaries: FAIL", file=sys.stderr)
        return 1
    print(f"check_import_boundaries: PASS ({scanned} files scanned, no pack imports)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
