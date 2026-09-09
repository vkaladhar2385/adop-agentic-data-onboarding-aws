"""Upload demo/synthetic landing data for a workload before SFN E2E."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_source(workload: str, repo_root: Path | None = None) -> dict:
    root = repo_root or REPO_ROOT
    path = root / "workloads" / workload / "config" / "source.yaml"
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def resolve_landing_s3_uri(
    workload: str,
    bucket: str,
    *,
    ingestion_date: date | None = None,
    repo_root: Path | None = None,
) -> tuple[str, str]:
    """Return (s3_uri, local_filename) from source.yaml location template."""
    source = _load_source(workload, repo_root)
    location = (source.get("source") or {}).get("location") or ""
    if not location:
        day = (ingestion_date or date.today()).isoformat()
        key = f"landing/{workload}/ingestion_date={day}/{workload}.csv"
        return f"s3://{bucket}/{key}", f"{workload}.csv"

    day = (ingestion_date or date.today()).isoformat()
    resolved = location.replace("YYYY-MM-DD", day)
    resolved = re.sub(r"data-lake-<account>-[^/]+", bucket, resolved)
    resolved = re.sub(r"s3://[^/]+", f"s3://{bucket}", resolved, count=1)

    if not resolved.startswith("s3://"):
        raise ValueError(f"unsupported source location: {location}")

    key = resolved.split("/", 3)[-1]
    filename = Path(key).name or f"{workload}.csv"
    return resolved, filename


def _generator_path(workload: str, repo_root: Path | None = None) -> Path | None:
    root = repo_root or REPO_ROOT
    gen = root / "demo" / "data_generators" / f"generate_{workload}.py"
    return gen if gen.is_file() else None


def _sample_csv_path(workload: str, repo_root: Path | None = None) -> Path | None:
    root = repo_root or REPO_ROOT
    sample = root / "demo" / "sample_data" / f"{workload}.csv"
    return sample if sample.is_file() else None


def prepare_local_csv(
    workload: str,
    *,
    ingestion_date: date | None = None,
    repo_root: Path | None = None,
    out_dir: Path | None = None,
) -> Path:
    """Generate or copy CSV; return local path."""
    root = repo_root or REPO_ROOT
    day = ingestion_date or date.today()
    _, filename = resolve_landing_s3_uri(workload, "placeholder", ingestion_date=day, repo_root=root)
    target_dir = out_dir or Path(tempfile.mkdtemp(prefix=f"adop-landing-{workload}-"))
    local_path = target_dir / filename

    generator = _generator_path(workload, root)
    if generator:
        cmd = [
            sys.executable,
            str(generator),
            "--date",
            day.isoformat(),
            "--out",
            str(local_path),
        ]
        print("+", " ".join(cmd), flush=True)
        subprocess.run(cmd, cwd=root, check=True)
        return local_path

    sample = _sample_csv_path(workload, root)
    if sample:
        local_path.write_bytes(sample.read_bytes())
        print(f"Copied sample data {sample} -> {local_path}")
        return local_path

    raise FileNotFoundError(
        f"No landing data for {workload}: add demo/data_generators/generate_{workload}.py "
        f"or demo/sample_data/{workload}.csv"
    )


def sync_landing_data(
    workload: str,
    bucket: str,
    *,
    ingestion_date: date | None = None,
    repo_root: Path | None = None,
    profile: str | None = None,
) -> str:
    """Generate/copy CSV and upload to landing prefix. Returns S3 URI."""
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 required for sync_landing_data") from exc

    root = repo_root or REPO_ROOT
    s3_uri, _ = resolve_landing_s3_uri(workload, bucket, ingestion_date=ingestion_date, repo_root=root)
    local_path = prepare_local_csv(workload, ingestion_date=ingestion_date, repo_root=root)

    _, _, key = s3_uri.partition("s3://")
    bucket_name, _, object_key = key.partition("/")

    session_kwargs = {}
    if profile:
        session_kwargs["profile_name"] = profile
    s3 = boto3.Session(**session_kwargs).client("s3")
    print(f"Uploading {local_path} -> s3://{bucket_name}/{object_key}", flush=True)
    s3.upload_file(str(local_path), bucket_name, object_key)
    print(f"Landing data ready: {s3_uri}", flush=True)
    return s3_uri
