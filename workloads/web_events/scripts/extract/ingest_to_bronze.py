# spec_hash: 563445dc75b490a5b7b780e2be3eef805f4bdfb15c876d045a7e4b45de244631
# template_id: ingest_to_bronze
# template_hash: cbf6bbb214796aedb3203a59c1cf5b1fb28daf2898565513dbe9033abe18916f
# schema_version: v1
# rendered_at: 2026-09-09T05:13:34Z
"""Bronze ingestion for `web_events`. Bronze is never transformed."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_self = Path(__file__).resolve()
_REPO_ROOT = _self.parents[4] if len(_self.parents) > 4 else _self.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from workloads.web_events.scripts.transform.local_runner import ingest_bronze
except ImportError:
    from local_runner import ingest_bronze  # type: ignore


def run_local(source_path: str, out_dir: str) -> str:
    df = ingest_bronze(source_path)
    out = Path(out_dir) / "bronze"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "bronze_web_events.jsonl"
    df.to_json(target, orient="records", lines=True)
    print(f"[bronze] ingested {len(df)} rows (immutable) -> {target}")
    return str(target)


def run_glue():  # pragma: no cover
    raise SystemExit("Glue path runs inside AWS Glue; use --local for the demo.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--source", default="demo/sample_data/web_events.jsonl")
    ap.add_argument("--out", default="output/web_events")
    args, _unknown = ap.parse_known_args()
    if args.local:
        run_local(args.source, args.out)
    else:
        run_glue()
