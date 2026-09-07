"""Silver -> Gold transform for `advisory_transactions`.

Builds the Gold star schema (fact_transactions + dim_account / dim_advisor /
dim_security / dim_date) plus an advisor daily-summary analytical table, and
enforces PII suppression (SSN/email/name dropped from Gold). Production writes
Iceberg to the Gold zone on Glue; local writes Parquet.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import sys
# On Glue this file is deployed standalone (flat); `shared`/`workloads` come
# from --extra-py-files (glue.tf) in that case, and this insert is a no-op.
_self = Path(__file__).resolve()
_REPO_ROOT = _self.parents[4] if len(_self.parents) > 4 else _self.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from workloads.advisory_transactions.scripts.transform import local_runner  # noqa: E402
except ImportError:
    import local_runner  # type: ignore  # noqa: E402 -- Glue Python Shell, flat via --extra-py-files


def run_local(silver_parquet: str, out_dir: str) -> dict:
    import pandas as pd
    cfg = local_runner.load_config("transformations.yaml")
    silver = pd.read_parquet(silver_parquet)
    gold = local_runner.silver_to_gold(silver, cfg)

    out = Path(out_dir) / "gold"
    out.mkdir(parents=True, exist_ok=True)
    for name, tbl in gold.items():
        tbl.to_parquet(out / f"{name}.parquet", index=False)
        print(f"[gold] {name}: {len(tbl)} rows")
    return gold


def run_glue():  # pragma: no cover - requires AWS runtime
    """Production path. Runs as a Glue Python Shell job, building the same
    star schema as local_runner.silver_to_gold (a real deployment would
    target Iceberg on S3 Tables). Writes one Parquet file per Gold table to
    --gold_path; PII columns are already suppressed by local_runner.
    """
    try:
        from shared.utils import s3_io
    except ImportError:
        import s3_io  # type: ignore

    silver_path = s3_io.get_arg("silver_path")
    gold_path = s3_io.get_arg("gold_path")
    if not silver_path or not gold_path:
        raise SystemExit("run_glue requires --silver_path and --gold_path")

    cfg = local_runner.load_config("transformations.yaml")
    silver = s3_io.read_parquet_prefix(silver_path)
    gold = local_runner.silver_to_gold(silver, cfg)

    for name, tbl in gold.items():
        # Each table gets its own subfolder: Hive/Athena/Glue tables are
        # folder-based, so 6 different-schema tables' files can't share one
        # prefix without a Glue Catalog table over that prefix reading them
        # all as one (see register_catalog.py's register_tables()).
        target = gold_path.rstrip("/") + f"/{name}/{name}.parquet"
        s3_io.write_parquet(tbl, target)
        print(f"[gold] {name}: {len(tbl)} rows -> {target}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--silver", default="output/advisory_transactions/silver/silver_advisory_transactions.parquet")
    ap.add_argument("--out", default="output/advisory_transactions")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.silver, args.out)
    else:
        run_glue()
