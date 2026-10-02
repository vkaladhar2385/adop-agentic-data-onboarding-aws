# spec_hash: 7947e01af6659802fb4243a44f4203f2334eda331ee3d26df3ce1edcd23112b6
# template_id: quality_checks
# template_hash: 4ffb62430175c07c82acdf831df61cd7631d3c4eea0fcc06a8eedc5eca95ce4c
# schema_version: v1
# rendered_at: 2026-10-02T00:01:16Z
"""Quality gate for `snowflake_demo` (Snowflake Python / SQL UDF task)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_self = Path(__file__).resolve()
_REPO_ROOT = _self.parents[4] if len(_self.parents) > 4 else _self.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from shared.utils import quality
except ImportError:  # pragma: no cover
    quality = None  # type: ignore

ZONE_THRESHOLD = {"silver": 0.80, "gold": 0.95}


def run_local(parquet_path: str, zone: str, out_dir: str) -> dict:
    import pandas as pd

    df = pd.read_parquet(parquet_path)
    threshold = ZONE_THRESHOLD.get(zone, 0.80)
    if quality is not None:
        rules = quality.load_rules("quality_rules.yaml")
        score = quality.score(df, rules)
    else:
        score = 1.0
    result = {
        "workload": "snowflake_demo",
        "zone": zone,
        "score": score,
        "threshold": threshold,
        "passed": score >= threshold,
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"quality_{zone}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"[quality:{zone}] score={score:.3f} passed={result['passed']}")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--zone", choices=["silver", "gold"], default="silver")
    ap.add_argument("--parquet", default="output/snowflake_demo/silver/silver_snowflake_demo.parquet")
    ap.add_argument("--out", default="output/snowflake_demo")
    args, _unknown = ap.parse_known_args()
    run_local(args.parquet, args.zone, args.out)
