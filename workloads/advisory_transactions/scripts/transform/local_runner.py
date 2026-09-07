"""Local-mode transformation core for `advisory_transactions`.

This is the single source of transformation truth. The Glue/PySpark production
entrypoints (`bronze_to_silver.py`, `silver_to_gold.py`) call into the same
declarative rules (`config/transformations.yaml`), so local demo/test behaviour
cannot drift from what runs on AWS.

Pure pandas, no AWS, no Spark -> runs anywhere pytest runs.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

# Make `shared` importable whether run from repo root or workload dir.
import sys
_self = Path(__file__).resolve()
_REPO_ROOT = _self.parents[4] if len(_self.parents) > 4 else _self.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from shared.utils.pii import mask_email, mask_ssn, hash_token  # noqa: E402
except ImportError:
    # Glue Python Shell: this file is deployed flat via --extra-py-files
    # (glue.tf) alongside pii.py, not as part of the `shared` package.
    from pii import mask_email, mask_ssn, hash_token  # type: ignore  # noqa: E402

WORKLOAD_DIR = _self.parents[2] if len(_self.parents) > 4 else _self.parent
CONFIG_DIR = WORKLOAD_DIR / "config"

DECIMAL_COLS = ["quantity", "unit_price", "gross_amount", "commission", "fees", "net_amount"]


def load_config(name: str) -> dict:
    # Local/repo layout: workloads/<w>/config/<name>. On Glue this file and the
    # yaml are deployed flat side-by-side via --extra-py-files/--extra-files.
    for candidate in (CONFIG_DIR / name, Path(__file__).resolve().parent / name):
        if candidate.exists():
            with candidate.open(encoding="utf-8") as fh:
                return yaml.safe_load(fh)
    raise FileNotFoundError(f"{name} not found in {CONFIG_DIR} or {Path(__file__).resolve().parent}")


# ---- Bronze ----------------------------------------------------------------

def ingest_bronze(csv_path: str | Path) -> pd.DataFrame:
    """Read the raw source file as-is (all strings) -> immutable Bronze frame."""
    return pd.read_csv(csv_path, dtype=str, keep_default_na=False, na_values=[""])


# ---- Bronze -> Silver ------------------------------------------------------

def _quarantine_flags(df: pd.DataFrame) -> pd.DataFrame:
    num = {c: pd.to_numeric(df[c], errors="coerce") for c in DECIMAL_COLS}
    trade_ok = pd.to_datetime(df["trade_date"], errors="coerce", format="%Y-%m-%d").notna()

    gross_expected = num["quantity"] * num["unit_price"]
    net_expected = num["gross_amount"] - num["commission"] - num["fees"]

    flags = pd.DataFrame(index=df.index)
    flags["invalid_trade_date"] = ~trade_ok
    flags["negative_quantity"] = num["quantity"].fillna(-1) < 0
    flags["missing_net_amount"] = df["net_amount"].isna() | (df["net_amount"].astype(str).str.strip() == "")
    flags["broken_gross_formula"] = (num["gross_amount"] - gross_expected).abs() > 0.01
    flags["broken_net_formula"] = (num["net_amount"] - net_expected).abs() > 0.01
    return flags


def bronze_to_silver(bronze: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (silver_clean, quarantine). Follows config/transformations.yaml."""
    b2s = cfg["bronze_to_silver"]
    df = bronze.copy()

    # 1) dedup (keep latest by ingestion_date)
    keys = b2s["dedup"]["keys"]
    order_by = b2s["dedup"]["order_by"]
    df = df.sort_values(order_by).drop_duplicates(subset=keys, keep="last").reset_index(drop=True)

    # 2) string ops
    str_cols = df.select_dtypes(include="object").columns
    for c in str_cols:
        df[c] = df[c].astype(str).where(df[c].notna(), None)
        df[c] = df[c].apply(lambda v: v.strip() if isinstance(v, str) else v)
    for c in b2s["string_ops"]["uppercase"]:
        df[c] = df[c].apply(lambda v: v.upper() if isinstance(v, str) else v)

    # 3) quarantine rows failing any critical check (do NOT drop silently)
    flags = _quarantine_flags(df)
    bad_mask = flags.any(axis=1)
    quarantine = df[bad_mask].copy()
    quarantine = quarantine.join(flags[bad_mask].apply(
        lambda r: ",".join([k for k, v in r.items() if v]), axis=1).rename("quarantine_reason"))
    silver = df[~bad_mask].copy().reset_index(drop=True)

    # 4) type casts on clean rows
    for c in DECIMAL_COLS:
        silver[c] = pd.to_numeric(silver[c], errors="coerce")
    silver["trade_date"] = pd.to_datetime(silver["trade_date"], errors="coerce").dt.date
    silver["settlement_date"] = pd.to_datetime(silver["settlement_date"], errors="coerce").dt.date

    # 5) PII masking (SOX + PII: masked in Silver, raw never persisted downstream)
    silver["client_ssn"] = silver["client_ssn"].apply(mask_ssn)
    silver["client_email"] = silver["client_email"].apply(mask_email)
    silver["client_id"] = silver["client_id"].apply(hash_token)

    # 6) derived columns
    silver["trade_year"] = silver["trade_date"].apply(lambda d: d.year if pd.notna(d) else None)
    silver["trade_month"] = silver["trade_date"].apply(lambda d: d.month if pd.notna(d) else None)

    return silver, quarantine


