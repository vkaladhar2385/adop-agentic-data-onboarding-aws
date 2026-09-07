"""Bronze -> Silver transform for `advisory_transactions`.

Production runs on AWS Glue writing Apache Iceberg to the Silver zone. The
cleaning/masking/quarantine rules are declared in config/transformations.yaml
and executed by `local_runner.bronze_to_silver`, so the Glue job and the local
demo apply identical logic.
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


def run_local(bronze_parquet: str, out_dir: str) -> dict:
    import pandas as pd
    cfg = local_runner.load_config("transformations.yaml")
    bronze = pd.read_parquet(bronze_parquet)
    silver, quarantine = local_runner.bronze_to_silver(bronze, cfg)

    out = Path(out_dir)
    (out / "silver").mkdir(parents=True, exist_ok=True)
    (out / "quarantine").mkdir(parents=True, exist_ok=True)
    silver.to_parquet(out / "silver" / "silver_advisory_transactions.parquet", index=False)
    quarantine.to_csv(out / "quarantine" / "quarantine.csv", index=False)
    print(f"[silver] clean rows: {len(silver)}  |  quarantined: {len(quarantine)}")
    return {"silver": silver, "quarantine": quarantine}


def run_glue():  # pragma: no cover - requires AWS runtime
    """Production path. Runs as a Glue Python Shell job; rules are identical
    to local_runner.bronze_to_silver so demo and AWS behaviour can't drift.

    Writes clean rows to --silver_path as Parquet (a real deployment would
    target Iceberg on S3 Tables with the Silver KMS CMK -- Parquet here keeps
    the pilot's Athena/Glue Catalog wiring simple). Quarantine rows are
    written to a sibling `quarantine/` prefix for SOX human review rather
    than dropped, satisfying the `no silent row drops` guardrail.
    """
    try:
        from shared.utils import s3_io
    except ImportError:
        import s3_io  # type: ignore

    bronze_path = s3_io.get_arg("bronze_path")
    silver_path = s3_io.get_arg("silver_path")
    if not bronze_path or not silver_path:
        raise SystemExit("run_glue requires --bronze_path and --silver_path")

    cfg = local_runner.load_config("transformations.yaml")
    bronze = s3_io.read_parquet_prefix(bronze_path)
    silver, quarantine = local_runner.bronze_to_silver(bronze, cfg)

    silver_target = silver_path.rstrip("/") + "/silver_advisory_transactions.parquet"
    s3_io.write_parquet(silver, silver_target)

    if len(quarantine):
        quarantine_target = silver_path.rstrip("/").replace("/silver/", "/quarantine/") + "/quarantine.csv"
        s3_io.write_csv(quarantine, quarantine_target)

    print(f"[silver] clean rows: {len(silver)}  |  quarantined: {len(quarantine)} -> {silver_target}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--bronze", default="output/advisory_transactions/bronze/bronze_advisory_transactions.parquet")
    ap.add_argument("--out", default="output/advisory_transactions")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.bronze, args.out)
    else:
        run_glue()
