# spec_hash: 7f9f6552837118528d39e6cb1db5faa1e97c4853f5c38bd80804d716142e1f07
# template_id: ingest_to_bronze
# template_hash: cbf6bbb214796aedb3203a59c1cf5b1fb28daf2898565513dbe9033abe18916f
# schema_version: v1
# rendered_at: 2026-09-09T05:17:05Z
"""Bronze ingestion for `supplier_lead_times`. Bronze is never transformed."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_self = Path(__file__).resolve()
_REPO_ROOT = _self.parents[4] if len(_self.parents) > 4 else _self.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from workloads.supplier_lead_times.scripts.transform.local_runner import ingest_bronze
except ImportError:
    from local_runner import ingest_bronze  # type: ignore


def run_local(source_path: str, out_dir: str) -> str:
    df = ingest_bronze(source_path)
    out = Path(out_dir) / "bronze"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "bronze_supplier_lead_times.parquet"
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
    target = bronze_path.rstrip("/") + "/bronze_supplier_lead_times.parquet"
    s3_io.write_parquet(df, target)
    print(f"[bronze] ingested {len(df)} rows (immutable) -> {target}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--source", default="demo/sample_data/supplier_lead_times.csv")
    ap.add_argument("--out", default="output/supplier_lead_times")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.source, args.out)
    else:
        run_glue()
