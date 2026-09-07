"""Synthetic JSONL generator for the `web_events` GDPR demo workload.

Simulates a Kinesis/clickstream landing file: one JSON object per line.
Seeds consent-denied rows, missing event ids, and a duplicate so GDPR
filters and quality gates have something to catch.

Usage:
    python demo/data_generators/generate_web_events.py \
        --rows 240 --out demo/sample_data/web_events.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

EVENT_TYPES = ["page_view", "click", "session_start", "session_end"]
SOURCES = ["organic", "paid", "email", "direct", "referral"]
PAGES = ["/", "/pricing", "/login", "/accounts", "/help"]


def generate(rows: int, seed: int, start: datetime) -> list[dict]:
    rng = random.Random(seed)
    events: list[dict] = []
    for i in range(1, rows + 1):
        ts = start + timedelta(minutes=rng.randint(0, 180), seconds=rng.randint(0, 59))
        uid = f"U{rng.randint(1001, 1080)}"
        events.append({
            "event_id": f"EVT{i:07d}",
            "user_id": uid,
            "session_id": f"SES{uid[1:]}-{ts.strftime('%Y%m%d%H')}",
            "event_type": rng.choice(EVENT_TYPES),
            "event_ts": ts.isoformat(),
            "page_path": rng.choice(PAGES),
            "traffic_source": rng.choice(SOURCES),
            "ip_address": f"203.0.113.{rng.randint(1, 250)}",
            "user_email": f"user{uid[1:]}@example.com",
            "consent_analytics": True,
            "country": rng.choice(["US", "GB", "DE", "FR", "IN"]),
            "ingestion_ts": start.isoformat(),
        })

    if len(events) >= 8:
        events[1]["consent_analytics"] = False          # GDPR: must not reach Gold
        events[2]["event_id"] = ""                      # completeness
        events[3]["event_type"] = "not-a-type"          # validity
        events[4]["ip_address"] = "not-an-ip"
        events[5]["user_email"] = "bad-email"
        dup = dict(events[0])
        dup["page_path"] = "/dup"                       # uniqueness
        events.append(dup)
    return events


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=240)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="demo/sample_data/web_events.jsonl")
    args = ap.parse_args()
    start = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
    events = generate(args.rows, args.seed, start)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")
    print(f"Wrote {len(events)} events -> {out}")


if __name__ == "__main__":
    main()
