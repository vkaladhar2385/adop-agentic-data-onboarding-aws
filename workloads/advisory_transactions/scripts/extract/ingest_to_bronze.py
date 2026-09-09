# spec_hash: 246f330c9a769e3ad2b71a1f50695452c844f53cf8d5b5e701227489de0ae553
# template_id: ingest_to_bronze
# template_hash: cbf6bbb214796aedb3203a59c1cf5b1fb28daf2898565513dbe9033abe18916f
# schema_version: v1
# rendered_at: 2026-09-09T05:13:33Z
"""Bronze ingestion for `advisory_transactions`. Bronze is never transformed."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_self = Path(__file__).resolve()
_REPO_ROOT = _self.parents[4] if len(_self.parents) > 4 else _self.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from workloads.advisory_transactions.scripts.transform.local_runner import ingest_bronze
except ImportError:
    from local_runner import ingest_bronze  # type: ignore


def run_local(source_path: str, out_dir: str) -> str:
    df = ingest_bronze(source_path)
    out = Path(out_dir) / "bronze"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "bronze_advisory_transactions.parquet"
    df.to_parquet(target, index=False)
    print(f"[bronze] ingested {len(df)} rows (immutable) -> {target}")
    return str(target)


def run_glue():  # pragma: no cover
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
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.source, args.out)
    else:
        run_glue()
