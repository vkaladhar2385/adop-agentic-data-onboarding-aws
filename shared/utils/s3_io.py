"""Minimal S3 read/write helpers for AWS Glue Python Shell jobs.

Python Shell jobs don't get PySpark, and adding s3fs/fsspec just to read a
handful of demo-scale files would be a heavier dependency than this warrants
-- these wrap boto3 + pandas directly, reading/writing whole objects into
memory. Fine at this dataset size; a real production volume would move back
to PySpark (see docs/EXTENDING_TO_NEW_SERVICES.md-style trade-off notes in
each script's run_glue()).

Also provides `get_arg`, a minimal Glue-style argument reader that tolerates
the extra flags Glue always injects (--JOB_NAME, --JOB_RUN_ID, --additional-
python-modules, etc.) without needing a strict argparse schema -- the whole
reason the original run_glue() stubs broke was argparse rejecting exactly
those injected flags.
"""
from __future__ import annotations

import io
import sys
from urllib.parse import urlparse

import boto3
import pandas as pd


def parse_s3_uri(uri: str) -> tuple[str, str]:
    p = urlparse(uri)
    if p.scheme != "s3":
        raise ValueError(f"not an s3:// URI: {uri}")
    return p.netloc, p.path.lstrip("/")


def list_keys(prefix_uri: str, suffix: str | None = None) -> list[str]:
    bucket, prefix = parse_s3_uri(prefix_uri)
    s3 = boto3.client("s3")
    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if suffix is None or obj["Key"].endswith(suffix):
                keys.append(obj["Key"])
    return keys


def read_csv_prefix(prefix_uri: str, **kwargs) -> pd.DataFrame:
    bucket, _ = parse_s3_uri(prefix_uri)
    s3 = boto3.client("s3")
    frames = []
    for key in list_keys(prefix_uri, suffix=".csv"):
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        frames.append(pd.read_csv(io.BytesIO(body), **kwargs))
    if not frames:
        raise FileNotFoundError(f"no .csv objects under {prefix_uri}")
    return pd.concat(frames, ignore_index=True)


def read_parquet_object(uri: str) -> pd.DataFrame:
    """Read exactly one Parquet object (not every object under its prefix)."""
    bucket, key = parse_s3_uri(uri)
    body = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
    return pd.read_parquet(io.BytesIO(body))


def read_parquet_prefix(prefix_uri: str) -> pd.DataFrame:
    bucket, _ = parse_s3_uri(prefix_uri)
    s3 = boto3.client("s3")
    frames = []
    for key in list_keys(prefix_uri, suffix=".parquet"):
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        frames.append(pd.read_parquet(io.BytesIO(body)))
    if not frames:
        raise FileNotFoundError(f"no .parquet objects under {prefix_uri}")
    return pd.concat(frames, ignore_index=True)


def write_parquet(df: pd.DataFrame, uri: str) -> None:
    bucket, key = parse_s3_uri(uri)
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=buf.getvalue())


def write_csv(df: pd.DataFrame, uri: str) -> None:
    bucket, key = parse_s3_uri(uri)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=buf.getvalue().encode("utf-8"))


def write_json(obj, uri: str) -> None:
    import json
    bucket, key = parse_s3_uri(uri)
    boto3.client("s3").put_object(
        Bucket=bucket, Key=key, Body=json.dumps(obj, default=str).encode("utf-8"),
        ContentType="application/json",
    )


def get_arg(name: str, default: str | None = None) -> str | None:
    """Scan sys.argv for `--name value` or `--name=value`, ignoring every
    other flag (Glue injects several we don't care about)."""
    flag = f"--{name}"
    argv = sys.argv
    for i, tok in enumerate(argv):
        if tok == flag and i + 1 < len(argv):
            return argv[i + 1]
        if tok.startswith(flag + "="):
            return tok.split("=", 1)[1]
    return default
