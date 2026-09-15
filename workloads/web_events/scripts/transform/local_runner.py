"""Shim: pandas transforms live in shared.transforms.pandas_engine (GDPR JSONL)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_self = Path(__file__).resolve()
_REPO_ROOT = _self.parents[4] if len(_self.parents) > 4 else _self.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from shared.transforms import pandas_engine as _engine
except ImportError:  # pragma: no cover - Glue flat extra-py-files
    import pandas_engine as _engine  # type: ignore

WORKLOAD_DIR = _self.parents[2] if len(_self.parents) > 4 else _self.parent
CONFIG_DIR = WORKLOAD_DIR / "config"


def load_config(name: str) -> dict:
    return _engine.load_config(name, CONFIG_DIR)


def ingest_bronze(jsonl_path: str | Path) -> pd.DataFrame:
    return _engine.ingest_bronze(jsonl_path, "jsonl")


def bronze_to_silver(
    bronze: pd.DataFrame, cfg: dict
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return _engine.bronze_to_silver(bronze, cfg)


def silver_to_gold(silver: pd.DataFrame, cfg: dict) -> dict[str, pd.DataFrame]:
    return _engine.silver_to_gold(silver, cfg)


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
