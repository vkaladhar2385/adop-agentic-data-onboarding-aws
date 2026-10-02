# spec_hash: 5f274c8f4dccf7555e62b037bdce1d7de586a2b54c2cbcaf9851c4ad2a8f8e59
# template_id: bronze_to_silver
# template_hash: 186935ba69bfaf5846c6de9eaf5d291ce1c8faf044816f686d516e7ef8291e02
# schema_version: v1
# rendered_at: 2026-10-02T00:01:16Z
"""Bronze -> Silver for `snowflake_demo` (Snowflake Snowpark, native tables).

Local mode uses pandas for pytest. Rules from transformations.yaml.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_self = Path(__file__).resolve()
_REPO_ROOT = _self.parents[4] if len(_self.parents) > 4 else _self.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from workloads.snowflake_demo.scripts.transform import local_runner, spark_transforms
except ImportError:  # pragma: no cover
    local_runner = None  # type: ignore
    spark_transforms = None  # type: ignore

DATABASE = "snowflake_demo_db"
BRONZE_SCHEMA = "BRONZE"
SILVER_SCHEMA = "SILVER"
BRONZE_TABLE = "bronze_snowflake_demo"
SILVER_TABLE = "silver_snowflake_demo"


def run_local(bronze_parquet: str, out_dir: str) -> dict:
    import pandas as pd

    cfg = local_runner.load_config("transformations.yaml")
    bronze = pd.read_parquet(bronze_parquet)
    silver, quarantine = local_runner.bronze_to_silver(bronze, cfg)
    out = Path(out_dir)
    (out / "silver").mkdir(parents=True, exist_ok=True)
    (out / "quarantine").mkdir(parents=True, exist_ok=True)
    silver.to_parquet(out / "silver" / "silver_snowflake_demo.parquet", index=False)
    quarantine.to_csv(out / "quarantine" / "quarantine.csv", index=False)
    print(f"[silver] clean={len(silver)} quarantined={len(quarantine)}")
    return {"silver": silver, "quarantine": quarantine}


def run_snowpark():  # pragma: no cover
    from snowflake.snowpark import Session

    session = Session.builder.appName("snowflake_demo_bronze_to_silver").getOrCreate()
    bronze_df = session.table(f"{DATABASE}.{BRONZE_SCHEMA}.{BRONZE_TABLE}")
    if spark_transforms is not None:
        silver_df, _q = spark_transforms.bronze_to_silver_df(bronze_df)
    else:
        silver_df = bronze_df
    fqn = f"{DATABASE}.{SILVER_SCHEMA}.{SILVER_TABLE}"
    silver_df.write.mode("overwrite").save_as_table(fqn)
    print(f"[silver] {fqn}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--bronze", default="output/snowflake_demo/bronze/bronze_snowflake_demo.parquet")
    ap.add_argument("--out", default="output/snowflake_demo")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.bronze, args.out)
    else:
        run_snowpark()
