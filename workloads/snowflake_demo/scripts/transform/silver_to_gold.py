# spec_hash: 71752bb44a0c44ec643e663359acdf9b4bdc204dd19b2ba35ae1969308a3bac7
# template_id: silver_to_gold
# template_hash: 5ab38f44eb29b862d0cdaaedb667275bd72389e0aa729bae875f89c8bbd4b026
# schema_version: v1
# rendered_at: 2026-10-02T00:01:16Z
"""Silver -> Gold for `snowflake_demo` (Snowflake Snowpark, native tables)."""
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
SILVER_SCHEMA = "SILVER"
GOLD_SCHEMA = "GOLD"
SILVER_TABLE = "silver_snowflake_demo"
GOLD_TABLE = "gold_snowflake_demo"


def run_local(silver_parquet: str, out_dir: str) -> dict:
    import pandas as pd

    cfg = local_runner.load_config("transformations.yaml")
    silver = pd.read_parquet(silver_parquet)
    gold = local_runner.silver_to_gold(silver, cfg)
    out = Path(out_dir)
    (out / "gold").mkdir(parents=True, exist_ok=True)
    gold.to_parquet(out / "gold" / "gold_snowflake_demo.parquet", index=False)
    print(f"[gold] rows={len(gold)}")
    return {"gold": gold}


def run_snowpark():  # pragma: no cover
    from snowflake.snowpark import Session

    session = Session.builder.appName("snowflake_demo_silver_to_gold").getOrCreate()
    silver_df = session.table(f"{DATABASE}.{SILVER_SCHEMA}.{SILVER_TABLE}")
    gold_df = spark_transforms.silver_to_gold_df(silver_df) if spark_transforms else silver_df
    fqn = f"{DATABASE}.{GOLD_SCHEMA}.{GOLD_TABLE}"
    gold_df.write.mode("overwrite").save_as_table(fqn)
    print(f"[gold] {fqn}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--silver", default="output/snowflake_demo/silver/silver_snowflake_demo.parquet")
    ap.add_argument("--out", default="output/snowflake_demo")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.silver, args.out)
    else:
        run_snowpark()
