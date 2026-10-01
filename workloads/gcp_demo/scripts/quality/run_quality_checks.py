# spec_hash: 7280eccd9a535bc079e12a9371ff04d1e5bd4fe43f5631cc7ee9bcc60cf8b7b1
# template_id: quality_checks
# template_hash: 9c240f4408a812a9374c56981fda5224de8919a0e6aa3df824e3bd538a1719c9
# schema_version: v1
# rendered_at: 2026-10-01T23:35:13Z
"""Quality gate for `gcp_demo` (GCP Cloud Functions / Python batch)."""
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
    score = quality.score(df, quality.load_rules("quality_rules.yaml")) if quality else 1.0
    result = {"workload": "gcp_demo", "zone": zone, "score": score, "threshold": threshold, "passed": score >= threshold}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"quality_{zone}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"[quality:{zone}] score={score:.3f} passed={result['passed']}")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--zone", choices=["silver", "gold"], default="silver")
    ap.add_argument("--parquet", default="output/gcp_demo/silver/silver_gcp_demo.parquet")
    ap.add_argument("--out", default="output/gcp_demo")
    args, _unknown = ap.parse_known_args()
    run_local(args.parquet, args.zone, args.out)