# ---- Silver -> Gold (star schema) -----------------------------------------

def silver_to_gold(silver: pd.DataFrame, cfg: dict) -> dict[str, pd.DataFrame]:
    s2g = cfg["silver_to_gold"]
    suppress = s2g["gold_pii_policy"]["suppress"]

    fact_cols = (["transaction_id", "account_id", "advisor_id", "security_id", "trade_date"]
                 + s2g["fact"]["measures"])
    fact = silver[fact_cols].copy()

    dim_account = (silver[["account_id", "account_type", "branch_code", "client_id"]]
                   .drop_duplicates("account_id").reset_index(drop=True))
    dim_advisor = (silver[["advisor_id", "advisor_name", "branch_code"]]
                   .drop_duplicates("advisor_id").reset_index(drop=True))
    dim_security = (silver[["security_id", "security_name", "asset_class"]]
                    .drop_duplicates("security_id").reset_index(drop=True))
    dim_date = (silver[["trade_date", "trade_year", "trade_month"]]
                .drop_duplicates("trade_date").reset_index(drop=True))
    dim_date["trade_quarter"] = dim_date["trade_month"].apply(
        lambda m: (int(m) - 1) // 3 + 1 if pd.notna(m) else None)

    summary = (silver.groupby(["advisor_id", "trade_date"], as_index=False)
               .agg(total_net_amount=("net_amount", "sum"),
                    total_commission=("commission", "sum"),
                    transaction_count=("transaction_id", "count")))

    gold = {
        "fact_transactions": fact,
        "dim_account": dim_account,
        "dim_advisor": dim_advisor,
        "dim_security": dim_security,
        "dim_date": dim_date,
        "gold_advisor_daily_summary": summary,
    }

    # Enforce PII suppression across every Gold table.
    for name, tbl in gold.items():
        drop_cols = [c for c in suppress if c in tbl.columns]
        if drop_cols:
            gold[name] = tbl.drop(columns=drop_cols)
    return gold


# ---- Convenience: run the whole thing --------------------------------------

def run_pipeline(csv_path: str | Path) -> dict:
    cfg = load_config("transformations.yaml")
    bronze = ingest_bronze(csv_path)
    silver, quarantine = bronze_to_silver(bronze, cfg)
    gold = silver_to_gold(silver, cfg)
    return {"bronze": bronze, "silver": silver, "quarantine": quarantine, "gold": gold}
