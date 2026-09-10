#!/usr/bin/env python3
"""Zip ADOP repo for CodeBuild factory provision source (Option B Step 3).

Usage:
  python tools/package_factory_artifact.py --bucket adop-datalake-199064440913-us-east-1
  python tools/package_factory_artifact.py --bucket my-lake --dry-run
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".terraform",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    ".cursor",
    "build",
}
SKIP_SUFFIXES = {".pyc", ".zip", ".tfstate", ".tfstate.backup"}


def should_include(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT)
    for part in rel.parts:
        if part in SKIP_DIRS:
            return False
    if path.suffix in SKIP_SUFFIXES:
        return False
    if path.name.startswith(".env"):
        return False
    return True


def build_zip(out_path: Path) -> int:
    count = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in REPO_ROOT.rglob("*"):
            if not fp.is_file() or not should_include(fp):
                continue
            arc = fp.relative_to(REPO_ROOT).as_posix()
            zf.write(fp, arc)
            count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Package repo zip for factory CodeBuild")
    ap.add_argument("--bucket", required=True, help="S3 bucket for factory-artifacts/adop-repo.zip")
    ap.add_argument("--key", default="factory-artifacts/adop-repo.zip")
    ap.add_argument("--profile", default="aws-agent")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    files = build_zip(tmp_path)
    size_mb = tmp_path.stat().st_size / (1024 * 1024)
    print(f"Packed {files} files ({size_mb:.1f} MB) -> {tmp_path}")

    if args.dry_run:
        print("Dry run — zip not uploaded.")
        tmp_path.unlink(missing_ok=True)
        return 0

    dest = f"s3://{args.bucket}/{args.key}"
    cmd = ["aws", "s3", "cp", str(tmp_path), dest, "--profile", args.profile]
    print("+", " ".join(cmd))
    proc = subprocess.run(cmd, check=False)
    tmp_path.unlink(missing_ok=True)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
