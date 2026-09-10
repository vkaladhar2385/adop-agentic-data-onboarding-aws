"""Local equivalent of deploy.yml's `package_and_sync` job.

APPLY_GUIDE.md assumes the CI workflow has already put Glue scripts and Lambda
zips in S3 before `terraform apply` runs. When applying by hand (no GitHub
Actions), run this first. Uses Python's zipfile rather than shell `zip` so the
archives get POSIX separators Lambda can load, regardless of host OS.

    python tools/package_and_sync.py --bucket <data-lake-bucket> [--workload advisory_transactions]

Packaging rules mirror deploy.yml: lean zips (stdlib + boto3, which the Lambda
runtime ships) for everything except cache_quality_scores, which must bundle
redis-py because Redis has no AWS-signed HTTP API. See
docs/EXTENDING_TO_NEW_SERVICES.md#trade-offs.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = REPO_ROOT / "build"

# Files every Lambda zip needs, relative to the repo root.
_SHARED = ["shared/utils/pii.py", "shared/utils/post_deployment_verifier.py"]

# short name -> {extra files to include, pip packages to vendor}
LAMBDAS: dict[str, dict] = {
    "register_catalog": {"scripts": ["scripts/load/register_catalog.py"], "pip": []},
    "post_deploy_verifier": {"scripts": [], "pip": []},
    "register_redshift_spectrum": {"scripts": ["scripts/load/register_redshift_spectrum.py"], "pip": []},
    "index_gold_to_opensearch": {"scripts": ["scripts/load/index_gold_to_opensearch.py"], "pip": []},
    "cache_quality_scores": {"scripts": ["scripts/load/cache_quality_scores.py"], "pip": ["redis"]},
}


def _touch_packages(build: Path, workload: str) -> None:
    """Create the __init__.py chain so dotted handler paths resolve."""
    for pkg in (
        "shared", "shared/utils", "workloads",
        f"workloads/{workload}", f"workloads/{workload}/scripts",
        f"workloads/{workload}/scripts/load",
    ):
        d = build / pkg
        d.mkdir(parents=True, exist_ok=True)
        (d / "__init__.py").touch()


def lambdas_for_workload(workload: str) -> dict[str, dict]:
    """Build only Lambda zips whose workload scripts exist (catalog-only vs extensions)."""
    selected: dict[str, dict] = {}
    for name, spec in LAMBDAS.items():
        scripts = spec.get("scripts") or []
        if not scripts:
            selected[name] = spec
            continue
        if all((REPO_ROOT / "workloads" / workload / rel).is_file() for rel in scripts):
            selected[name] = spec
    return selected


def build_zip(name: str, spec: dict, workload: str) -> Path:
    build = BUILD_ROOT / workload / name
    if build.exists():
        shutil.rmtree(build)
    _touch_packages(build, workload)

    for rel in _SHARED:
        shutil.copy2(REPO_ROOT / rel, build / rel)
    for rel in spec["scripts"]:
        shutil.copy2(REPO_ROOT / "workloads" / workload / rel, build / "workloads" / workload / rel)

    for package in spec["pip"]:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "--target", str(build), package],
            check=True,
        )

    archive = BUILD_ROOT / workload / f"{name}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(build.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(build).as_posix())
    return archive


# Flat modules (no package hierarchy) + flat config files that Glue Python
# Shell jobs pull in via --extra-py-files / --extra-files (glue.tf). Glue
# deploys those into the job's working dir as plain files, NOT an extracted
# package tree, so dotted imports like `shared.utils.pii` can't resolve there
# -- hence the flat names and the try/except ImportError fallbacks in each
# job script and in local_runner.py itself.
_GLUE_FLAT_PY = {
    "pii.py": "shared/utils/pii.py",
    "quality.py": "shared/utils/quality.py",
    "s3_io.py": "shared/utils/s3_io.py",
    "local_runner.py": "workloads/{workload}/scripts/transform/local_runner.py",
    "spark_transforms.py": "workloads/{workload}/scripts/transform/spark_transforms.py",
}
_GLUE_FLAT_CONFIG = {
    "transformations.yaml": "workloads/{workload}/config/transformations.yaml",
    "quality_rules.yaml": "workloads/{workload}/config/quality_rules.yaml",
}


def sync_glue_deps_flat(s3, bucket: str, workload: str) -> tuple[list[str], list[str]]:
    """Upload the flat .py/.yaml deps and return their S3 URIs, for
    --extra-py-files / --extra-files (glue.tf default_arguments)."""
    py_uris, cfg_uris = [], []
    for flat_name, rel_tmpl in _GLUE_FLAT_PY.items():
        src = REPO_ROOT / rel_tmpl.format(workload=workload)
        key = f"glue-deps/{workload}/{flat_name}"
        s3.upload_file(str(src), bucket, key)
        py_uris.append(f"s3://{bucket}/{key}")
    for flat_name, rel_tmpl in _GLUE_FLAT_CONFIG.items():
        src = REPO_ROOT / rel_tmpl.format(workload=workload)
        key = f"glue-deps/{workload}/{flat_name}"
        s3.upload_file(str(src), bucket, key)
        cfg_uris.append(f"s3://{bucket}/{key}")
    return py_uris, cfg_uris


def sync_workload_scripts(s3, bucket: str, workload: str) -> int:
    """Upload workloads/<workload>/** so Glue jobs can find their script_location."""
    src = REPO_ROOT / "workloads" / workload
    count = 0
    for path in src.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        key = f"workloads/{workload}/{path.relative_to(src).as_posix()}"
        s3.upload_file(str(path), bucket, key)
        count += 1
    return count


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--workload", default="advisory_transactions")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--skip-upload", action="store_true", help="Build zips only; don't touch AWS.")
    args = ap.parse_args()

    lambda_specs = lambdas_for_workload(args.workload)
    archives = {name: build_zip(name, spec, args.workload) for name, spec in lambda_specs.items()}
    for name, archive in archives.items():
        print(f"[package] {name}: {archive.stat().st_size / 1024:.1f} KB")

    if args.skip_upload:
        print("[package] --skip-upload set; nothing uploaded.")
        return 0

    import boto3
    session = boto3.Session(profile_name=args.profile) if args.profile else boto3.Session()
    s3 = session.client("s3")

    n = sync_workload_scripts(s3, args.bucket, args.workload)
    print(f"[sync] uploaded {n} workload files to s3://{args.bucket}/workloads/{args.workload}/")

    py_uris, cfg_uris = sync_glue_deps_flat(s3, args.bucket, args.workload)
    print(f"[upload] glue-deps/{args.workload}/: {len(py_uris)} .py + {len(cfg_uris)} .yaml (flat, for --extra-py-files/--extra-files)")

    for name, archive in archives.items():
        key = f"lambda-artifacts/{args.workload}/{name}.zip"
        s3.upload_file(str(archive), args.bucket, key)
        print(f"[upload] s3://{args.bucket}/{key}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
