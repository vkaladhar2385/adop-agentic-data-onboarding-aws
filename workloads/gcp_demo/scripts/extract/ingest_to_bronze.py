# spec_hash: aa0576e1e75809ae2b6e70903ace21c890e8156cd5348966e5ea6c12d07f2fb0
# template_id: ingest_to_bronze
# template_hash: b0b17535abbfbffe9a9d90122d60998510b9e0b46f429db47ff3e2809a297a49
# schema_version: v1
# rendered_at: 2026-10-01T23:35:13Z
"""Ingest -> Bronze for `gcp_demo` (GCS landing)."""
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
    target = out / "bronze_gcp_demo.parquet"
    df.to_parquet(target, index=False)
    print(f"[bronze] landed {len(df)} rows -> {target}")
    return str(target)


def run_gcp():  # pragma: no cover
    ap = argparse.ArgumentParser()
    ap.add_argument("--src_path", required=True)
    ap.add_argument("--bronze_path", required=True, help="gs:// Bronze target")
    args, _ = ap.parse_known_args()
    import pandas as pd

    df = pd.read_csv(args.src_path)
    df.to_parquet(args.bronze_path, index=False)
    print(f"[bronze] landed {len(df)} rows -> {args.bronze_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--src", default="output/gcp_demo/source.csv")
    ap.add_argument("--out", default="output/gcp_demo")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.src, args.out)
    else:
        run_gcp()
