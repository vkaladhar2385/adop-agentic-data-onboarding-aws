# spec_hash: fda5b867355762354eb348a07efaaafcde39de7ff487eb61ef2696d8c3833b9d
# template_id: ingest_to_bronze
# template_hash: d8a7c161345ec6d0b20b743547868e1268396cabb7f4ef97a1af3e4b39f1dc03
# schema_version: v1
# rendered_at: 2026-10-01T23:47:23Z
"""Ingest -> Bronze for `databricks_demo` (Databricks / UC volume landing)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_self = Path(__file__).resolve()
_REPO_ROOT = _self.parents[4] if len(_self.parents) > 4 else _self.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def run_local(src_path: str, out_dir: str) -> str:
    import pandas as pd

    df = pd.read_csv(src_path)
    out = Path(out_dir) / "bronze"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "bronze_databricks_demo.parquet"
    df.to_parquet(target, index=False)
    print(f"[bronze] landed {len(df)} rows -> {target}")
    return str(target)


def run_databricks():  # pragma: no cover
    ap = argparse.ArgumentParser()
    ap.add_argument("--src_path", required=True)
    ap.add_argument("--bronze_path", required=True)
    args, _ = ap.parse_known_args()
    import pandas as pd

    df = pd.read_csv(args.src_path)
    df.to_parquet(args.bronze_path, index=False)
    print(f"[bronze] landed {len(df)} rows -> {args.bronze_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--src", default="output/databricks_demo/source.csv")
    ap.add_argument("--out", default="output/databricks_demo")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.src, args.out)
    else:
        run_databricks()
