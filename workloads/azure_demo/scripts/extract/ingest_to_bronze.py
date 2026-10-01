# spec_hash: 822c0f4c5f28f5c3c9ff27da7b0186fa5aa5c182b14c5c4e597adb638f3ed68d
# template_id: ingest_to_bronze
# template_hash: a237af42d425f773f2963e2a5ca49cf3129ba52b5882ef536d63524669a8c22f
# schema_version: v1
# rendered_at: 2026-10-01T23:26:46Z
"""Ingest -> Bronze for `azure_demo` (Azure, ADLS Gen2).

Lands raw source into immutable Bronze on ADLS Gen2. Small/simple files use the
Python path (Azure Functions / Synapse Python); large files use Synapse Spark.
Source format: csv.
"""
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
    target = out / "bronze_azure_demo.parquet"
    df.to_parquet(target, index=False)
    print(f"[bronze] landed {len(df)} rows -> {target}")
    return str(target)


def run_azure():  # pragma: no cover - requires ADLS Gen2 auth
    """ADLS ingest. Args: --src_path --bronze_path (abfss://)."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--src_path", required=True)
    ap.add_argument("--bronze_path", required=True, help="abfss:// Bronze target (immutable)")
    args, _ = ap.parse_known_args()
    import pandas as pd

    df = pd.read_csv(args.src_path)
    df.to_parquet(args.bronze_path, index=False)
    print(f"[bronze] landed {len(df)} rows -> {args.bronze_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--src", default="output/azure_demo/source.csv")
    ap.add_argument("--out", default="output/azure_demo")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.src, args.out)
    else:
        run_azure()
