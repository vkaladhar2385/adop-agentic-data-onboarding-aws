"""Shim: pandas transforms live in shared.transforms.pandas_engine."""
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
except ImportError:  # pragma: no cover
    import pandas_engine as _engine  # type: ignore

WORKLOAD_DIR = _self.parents[2] if len(_self.parents) > 4 else _self.parent
CONFIG_DIR = WORKLOAD_DIR / "config"


def load_config(name: str) -> dict:
    return _engine.load_config(name, CONFIG_DIR)


def ingest_bronze(csv_path: str | Path) -> pd.DataFrame:
    return _engine.ingest_bronze(csv_path, "csv")


def bronze_to_silver(bronze: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    silver, quarantine, _suppressed = _engine.bronze_to_silver(bronze, cfg)
    return silver, quarantine


def silver_to_gold(silver: pd.DataFrame, cfg: dict) -> dict[str, pd.DataFrame]:
    return _engine.silver_to_gold(silver, cfg)
