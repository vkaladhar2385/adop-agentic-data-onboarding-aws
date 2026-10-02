# spec_hash: daecf9e0df80e5e8154a573dc15ddf30686b6f0e9ca0397f0f43bd953328041f
# template_id: ingest_to_bronze
# template_hash: 9cdbe8a5afe6d85ff634316c074d9d00c12afda7d3323ead78c4ee0ebd7b4e69
# schema_version: v1
# rendered_at: 2026-10-02T00:01:16Z
"""Ingest -> Bronze for `snowflake_demo` (Snowflake Snowpark + internal stage)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_self = Path(__file__).resolve()
_REPO_ROOT = _self.parents[4] if len(_self.parents) > 4 else _self.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

DATABASE = "snowflake_demo_db"
BRONZE_SCHEMA = "BRONZE"
BRONZE_TABLE = "bronze_snowflake_demo"


def run_local(src_path: str, out_dir: str) -> str:
    import pandas as pd

    df = pd.read_csv(src_path)
    out = Path(out_dir) / "bronze"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "bronze_snowflake_demo.parquet"
    df.to_parquet(target, index=False)
    print(f"[bronze] landed {len(df)} rows -> {target}")
    return str(target)


def run_snowpark():  # pragma: no cover
    from snowflake.snowpark import Session

    session = Session.builder.appName("snowflake_demo_ingest").getOrCreate()
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage_path", required=True)
    args, _ = ap.parse_known_args()
    df = session.read.options({"FIELD_OPTIONALLY_ENCLOSED_BY": '"'}).csv(args.stage_path)
    fqn = f"{DATABASE}.{BRONZE_SCHEMA}.{BRONZE_TABLE}"
    df.write.mode("overwrite").save_as_table(fqn)
    print(f"[bronze] {fqn} rows={df.count()}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--src", default="demo/sample_data/supplier_lead_times.csv")
    ap.add_argument("--out", default="output/snowflake_demo")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.src, args.out)
    else:
        run_snowpark()
