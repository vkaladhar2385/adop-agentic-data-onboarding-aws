#!/usr/bin/env python3
"""Render codegen artifacts from config/codegen/*.spec.yaml (ADOP factory subset)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.codegen.drift_validator import verify_artifact  # noqa: E402
from shared.codegen.renderer import render  # noqa: E402
from shared.codegen.spec_loader import compute_spec_hash, load_yaml_spec  # noqa: E402

ARTIFACTS = {
    "bronze_to_silver": {
        "spec": "config/codegen/bronze_to_silver.spec.yaml",
        "template_id": "advisory_bronze_to_silver",
        "output": "scripts/transform/bronze_to_silver.py",
    },
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workload", required=True)
    ap.add_argument("--artifact", choices=sorted(ARTIFACTS), default="bronze_to_silver")
    ap.add_argument("--write", action="store_true", help="Write rendered file to disk")
    ap.add_argument("--check-drift", action="store_true", help="Fail if artifact drifted from spec")
    args = ap.parse_args(argv)

    meta = ARTIFACTS[args.artifact]
    wl_dir = REPO_ROOT / "workloads" / args.workload
    spec_path = wl_dir / meta["spec"]
    out_path = wl_dir / meta["output"]

    spec = load_yaml_spec(spec_path)
    spec_hash = compute_spec_hash(spec)
    content = render(spec, spec_hash, meta["template_id"], schema_version=spec.get("schema_version", "v1"))

    if args.write:
        out_path.write_text(content, encoding="utf-8", newline="\n")
        print(f"Wrote {out_path.relative_to(REPO_ROOT)}")

    if args.check_drift:
        report = verify_artifact(out_path, spec_path, "")
        if not report.ok:
            print(f"DRIFT: {report.path}: {report.reason}", file=sys.stderr)
            return 1
        print(f"OK no drift: {report.path}")

    if not args.write and not args.check_drift:
        print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
