"""Local transformation core for `web_events` (GDPR clickstream).

Reads JSONL (stream-landing shape). Filters consent=false out of processing,
hashes user_id, masks email/IP, quarantines invalid events, rolls Gold hourly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.utils.pii import hash_token, mask_email, mask_ip  # noqa: E402

WORKLOAD_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = WORKLOAD_DIR / "config"
IP_RE = r"^\d{1,3}(\.\d{1,3}){3}$"
ALLOWED_TYPES = {"page_view", "click", "session_start", "session_end"}


def load_config(name: str) -> dict:
    with (CONFIG_DIR / name).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def ingest_bronze(jsonl_path: str | Path) -> pd.DataFrame:
    rows = []
    with Path(jsonl_path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return pd.DataFrame(rows)


def _as_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(["true", "1"])


def bronze_to_silver(bronze: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (silver, quarantine, suppressed_no_consent)."""
    df = bronze.copy()
    keys = cfg["bronze_to_silver"]["dedup"]["keys"]
    order_by = cfg["bronze_to_silver"]["dedup"]["order_by"]
    df = df.sort_values(order_by).drop_duplicates(subset=keys, keep="last").reset_index(drop=True)

    consent = _as_bool(df["consent_analytics"])
    suppressed = df[~consent].copy()
    work = df[consent].copy()

    missing_id = work["event_id"].isna() | (work["event_id"].astype(str).str.strip() == "")
    bad_type = ~work["event_type"].isin(ALLOWED_TYPES)
    bad_ip = ~work["ip_address"].astype(str).str.match(IP_RE, na=False)
    flags = pd.DataFrame({
        "missing_event_id": missing_id,
        "invalid_event_type": bad_type,
        "invalid_ip": bad_ip,
    }, index=work.index)
    bad = flags.any(axis=1)
    quarantine = work[bad].copy()
    quarantine["quarantine_reason"] = flags[bad].apply(
        lambda r: ",".join([k for k, v in r.items() if v]), axis=1)
    silver = work[~bad].copy().reset_index(drop=True)

    silver["user_id"] = silver["user_id"].apply(hash_token)
    silver["user_email"] = silver["user_email"].apply(mask_email)
    silver["ip_address"] = silver["ip_address"].apply(mask_ip)
    silver["event_ts"] = pd.to_datetime(silver["event_ts"], utc=True, errors="coerce")
    silver["event_hour"] = silver["event_ts"].dt.floor("h")
    silver["consent_analytics"] = True
    return silver, quarantine, suppressed


def silver_to_gold(silver: pd.DataFrame, cfg: dict) -> dict[str, pd.DataFrame]:
    suppress = cfg["silver_to_gold"]["gold_pii_policy"]["suppress"]
    hourly = (silver.groupby(["traffic_source", "event_hour"], as_index=False)
              .agg(event_count=("event_id", "count"),
                   page_views=("event_type", lambda s: int((s == "page_view").sum())),
                   unique_users=("user_id", "nunique")))
    # Right-to-erasure lookup: hashed user_id -> row count (ops can delete by token)
    erasure = (silver.groupby("user_id", as_index=False)
               .agg(event_count=("event_id", "count")))
    erasure["erasure_hook"] = "DELETE FROM silver_web_events WHERE user_id = :token"
    gold = {
        "gold_hourly_traffic": hourly,
        "gold_erasure_index": erasure,
    }
    for name, tbl in list(gold.items()):
        drop = [c for c in suppress if c in tbl.columns]
        if drop:
            gold[name] = tbl.drop(columns=drop)
    return gold


def run_pipeline(jsonl_path: str | Path) -> dict:
    cfg = load_config("transformations.yaml")
    bronze = ingest_bronze(jsonl_path)
    silver, quarantine, suppressed = bronze_to_silver(bronze, cfg)
    gold = silver_to_gold(silver, cfg)
    return {
        "bronze": bronze,
        "silver": silver,
        "quarantine": quarantine,
        "suppressed_no_consent": suppressed,
        "gold": gold,
    }
