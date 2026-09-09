"""Local-mode transformation core for `product_inventory`.

Pure pandas, no AWS, no Spark. Glue/PySpark entrypoints use the same
`config/transformations.yaml` rules.
"""
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

INT_COLS = ["on_hand_qty", "reserved_qty"]
DECIMAL_COLS = ["unit_cost", "list_price"]


def load_config(name: str) -> dict:
    for candidate in (CONFIG_DIR / name, Path(__file__).resolve().parent / name):
        if candidate.exists():
            with candidate.open(encoding="utf-8") as fh:
                return yaml.safe_load(fh)
    raise FileNotFoundError(f"{name} not found in {CONFIG_DIR} or {Path(__file__).resolve().parent}")


def ingest_bronze(csv_path: str | Path) -> pd.DataFrame:
    return pd.read_csv(csv_path, dtype=str, keep_default_na=False, na_values=[""])


def _quarantine_flags(df: pd.DataFrame) -> pd.DataFrame:
    sku = df["sku"].astype(str).str.strip()
    on_hand = pd.to_numeric(df["on_hand_qty"], errors="coerce")
    flags = pd.DataFrame(index=df.index)
    flags["missing_sku"] = df["sku"].isna() | (sku == "") | (sku == "nan")
    flags["negative_on_hand"] = on_hand.fillna(0) < 0
    return flags


def bronze_to_silver(bronze: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    b2s = cfg["bronze_to_silver"]
    df = bronze.copy()

    keys = b2s["dedup"]["keys"]
    order_by = b2s["dedup"]["order_by"]
    # Blank SKUs must stay visible for quarantine; only drop dups among non-blank keys.
    blank = df["sku"].isna() | (df["sku"].astype(str).str.strip() == "")
    keyed = df[~blank].sort_values(order_by).drop_duplicates(subset=keys, keep="last")
    df = pd.concat([keyed, df[blank]], ignore_index=True)

    str_cols = df.select_dtypes(include="object").columns
    for c in str_cols:
        df[c] = df[c].apply(lambda v: v.strip() if isinstance(v, str) else v)
    for c in b2s["string_ops"]["uppercase"]:
        df[c] = df[c].apply(lambda v: v.upper() if isinstance(v, str) else v)

    flags = _quarantine_flags(df)
    bad_mask = flags.any(axis=1)
    quarantine = df[bad_mask].copy()
    quarantine = quarantine.join(
        flags[bad_mask].apply(
            lambda r: ",".join([k for k, v in r.items() if v]), axis=1
        ).rename("quarantine_reason")
    )
    silver = df[~bad_mask].copy().reset_index(drop=True)

    for c in INT_COLS:
        silver[c] = pd.to_numeric(silver[c], errors="coerce").astype("Int64")
    for c in DECIMAL_COLS:
        silver[c] = pd.to_numeric(silver[c], errors="coerce")
    silver["updated_at"] = pd.to_datetime(silver["updated_at"], errors="coerce")

    silver["available_qty"] = silver["on_hand_qty"] - silver["reserved_qty"]
    silver["inventory_value"] = silver["on_hand_qty"].astype(float) * silver["unit_cost"]
    silver["margin_pct"] = silver.apply(
        lambda r: (r["list_price"] - r["unit_cost"]) / r["list_price"]
        if pd.notna(r["list_price"]) and r["list_price"] > 0
        else None,
        axis=1,
    )
    return silver, quarantine


def silver_to_gold(silver: pd.DataFrame, cfg: dict) -> dict[str, pd.DataFrame]:
    s2g = cfg["silver_to_gold"]
    suppress = s2g["gold_pii_policy"]["suppress"]
    gold = silver.drop(columns=[c for c in suppress if c in silver.columns], errors="ignore")
    table = s2g.get("table", "gold_product_inventory")
    return {table: gold.reset_index(drop=True)}
