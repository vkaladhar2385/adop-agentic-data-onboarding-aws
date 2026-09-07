"""Bronze ingestion for `advisory_transactions`.

Copies the daily source CSV into the immutable Bronze zone. On AWS this writes
Parquet to s3://.../bronze/... via Glue; locally it materialises Parquet under
the workload output dir. Bronze is NEVER transformed (ADOP `bronze-immutable`).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import sys
# On Glue this file is deployed standalone (flat, e.g. /tmp/glue-python-scripts-.../),
# so it may not have 4 parent directories -- `shared`/`workloads` come from
# --extra-py-files (glue.tf) in that case, and this insert is just a no-op.
_self = Path(__file__).resolve()
_REPO_ROOT = _self.parents[4] if len(_self.parents) > 4 else _self.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from workloads.advisory_transactions.scripts.transform.local_runner import ingest_bronze  # noqa: E402
except ImportError:
    # Glue Python Shell: local_runner.py is deployed flat via --extra-py-files (glue.tf).
    from local_runner import ingest_bronze  # type: ignore  # noqa: E402


def run_local(csv_path: str, out_dir: str) -> str:
    df = ingest_bronze(csv_path)
    out = Path(out_dir) / "bronze"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "bronze_advisory_transactions.parquet"
    df.to_parquet(target, index=False)
    print(f"[bronze] ingested {len(df)} rows (immutable) -> {target}")
    return str(target)


def run_glue():  # pragma: no cover - requires AWS runtime
    """Production path. Runs as a Glue Python Shell job (0.0625 DPU -- this
    dataset doesn't need Spark). Reads every CSV under --source_path, applies
    the same dtype-as-string ingest as run_local, writes one Parquet file to
    --bronze_path. Bronze is append-only/immutable per the ADOP
    `bronze-immutable` invariant, so this never mutates existing objects.
    """
    try:
        from shared.utils import s3_io
    except ImportError:
        import s3_io  # type: ignore

    source_path = s3_io.get_arg("source_path")
    bronze_path = s3_io.get_arg("bronze_path")
    if not source_path or not bronze_path:
        raise SystemExit("run_glue requires --source_path and --bronze_path")

    df = s3_io.read_csv_prefix(source_path, dtype=str, keep_default_na=False, na_values=[""])
    target = bronze_path.rstrip("/") + "/bronze_advisory_transactions.parquet"
    s3_io.write_parquet(df, target)
    print(f"[bronze] ingested {len(df)} rows (immutable) -> {target}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--source", default="demo/sample_data/advisory_transactions.csv")
    ap.add_argument("--out", default="output/advisory_transactions")
    # parse_known_args: Glue injects extra flags (--source_path, --JOB_NAME, ...)
    # that this local-mode parser doesn't declare; run_glue() reads sys.argv itself.
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.source, args.out)
    else:
        run_glue()
