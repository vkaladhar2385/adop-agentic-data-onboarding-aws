"""Local transformation core for `customer_orders` (pandas, no AWS)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml

_self = Path(__file__).resolve()
_REPO_ROOT = _self.parents[4] if len(_self.parents) > 4 else _self.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

WORKLOAD_DIR = _self.parents[2] if len(_self.parents) > 4 else _self.parent
CONFIG_DIR = WORKLOAD_DIR / "config"

INT_COLS = ["quantity"]


def load_config(name: str) -> dict:
    for candidate in (CONFIG_DIR / name, Path(__file__).resolve().parent / name):
        if candidate.exists():
            with candidate.open(encoding="utf-8") as fh:
                return yaml.safe_load(fh)
    raise FileNotFoundError(f"{name} not found under {CONFIG_DIR}")


def ingest_bronze(csv_path: str | Path) -> pd.DataFrame:
    return pd.read_csv(csv_path, dtype=str, keep_default_na=False, na_values=[""])


def _hash_customer_id(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _quarantine_flags(df: pd.DataFrame) -> pd.DataFrame:
    oid = df["order_id"].astype(str).str.strip()
    qty = pd.to_numeric(df["quantity"], errors="coerce")
    flags = pd.DataFrame(index=df.index)
    flags["missing_order_id"] = df["order_id"].isna() | (oid == "") | (oid == "nan")
    flags["invalid_quantity"] = qty.isna() | (qty < 1)
    return flags


def bronze_to_silver(bronze: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    b2s = cfg["bronze_to_silver"]
    df = bronze.copy()
    keys = b2s["dedup"]["keys"]
    order_by = b2s["dedup"]["order_by"]
    blank = df["order_id"].isna() | (df["order_id"].astype(str).str.strip() == "")
    keyed = df[~blank].sort_values(order_by).drop_duplicates(subset=keys, keep="last")
    df = pd.concat([keyed, df[blank]], ignore_index=True)

    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].apply(lambda v: v.strip() if isinstance(v, str) else v)
    for col in b2s["string_ops"]["uppercase"]:
        df[col] = df[col].apply(lambda v: v.upper() if isinstance(v, str) else v)

    for mask_rule in b2s.get("pii_masking", []):
        col = mask_rule["column"]
        if mask_rule.get("method") == "hash" and col in df.columns:
            df[col] = df[col].apply(lambda v: _hash_customer_id(str(v)) if str(v).strip() else v)

    flags = _quarantine_flags(df)
    bad = flags.any(axis=1)
    quarantine = df[bad].copy()
    quarantine = quarantine.join(
        flags[bad].apply(lambda r: ",".join([k for k, v in r.items() if v]), axis=1).rename(
            "quarantine_reason"
        )
    )
    silver = df[~bad].copy().reset_index(drop=True)

    for col in INT_COLS:
        silver[col] = pd.to_numeric(silver[col], errors="coerce").astype("Int64")
    silver["order_total"] = pd.to_numeric(silver["order_total"], errors="coerce")
    silver["updated_at"] = pd.to_datetime(silver["updated_at"], errors="coerce")
    silver["order_date"] = pd.to_datetime(silver["order_date"], errors="coerce")
    silver["line_value"] = silver["order_total"]
    return silver, quarantine


def silver_to_gold(silver: pd.DataFrame, cfg: dict) -> dict[str, pd.DataFrame]:
    s2g = cfg["silver_to_gold"]
    suppress = s2g["gold_pii_policy"]["suppress"]
    gold = silver.drop(columns=[c for c in suppress if c in silver.columns], errors="ignore")
    table = s2g.get("table", "gold_customer_orders")
    return {table: gold.reset_index(drop=True)}
