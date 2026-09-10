#!/usr/bin/env python3
"""Verify Gateway-style Lambda handler routing (Step 2 local smoke).

Usage:
  python tools/verify_factory_gateway.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


class _Custom:
    def __init__(self, data: dict):
        self.custom = data


class _Context:
    def __init__(self, target: str, tool: str):
        self.client_context = _Custom({"bedrockAgentCoreToolName": f"{target}___{tool}"})


def _load_handler(rel_path: str, mod_name: str):
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod.handler


def main() -> int:
    failures = 0

    glue_handler = _load_handler("mcp-servers/glue-athena-server/lambda_handler.py", "glue_athena")
    out = glue_handler({}, _Context("glue-athena", "get_databases"))
    print("glue-athena:", json.dumps(out)[:400])
    if "databases" in out or out.get("status") == "success":
        print("PASS glue-athena gateway routing")
    else:
        print("FAIL glue-athena")
        failures += 1

    factory_handler = _load_handler("mcp-servers/gateway-lambdas/factory/lambda_handler.py", "factory")
    try:
        factory_handler(
            {
                "workload": "supplier_lead_times",
                "bucket": "adop-datalake-199064440913-us-east-1",
                "approve": True,
                "run_e2e": False,
            },
            _Context("factory", "trigger_provision"),
        )
        print("FAIL factory (expected SFN lookup error)")
        failures += 1
    except LookupError as exc:
        print(f"PASS factory gateway routing (SFN pending): {exc}")
    except Exception as exc:
        print(f"FAIL factory unexpected: {exc}")
        failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
